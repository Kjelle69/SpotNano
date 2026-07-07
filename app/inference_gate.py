import contextlib
import threading
import time
from collections.abc import Iterator

from app.logger import event_logger


_lock = threading.Lock()
_state_lock = threading.RLock()
_current_owner = ""
_audio_activity_until = 0.0
_vision_cancel_requested = False
_vision_cancel_reason = ""


@contextlib.contextmanager
def acquire_inference(name: str, priority: str = "normal", timeout: float = 0.0) -> Iterator[bool]:
    if name == "audio_whisper" and get_current_owner() == "vision_moondream":
        request_cancel_vision("audio_priority")

    acquired = _lock.acquire(timeout=max(0.0, float(timeout)))
    if not acquired:
        event_logger.event("inference_skipped_busy", name=name, priority=priority)
        yield False
        return

    _set_current_owner(name)
    event_logger.event("inference_acquired", name=name, priority=priority)
    try:
        yield True
    finally:
        _set_current_owner("")
        _lock.release()
        event_logger.event("inference_released", name=name, priority=priority)


def get_current_owner() -> str:
    with _state_lock:
        return _current_owner


def mark_audio_activity(duration_s: float = 4.0) -> None:
    global _audio_activity_until
    until = time.time() + max(0.0, float(duration_s))
    with _state_lock:
        _audio_activity_until = max(_audio_activity_until, until)
    _update_shared_state(audio_activity_active=True, audio_activity_until=_audio_activity_until)
    event_logger.event("audio_activity_detected", duration_s=duration_s, active_until=_audio_activity_until)


def is_audio_activity_active() -> bool:
    with _state_lock:
        active = time.time() < _audio_activity_until
        until = _audio_activity_until if active else None
    _update_shared_state(audio_activity_active=active, audio_activity_until=until)
    return active


def clear_audio_activity() -> None:
    global _audio_activity_until
    with _state_lock:
        _audio_activity_until = 0.0
    _update_shared_state(audio_activity_active=False, audio_activity_until=None)


def request_cancel_vision(reason: str = "audio_activity") -> None:
    global _vision_cancel_requested, _vision_cancel_reason
    with _state_lock:
        _vision_cancel_requested = True
        _vision_cancel_reason = reason
    _update_shared_state(last_vision_cancel_reason=reason)
    event_logger.event("vision_cancel_requested", reason=reason, owner=get_current_owner())


def should_cancel_vision() -> bool:
    with _state_lock:
        return _vision_cancel_requested or time.time() < _audio_activity_until


def clear_cancel_vision() -> None:
    global _vision_cancel_requested, _vision_cancel_reason
    with _state_lock:
        _vision_cancel_requested = False
        _vision_cancel_reason = ""


def get_vision_cancel_reason() -> str:
    with _state_lock:
        if _vision_cancel_reason:
            return _vision_cancel_reason
        if time.time() < _audio_activity_until:
            return "audio_activity"
        return ""


def _set_current_owner(name: str) -> None:
    global _current_owner
    with _state_lock:
        _current_owner = name
    _update_shared_state(inference_owner=name)


def _update_shared_state(**kwargs) -> None:
    try:
        from app.state import shared_state

        shared_state.update(**kwargs)
    except Exception:
        pass
