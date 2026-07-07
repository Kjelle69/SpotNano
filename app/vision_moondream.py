import time
from dataclasses import dataclass
import base64
from pathlib import Path
import re

import requests

from app.config import config
from app.inference_gate import (
    acquire_inference,
    clear_cancel_vision,
    get_vision_cancel_reason,
    should_cancel_vision,
)
from app.logger import event_logger
from app.state import shared_state

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


VISION_PROMPT = """
Look at the image.

Is there a clearly visible blue or turquoise toy snake or blue dog toy shaped like a snake?

The object counts as a blue snake if it is:
- blue or turquoise
- toy-like
- long, curved, rope-like or snake-shaped

Answer exactly one of these two lines:

BLUE_SNAKE: YES
BLUE_SNAKE: NO

Do not explain.
"""

VISION_RETRY_PROMPT = "Is there a blue toy snake visible? Answer YES or NO."


class VisionCancelled(RuntimeError):
    pass


def _content_to_flag_text(text: str) -> str:
    return re.sub(r"[^A-Z_:]+", " ", text.strip().upper()).strip()


def _single_word_response(text: str) -> str:
    return re.sub(r"[^A-Z]+", "", text.strip().upper())


def _ollama_chat_url() -> str:
    base = config.ollama_url.rstrip("/")
    if base.endswith("/api/chat"):
        return base
    return f"{base}/api/chat"


@dataclass(frozen=True)
class VisionParseResult:
    visible: bool
    stable: bool
    uncertain: bool


def parse_blue_snake_response(raw_response: str) -> VisionParseResult:
    normalized = _content_to_flag_text(raw_response)
    single_word = _single_word_response(raw_response)
    if "BLUE_SNAKE: YES" in normalized or "BLUE_SNAKE YES" in normalized:
        return VisionParseResult(visible=True, stable=True, uncertain=False)
    if "BLUE_SNAKE: NO" in normalized or "BLUE_SNAKE NO" in normalized:
        return VisionParseResult(visible=False, stable=False, uncertain=False)
    if single_word == "YES":
        return VisionParseResult(visible=True, stable=True, uncertain=False)
    if single_word == "NO":
        return VisionParseResult(visible=False, stable=False, uncertain=False)
    return VisionParseResult(visible=False, stable=False, uncertain=True)


def update_blue_snake_detection(raw_response: str, duration_s: float | None = None) -> bool:
    result = parse_blue_snake_response(raw_response)
    shared_state.update(
        blue_snake_visible=result.visible,
        blue_snake_stable=result.stable,
        last_vision_raw=raw_response,
        last_vision_time=time.time(),
        last_vision_duration_s=duration_s,
    )
    if result.uncertain:
        event_logger.event("vision_parse_failure", raw=raw_response, duration_s=duration_s)
    event_logger.event(
        "vision_result",
        visible=result.visible,
        stable=result.stable,
        uncertain=result.uncertain,
        raw=raw_response,
        duration_s=duration_s,
    )
    return result.visible


class VisionService:
    def __init__(self, camera) -> None:
        self.camera = camera
        self.after_analysis = None

    def analyze_once(self, source: str = "manual") -> dict:
        event_logger.event("vision_analyze_started", enabled=config.vision_enabled, source=source)
        if not config.vision_enabled:
            return self._disabled_result()
        clear_cancel_vision()
        timeout = 1.0 if source == "manual" else 0.0
        with acquire_inference("vision_moondream", priority="low" if source == "auto" else "normal", timeout=timeout) as acquired:
            if not acquired:
                return {
                    "accepted": False,
                    "status": "busy",
                    "message": "Inference is busy",
                    "state": shared_state.snapshot(),
                }
            return self._analyze_once_locked(source)

    def _analyze_once_locked(self, source: str = "manual") -> dict:
        frame = self.camera.latest_frame()
        if frame is None:
            event_logger.event("vision_no_frame", source=source)
            return {
                "accepted": False,
                "status": "no_frame",
                "message": "No camera frame is available",
                "state": shared_state.snapshot(),
            }
        if cv2 is None:
            event_logger.event("vision_parse_failure", raw="", error="opencv is not installed")
            return {
                "accepted": False,
                "status": "opencv_missing",
                "message": "OpenCV is not installed",
                "state": shared_state.snapshot(),
            }

        start = time.time()
        try:
            raw_response = self._ask_moondream(frame)
        except VisionCancelled as exc:
            duration_s = time.time() - start
            reason = str(exc) or get_vision_cancel_reason() or "audio_activity"
            shared_state.update(last_vision_cancel_reason=reason)
            event_logger.event("vision_cancelled_audio_activity", reason=reason, duration_s=duration_s)
            return {
                "accepted": False,
                "status": "cancelled",
                "message": "Vision cancelled because audio activity has priority",
                "reason": reason,
                "state": shared_state.snapshot(),
            }
        except Exception as exc:
            duration_s = time.time() - start
            event_logger.event("vision_parse_failure", raw="", error=str(exc), duration_s=duration_s)
            update_blue_snake_detection("", duration_s=duration_s)
            return {
                "accepted": False,
                "status": "vision_error",
                "message": str(exc),
                "state": shared_state.snapshot(),
            }
        duration_s = time.time() - start
        visible = update_blue_snake_detection(raw_response, duration_s=duration_s)
        if self.after_analysis is not None:
            self.after_analysis(source=source)
        return {
            "accepted": True,
            "status": "analyzed",
            "source": source,
            "visible": visible,
            "raw": raw_response,
            "duration_s": duration_s,
            "state": shared_state.snapshot(),
        }

    def _disabled_result(self) -> dict:
        return {
            "accepted": False,
            "status": "disabled",
            "message": "Vision is disabled. Set VISION_ENABLED=true to use Ollama/Moondream.",
            "state": shared_state.snapshot(),
        }

    def _ask_moondream(self, frame) -> str:
        image_b64 = self._encode_frame_to_debug_jpeg(frame)
        data = self._post_moondream(image_b64, VISION_PROMPT)
        content = self._message_content(data)
        if content:
            return content

        event_logger.event("vision_empty_response", ollama_response=data)
        retry_data = self._post_moondream(image_b64, VISION_RETRY_PROMPT)
        retry_content = self._message_content(retry_data)
        if not retry_content:
            event_logger.event("vision_empty_response", ollama_response=retry_data, retry=True)
        return retry_content

    def _post_moondream(self, image_b64: str, prompt: str) -> dict:
        if should_cancel_vision():
            reason = get_vision_cancel_reason() or "audio_activity"
            event_logger.event("vision_cancelled_audio_activity", reason=reason, before_request=True)
            raise VisionCancelled(reason)
        payload = {
            "model": config.vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],
                }
            ],
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": 30,
            },
        }
        response = requests.post(
            _ollama_chat_url(),
            json=payload,
            timeout=config.vision_request_timeout_s,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Ollama error {response.status_code}: {response.text}")
        data = response.json()
        if should_cancel_vision():
            reason = get_vision_cancel_reason() or "audio_activity"
            event_logger.event("vision_response_ignored_due_to_audio", reason=reason)
            raise VisionCancelled(reason)
        return data

    def _message_content(self, data: dict) -> str:
        return str(data.get("message", {}).get("content", "")).strip()

    def _encode_frame_to_debug_jpeg(self, frame) -> str:
        original_shape = tuple(frame.shape[:2])
        frame = prepare_frame_for_vision(frame)
        sent_shape = tuple(frame.shape[:2])
        frame = self._enhance_frame_for_vision(frame)
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), config.vision_jpeg_quality],
        )
        if not ok:
            raise RuntimeError("Could not encode frame for vision")
        jpg_bytes = encoded.tobytes()
        path = Path(config.vision_debug_image_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(jpg_bytes)
        log_vision_image_prepared(original_shape, sent_shape, len(jpg_bytes), config.vision_jpeg_quality)
        return base64.b64encode(jpg_bytes).decode("utf-8")

    def _enhance_frame_for_vision(self, frame):
        if not config.vision_enhance_enabled:
            return frame

        bright = cv2.convertScaleAbs(
            frame,
            alpha=config.vision_enhance_alpha,
            beta=config.vision_enhance_beta,
        )

        if not config.vision_use_clahe:
            return bright

        lab = cv2.cvtColor(bright, cv2.COLOR_BGR2LAB)
        luminance, a_channel, b_channel = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced_luminance = clahe.apply(luminance)
        enhanced_lab = cv2.merge((enhanced_luminance, a_channel, b_channel))
        return cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)


def prepare_frame_for_vision(frame):
    if cv2 is None:
        return frame

    prepared = frame
    if getattr(config, "vision_center_crop_enabled", False):
        prepared = center_crop(prepared, getattr(config, "vision_center_crop_fraction", 1.0))

    height, width = prepared.shape[:2]
    max_width = max(1, int(getattr(config, "vision_image_max_width", 640)))
    if width <= max_width:
        return prepared

    scale = max_width / float(width)
    new_size = (max_width, max(1, int(round(height * scale))))
    return cv2.resize(prepared, new_size, interpolation=cv2.INTER_AREA)


def log_vision_image_prepared(original_shape, sent_shape, jpeg_bytes: int, jpeg_quality: int) -> None:
    event_logger.event(
        "vision_image_prepared",
        original_height=original_shape[0],
        original_width=original_shape[1],
        sent_height=sent_shape[0],
        sent_width=sent_shape[1],
        jpeg_bytes=jpeg_bytes,
        jpeg_quality=jpeg_quality,
    )
    if sent_shape[1] <= 320:
        event_logger.event(
            "vision_quality_warning",
            message="Moondream image may be too small for reliable recognition",
            sent_width=sent_shape[1],
            sent_height=sent_shape[0],
        )


def center_crop(frame, fraction: float):
    height, width = frame.shape[:2]
    safe_fraction = min(1.0, max(0.1, float(fraction)))
    crop_width = max(1, int(width * safe_fraction))
    crop_height = max(1, int(height * safe_fraction))
    x0 = max(0, (width - crop_width) // 2)
    y0 = max(0, (height - crop_height) // 2)
    return frame[y0 : y0 + crop_height, x0 : x0 + crop_width]
