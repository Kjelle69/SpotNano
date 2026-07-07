from types import SimpleNamespace

import numpy as np

import app.vision_moondream as vision_moondream
from app.vision_moondream import VisionCancelled, VisionService, parse_blue_snake_response
from app.inference_gate import clear_audio_activity, clear_cancel_vision


def test_vision_parse_yes():
    result = parse_blue_snake_response("BLUE_SNAKE: YES")
    assert result.visible
    assert result.stable
    assert not result.uncertain


def test_vision_parse_mixed_case_yes():
    result = parse_blue_snake_response("BLUE_SNAKE: Yes")
    assert result.visible
    assert result.stable
    assert not result.uncertain


def test_vision_parse_plain_yes():
    result = parse_blue_snake_response("YES")
    assert result.visible
    assert result.stable
    assert not result.uncertain


def test_vision_parse_no():
    result = parse_blue_snake_response("BLUE_SNAKE: NO")
    assert not result.visible
    assert not result.stable
    assert not result.uncertain


def test_vision_parse_plain_no():
    result = parse_blue_snake_response("NO")
    assert not result.visible
    assert not result.stable
    assert not result.uncertain


def test_vision_unknown_output_becomes_false_uncertain():
    result = parse_blue_snake_response("maybe there is something blue")
    assert not result.visible
    assert not result.stable
    assert result.uncertain


def test_vision_empty_output_becomes_false_uncertain():
    result = parse_blue_snake_response("")
    assert not result.visible
    assert not result.stable
    assert result.uncertain


def test_ask_moondream_retries_once_on_empty_content(monkeypatch, tmp_path):
    clear_audio_activity()
    clear_cancel_vision()
    calls = []

    class FakeResponse:
        status_code = 200
        text = "ok"

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def fake_post(url, json, timeout):
        calls.append(json)
        if len(calls) == 1:
            return FakeResponse({"message": {"content": ""}, "done": True})
        return FakeResponse({"message": {"content": "YES"}, "done": True})

    monkeypatch.setattr(vision_moondream.requests, "post", fake_post)
    monkeypatch.setattr(
        vision_moondream,
        "config",
        SimpleNamespace(
            vision_model="moondream",
            ollama_url="http://localhost:11434",
            vision_request_timeout_s=300.0,
            vision_jpeg_quality=85,
            vision_debug_image_path=str(tmp_path / "latest_vision_frame.jpg"),
            vision_enhance_enabled=True,
            vision_enhance_alpha=1.4,
            vision_enhance_beta=20,
            vision_use_clahe=False,
        ),
    )

    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    service = VisionService(camera=None)
    assert service._ask_moondream(frame) == "YES"
    assert len(calls) == 2
    assert "num_predict" in calls[0]["options"]
    assert calls[0]["options"]["num_predict"] == 30
    assert "Answer YES or NO" in calls[1]["messages"][0]["content"]
    assert (tmp_path / "latest_vision_frame.jpg").exists()


def test_analyze_once_no_frame_does_not_overwrite_vision_state(monkeypatch):
    class EmptyCamera:
        def latest_frame(self):
            return None

    monkeypatch.setattr(
        vision_moondream,
        "config",
        SimpleNamespace(vision_enabled=True),
    )
    service = VisionService(EmptyCamera())
    before = vision_moondream.shared_state.snapshot()["last_vision_raw"]
    result = service.analyze_once()
    after = vision_moondream.shared_state.snapshot()["last_vision_raw"]
    assert result["status"] == "no_frame"
    assert after == before


def test_vision_response_ignored_if_cancel_requested(monkeypatch):
    monkeypatch.setattr(vision_moondream, "should_cancel_vision", lambda: True)
    monkeypatch.setattr(vision_moondream, "get_vision_cancel_reason", lambda: "audio_activity")

    service = VisionService(camera=None)

    try:
        service._post_moondream("abc", "prompt")
    except VisionCancelled as exc:
        assert str(exc) == "audio_activity"
    else:
        raise AssertionError("expected VisionCancelled")
