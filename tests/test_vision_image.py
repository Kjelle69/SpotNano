import numpy as np
from types import SimpleNamespace

import app.vision_moondream as vision_moondream


def test_prepare_frame_for_vision_preserves_aspect_ratio(monkeypatch):
    monkeypatch.setattr(
        vision_moondream,
        "config",
        SimpleNamespace(vision_image_max_width=320, vision_center_crop_enabled=False),
    )

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    resized = vision_moondream.prepare_frame_for_vision(frame)

    assert resized.shape[1] == 320
    assert resized.shape[0] == 240


def test_prepare_frame_for_vision_preserves_640_max_width(monkeypatch):
    monkeypatch.setattr(
        vision_moondream,
        "config",
        SimpleNamespace(vision_image_max_width=640, vision_center_crop_enabled=False),
    )

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    resized = vision_moondream.prepare_frame_for_vision(frame)

    assert resized.shape == frame.shape


def test_prepare_frame_for_vision_does_not_upscale(monkeypatch):
    monkeypatch.setattr(
        vision_moondream,
        "config",
        SimpleNamespace(vision_image_max_width=320, vision_center_crop_enabled=False),
    )

    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    resized = vision_moondream.prepare_frame_for_vision(frame)

    assert resized.shape == frame.shape


def test_vision_quality_warning_for_320_width(monkeypatch):
    events = []
    monkeypatch.setattr(
        vision_moondream.event_logger,
        "event",
        lambda event_type, **payload: events.append((event_type, payload)),
    )

    vision_moondream.log_vision_image_prepared((480, 640), (240, 320), 10_000, 85)

    assert any(event_type == "vision_quality_warning" for event_type, _ in events)
