import threading
import time
from typing import Any

from app import audio_out
from app.config import config
from app.inference_gate import is_audio_activity_active
from app.logger import event_logger
from app.state import SharedState, SystemMode


class AutoVisionService:
    def __init__(self, state: SharedState, vision_service) -> None:
        self.state = state
        self.vision_service = vision_service
        self.vision_service.after_analysis = self.handle_post_analysis
        self._running = False
        self._busy = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_stable = False
        self._last_bark_time = 0.0
        self._auto_enabled = config.auto_vision_enabled

    def start(self) -> None:
        self.state.update(
            auto_vision_enabled=self.enabled,
            auto_vision_interval_s=config.auto_vision_interval_s,
        )
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        event_logger.event("auto_vision_started", enabled=self.enabled)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    @property
    def enabled(self) -> bool:
        return self._auto_enabled and config.vision_enabled

    def toggle(self) -> dict[str, Any]:
        self._auto_enabled = not self._auto_enabled
        self.state.update(auto_vision_enabled=self.enabled)
        event_logger.event("auto_vision_toggled", enabled=self.enabled)
        return {"auto_vision_enabled": self.enabled}

    def handle_post_analysis(self, source: str = "manual") -> None:
        snapshot = self.state.snapshot()
        stable = bool(snapshot["blue_snake_stable"])
        stopped = bool(snapshot["emergency_stop"])
        mode = SystemMode(snapshot["mode"])

        if stable and not stopped and mode == SystemMode.IDLE:
            self.state.set_mode(SystemMode.BLUE_SNAKE_DETECTED)
        elif not stable and not stopped and mode == SystemMode.BLUE_SNAKE_DETECTED:
            self.state.set_mode(SystemMode.IDLE)

        self._handle_bark_transition(stable)
        event_logger.event("vision_post_analysis", source=source, stable=stable, mode=self.state.get_mode().value)

    def _handle_bark_transition(self, stable: bool) -> bool:
        now = time.time()
        transitioned_to_stable = stable and not self._last_stable
        cooldown_ready = now - self._last_bark_time >= config.bark_cooldown_s
        self._last_stable = stable

        if not (config.bark_on_blue_snake and transitioned_to_stable and cooldown_ready):
            return False

        audio_out.bark_snake()
        self._last_bark_time = now
        self.state.update(last_audio_phrase="bark: blue snake detected")
        event_logger.event("blue_snake_bark")
        return True

    def _loop(self) -> None:
        while self._running:
            if self.enabled:
                self._analyze_if_idle()
            time.sleep(max(0.2, config.auto_vision_interval_s))

    def _analyze_if_idle(self) -> None:
        if is_audio_activity_active():
            self.state.update(
                last_auto_vision_time=time.time(),
                auto_vision_enabled=self.enabled,
                auto_vision_interval_s=config.auto_vision_interval_s,
                last_auto_vision_skip_reason="audio_active",
            )
            event_logger.event("auto_vision_skipped_audio_active")
            return

        with self._lock:
            if self._busy:
                return
            self._busy = True

        started = time.time()
        if hasattr(self.vision_service.camera, "has_frame") and not self.vision_service.camera.has_frame():
            self.state.update(
                last_auto_vision_time=started,
                auto_vision_enabled=self.enabled,
                auto_vision_interval_s=config.auto_vision_interval_s,
                last_auto_vision_skip_reason="no_frame",
            )
            event_logger.event("auto_vision_waiting_for_frame")
            with self._lock:
                self._busy = False
            return

        self.state.update(
            last_auto_vision_time=started,
            auto_vision_enabled=self.enabled,
            auto_vision_interval_s=config.auto_vision_interval_s,
            last_auto_vision_skip_reason="",
        )
        event_logger.event("auto_vision_started")
        try:
            result = self.vision_service.analyze_once(source="auto")
            if result.get("status") == "busy":
                self.state.update(last_auto_vision_skip_reason="busy")
                event_logger.event("auto_vision_skipped_busy")
                return
            if result.get("status") == "cancelled":
                self.state.update(last_auto_vision_skip_reason="cancelled")
            event_logger.event(
                "auto_vision_result",
                accepted=result.get("accepted"),
                status=result.get("status"),
                visible=result.get("visible"),
                raw=result.get("raw"),
                duration_s=result.get("duration_s"),
            )
        except Exception as exc:
            event_logger.event("auto_vision_error", error=str(exc))
        finally:
            with self._lock:
                self._busy = False
