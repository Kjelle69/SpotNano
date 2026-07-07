import threading
import time
from typing import Iterator

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

from app.config import config
from app.logger import event_logger
from app.state import shared_state


class Camera:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest_frame = None
        self._latest_jpeg: bytes | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_error_log_time = 0.0

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        event_logger.event(
            "camera_started",
            index=config.camera_index,
            width=config.camera_width,
            height=config.camera_height,
            fps=config.camera_fps,
            mjpeg_fps=config.mjpeg_fps,
            jpeg_quality=config.camera_jpeg_quality,
            brightness_enabled=config.camera_brightness_enabled,
        )

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def latest_frame(self):
        with self._lock:
            if self._latest_frame is None:
                if self._latest_jpeg is None or cv2 is None:
                    return None
                import numpy as np

                buffer = np.frombuffer(self._latest_jpeg, dtype=np.uint8)
                decoded = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
                if decoded is None:
                    return None
                return decoded
            return self._latest_frame.copy()

    def has_frame(self) -> bool:
        with self._lock:
            return self._latest_frame is not None or self._latest_jpeg is not None

    def latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self._latest_jpeg

    def mjpeg_stream(self) -> Iterator[bytes]:
        delay = 1.0 / max(1.0, float(config.mjpeg_fps))
        while True:
            frame = self.latest_jpeg()
            if frame:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            time.sleep(delay)

    def _capture_loop(self) -> None:
        if cv2 is None:
            event_logger.event("camera_error", error="opencv is not installed")
            return
        capture = cv2.VideoCapture(config.camera_index, cv2.CAP_V4L2)
        if not capture.isOpened():
            event_logger.event("camera_error", error="camera could not be opened", index=config.camera_index)
            self._running = False
            return
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.camera_width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.camera_height)
        capture.set(cv2.CAP_PROP_FPS, config.camera_fps)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, config.camera_buffer_size)
        capture.set(cv2.CAP_PROP_BRIGHTNESS, config.camera_control_brightness)
        capture.set(cv2.CAP_PROP_CONTRAST, config.camera_control_contrast)
        capture.set(cv2.CAP_PROP_SATURATION, config.camera_control_saturation)
        capture.set(cv2.CAP_PROP_GAMMA, config.camera_control_gamma)
        capture.set(cv2.CAP_PROP_EXPOSURE, config.camera_control_exposure)
        event_logger.event(
            "camera_opened",
            index=config.camera_index,
            requested_width=config.camera_width,
            requested_height=config.camera_height,
            requested_fps=config.camera_fps,
            actual_width=capture.get(cv2.CAP_PROP_FRAME_WIDTH),
            actual_height=capture.get(cv2.CAP_PROP_FRAME_HEIGHT),
            actual_fps=capture.get(cv2.CAP_PROP_FPS),
            actual_buffer_size=capture.get(cv2.CAP_PROP_BUFFERSIZE),
        )
        frame_delay = 1.0 / max(1.0, float(config.camera_fps))
        try:
            while self._running:
                started = time.time()
                ok, frame = capture.read()
                if not ok:
                    self._log_camera_error("camera frame read failed")
                    time.sleep(0.2)
                    continue
                frame = self._enhance_brightness(frame)
                ok, encoded = cv2.imencode(
                    ".jpg",
                    frame,
                    [int(cv2.IMWRITE_JPEG_QUALITY), config.camera_jpeg_quality],
                )
                if ok:
                    with self._lock:
                        self._latest_frame = frame.copy()
                        self._latest_jpeg = encoded.tobytes()
                    shared_state.update(last_frame_time=time.time())
                else:
                    self._log_camera_error("jpeg encode failed")
                elapsed = time.time() - started
                if elapsed < frame_delay:
                    time.sleep(frame_delay - elapsed)
        finally:
            capture.release()
            event_logger.event("camera_stopped", index=config.camera_index)

    def _enhance_brightness(self, frame):
        if not config.camera_brightness_enabled:
            return frame
        return cv2.convertScaleAbs(
            frame,
            alpha=config.camera_brightness_alpha,
            beta=config.camera_brightness_beta,
        )

    def _log_camera_error(self, error: str) -> None:
        now = time.time()
        if now - self._last_error_log_time < 5:
            return
        self._last_error_log_time = now
        event_logger.event("camera_error", error=error)


camera = Camera()
