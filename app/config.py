from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Config:
    app_name: str = "Spot Orin Nano"
    app_version: str = os.getenv("APP_VERSION", "v20260707g")
    real_spot_mode: bool = os.getenv("SPOT_REAL_MODE", "false").lower() == "true"
    camera_index: int = int(os.getenv("CAMERA_INDEX", "0"))
    camera_width: int = int(os.getenv("CAMERA_WIDTH", "640"))
    camera_height: int = int(os.getenv("CAMERA_HEIGHT", "480"))
    camera_fps: float = float(os.getenv("CAMERA_FPS", "8"))
    mjpeg_fps: float = float(os.getenv("MJPEG_FPS", "6"))
    camera_jpeg_quality: int = int(os.getenv("CAMERA_JPEG_QUALITY", "65"))
    camera_buffer_size: int = int(os.getenv("CAMERA_BUFFER_SIZE", "1"))
    camera_brightness_enabled: bool = os.getenv("CAMERA_BRIGHTNESS_ENABLED", "false").lower() == "true"
    camera_brightness_alpha: float = float(os.getenv("CAMERA_BRIGHTNESS_ALPHA", "1.08"))
    camera_brightness_beta: int = int(os.getenv("CAMERA_BRIGHTNESS_BETA", "6"))
    camera_control_brightness: int = int(os.getenv("CAMERA_CONTROL_BRIGHTNESS", "200"))
    camera_control_contrast: int = int(os.getenv("CAMERA_CONTROL_CONTRAST", "40"))
    camera_control_saturation: int = int(os.getenv("CAMERA_CONTROL_SATURATION", "140"))
    camera_control_gamma: int = int(os.getenv("CAMERA_CONTROL_GAMMA", "100"))
    camera_control_exposure: int = int(os.getenv("CAMERA_CONTROL_EXPOSURE", "5000"))
    command_rate_limit_s: float = float(os.getenv("COMMAND_RATE_LIMIT_S", "0.4"))
    approach_timeout_s: float = float(os.getenv("APPROACH_TIMEOUT_S", "10.0"))
    vision_enabled: bool = os.getenv("VISION_ENABLED", "false").lower() == "true"
    vision_model: str = os.getenv("VISION_MODEL", "moondream")
    ollama_url: str = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    vision_request_timeout_s: float = float(os.getenv("VISION_REQUEST_TIMEOUT_S", "300.0"))
    vision_image_max_width: int = int(os.getenv("VISION_IMAGE_MAX_WIDTH", "640"))
    vision_jpeg_quality: int = int(os.getenv("VISION_JPEG_QUALITY", "85"))
    vision_center_crop_enabled: bool = os.getenv("VISION_CENTER_CROP_ENABLED", "false").lower() == "true"
    vision_center_crop_fraction: float = float(os.getenv("VISION_CENTER_CROP_FRACTION", "1.0"))
    vision_prompt_mode: str = os.getenv("VISION_PROMPT_MODE", "blue_snake")
    vision_min_interval_s: float = float(os.getenv("VISION_MIN_INTERVAL_S", "5.0"))
    vision_busy_skip_enabled: bool = os.getenv("VISION_BUSY_SKIP_ENABLED", "true").lower() == "true"
    vision_debug_image_path: str = os.getenv("VISION_DEBUG_IMAGE_PATH", "logs/latest_vision_frame.jpg")
    vision_enhance_enabled: bool = os.getenv("VISION_ENHANCE_ENABLED", "true").lower() == "true"
    vision_enhance_alpha: float = float(os.getenv("VISION_ENHANCE_ALPHA", "1.4"))
    vision_enhance_beta: int = int(os.getenv("VISION_ENHANCE_BETA", "20"))
    vision_use_clahe: bool = os.getenv("VISION_USE_CLAHE", "false").lower() == "true"
    auto_vision_enabled: bool = os.getenv("AUTO_VISION_ENABLED", "false").lower() == "true"
    auto_vision_interval_s: float = float(os.getenv("AUTO_VISION_INTERVAL_S", "5.0"))
    bark_on_blue_snake: bool = os.getenv("BARK_ON_BLUE_SNAKE", "true").lower() == "true"
    bark_cooldown_s: float = float(os.getenv("BARK_COOLDOWN_S", "15.0"))
    audio_in_enabled: bool = os.getenv("AUDIO_IN_ENABLED", "false").lower() == "true"
    audio_in_backend: str = os.getenv("AUDIO_IN_BACKEND", "faster_whisper")
    audio_device: str = os.getenv("AUDIO_DEVICE", os.getenv("AUDIO_INPUT_DEVICE", "auto"))
    audio_device_match: str = os.getenv("AUDIO_DEVICE_MATCH", "")
    audio_sample_rate: int = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
    whisper_model: str = os.getenv("WHISPER_MODEL", "base.en")
    whisper_language: str = os.getenv("WHISPER_LANGUAGE", "en")
    whisper_device: str = os.getenv("WHISPER_DEVICE", "cpu")
    whisper_compute_type: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
    whisper_chunk_s: float = float(os.getenv("WHISPER_CHUNK_S", "2.0"))
    whisper_beam_size: int = int(os.getenv("WHISPER_BEAM_SIZE", "1"))
    whisper_vad_filter: bool = os.getenv("WHISPER_VAD_FILTER", "true").lower() == "true"
    whisper_condition_on_previous_text: bool = os.getenv("WHISPER_CONDITION_ON_PREVIOUS_TEXT", "false").lower() == "true"
    whisper_temperature: float = float(os.getenv("WHISPER_TEMPERATURE", "0.0"))
    audio_min_rms: float = float(os.getenv("AUDIO_MIN_RMS", "0.004"))
    audio_activity_hold_s: float = float(os.getenv("AUDIO_ACTIVITY_HOLD_S", "4.0"))
    audio_speech_rms_threshold: float = float(os.getenv("AUDIO_SPEECH_RMS_THRESHOLD", "0.015"))
    audio_speech_peak_threshold: float = float(os.getenv("AUDIO_SPEECH_PEAK_THRESHOLD", "0.08"))
    audio_speech_queue_max: int = int(os.getenv("AUDIO_SPEECH_QUEUE_MAX", "2"))
    audio_inference_wait_timeout_s: float = float(os.getenv("AUDIO_INFERENCE_WAIT_TIMEOUT_S", "10.0"))
    audio_debug_logs: bool = os.getenv("AUDIO_DEBUG_LOGS", "false").lower() == "true"
    whisper_hotwords: str = os.getenv(
        "WHISPER_HOTWORDS",
        "stop, spot stop, spot sit, spot stand up, spot go, spot forward, spot back, spot left, spot right, spot come",
    )
    whisper_initial_prompt: str = os.getenv(
        "WHISPER_INITIAL_PROMPT",
        "Short English robot commands. Say stop alone for emergency stop. Otherwise commands start with Spot: spot sit, spot stand up, spot go, spot forward, spot back, spot left, spot right, spot come.",
    )
    log_path: str = os.getenv("LOG_PATH", "logs/events.jsonl")
    audio_out_player: str = os.getenv("AUDIO_OUT_PLAYER", "paplay")
    audio_out_device: str = os.getenv("AUDIO_OUT_DEVICE", "")


config = Config()
