from dataclasses import asdict, dataclass, field
from enum import Enum
import threading
import time
from typing import Any


class SystemMode(str, Enum):
    IDLE = "IDLE"
    BLUE_SNAKE_DETECTED = "BLUE_SNAKE_DETECTED"
    APPROACHING_SNAKE = "APPROACHING_SNAKE"
    STOPPED = "STOPPED"


@dataclass
class SystemState:
    mode: SystemMode = SystemMode.IDLE
    emergency_stop: bool = False
    stop_state: str = "clear"
    fake_spot_mode: bool = True
    spot_mode: str = "fake"
    spot_real_available: bool = False
    spot_connected: bool = False
    spot_host: str = ""
    spot_last_error: str = ""
    spot_last_action: str = ""
    spot_last_action_status: str = ""
    spot_powered_on: bool | None = None
    spot_estopped: bool | None = None
    spot_lease_status: str = ""
    spot_battery_percentage: float | None = None
    spot_battery_status: str = ""
    blue_snake_visible: bool = False
    blue_snake_stable: bool = False
    last_vision_raw: str = ""
    last_vision_time: float | None = None
    last_vision_duration_s: float | None = None
    auto_vision_enabled: bool = False
    auto_vision_interval_s: float = 5.0
    last_auto_vision_time: float | None = None
    last_frame_time: float | None = None
    last_audio_phrase: str = ""
    last_parsed_voice_command: str = ""
    last_rejected_voice_reason: str = ""
    last_recognized_phrase: str = ""
    last_accepted_command: str = ""
    audio_input_enabled: bool = False
    audio_in_backend: str = ""
    audio_channels: int = 1
    audio_input_device: int | str | None = None
    audio_input_device_name: str = ""
    audio_input_max_channels: int | None = None
    audio_input_default_samplerate: float | None = None
    audio_input_requested_samplerate: int | None = None
    audio_input_chunk_s: float | None = None
    last_audio_rms: float | None = None
    last_audio_peak: float | None = None
    audio_left_rms: float | None = None
    audio_right_rms: float | None = None
    audio_peak_left: float | None = None
    audio_peak_right: float | None = None
    audio_lr_db: float | None = None
    audio_direction: str = ""
    audio_direction_confidence: float = 0.0
    audio_activity_active: bool = False
    audio_activity_until: float | None = None
    audio_out_suppress_until: float | None = None
    audio_queue_length: int = 0
    inference_owner: str = ""
    last_auto_vision_skip_reason: str = ""
    last_vision_cancel_reason: str = ""
    last_command: str = ""
    last_command_status: str = ""
    last_command_time: float | None = None
    command_log: list[str] = field(default_factory=list)


class SharedState:
    def __init__(self) -> None:
        self._state = SystemState()
        self._lock = threading.RLock()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            data = asdict(self._state)
            data["mode"] = self._state.mode.value
            return data

    def update(self, **kwargs: Any) -> None:
        with self._lock:
            for key, value in kwargs.items():
                if not hasattr(self._state, key):
                    raise KeyError(f"Unknown state field: {key}")
                setattr(self._state, key, value)

    def append_command_log(self, message: str, max_items: int = 100) -> None:
        with self._lock:
            stamped = f"{time.strftime('%H:%M:%S')} {message}"
            self._state.command_log.append(stamped)
            self._state.command_log = self._state.command_log[-max_items:]

    def get_mode(self) -> SystemMode:
        with self._lock:
            return self._state.mode

    def set_mode(self, mode: SystemMode) -> None:
        with self._lock:
            self._state.mode = mode

    def is_stopped(self) -> bool:
        with self._lock:
            return self._state.emergency_stop


shared_state = SharedState()
