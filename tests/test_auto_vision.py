from types import SimpleNamespace

import app.auto_vision as auto_vision
from app.auto_vision import AutoVisionService
from app.state import SharedState, SystemMode


class FakeVisionService:
    after_analysis = None


def make_service(monkeypatch):
    state = SharedState()
    service = AutoVisionService(state, FakeVisionService())
    monkeypatch.setattr(
        auto_vision,
        "config",
        SimpleNamespace(
            auto_vision_enabled=False,
            vision_enabled=True,
            auto_vision_interval_s=5.0,
            bark_on_blue_snake=True,
            bark_cooldown_s=15.0,
        ),
    )
    return state, service


def test_bark_on_stable_transition_respects_cooldown(monkeypatch):
    state, service = make_service(monkeypatch)
    barks = []
    times = [100.0, 105.0, 105.0]

    monkeypatch.setattr(auto_vision.audio_out, "bark_snake", lambda: barks.append("snake") or True)
    monkeypatch.setattr(auto_vision.time, "time", lambda: times.pop(0) if times else 105.0)

    assert service._handle_bark_transition(True)
    assert not service._handle_bark_transition(False)
    assert not service._handle_bark_transition(True)
    assert barks == ["snake"]
    assert state.snapshot()["last_audio_phrase"] == "bark: blue snake detected"


def test_bark_on_stable_transition_does_not_repeat_while_stable(monkeypatch):
    _, service = make_service(monkeypatch)
    barks = []

    monkeypatch.setattr(auto_vision.audio_out, "bark_snake", lambda: barks.append("snake") or True)
    monkeypatch.setattr(auto_vision.time, "time", lambda: 100.0)

    assert service._handle_bark_transition(True)
    assert not service._handle_bark_transition(True)
    assert barks == ["snake"]


def test_post_analysis_sets_blue_snake_detected_and_returns_idle(monkeypatch):
    state, service = make_service(monkeypatch)
    monkeypatch.setattr(auto_vision.audio_out, "bark_snake", lambda: True)

    state.update(blue_snake_stable=True)
    service.handle_post_analysis()
    assert state.get_mode() == SystemMode.BLUE_SNAKE_DETECTED

    state.update(blue_snake_stable=False)
    service.handle_post_analysis()
    assert state.get_mode() == SystemMode.IDLE


def test_post_analysis_does_not_leave_stopped_state(monkeypatch):
    state, service = make_service(monkeypatch)

    state.update(emergency_stop=True, blue_snake_stable=True)
    state.set_mode(SystemMode.STOPPED)
    service.handle_post_analysis()
    assert state.get_mode() == SystemMode.STOPPED


def test_auto_vision_skips_when_audio_activity_active(monkeypatch):
    state, service = make_service(monkeypatch)
    calls = []
    monkeypatch.setattr(auto_vision, "is_audio_activity_active", lambda: True)
    service.vision_service.analyze_once = lambda source="auto": calls.append(source)

    service._analyze_if_idle()

    assert calls == []
    assert state.snapshot()["last_auto_vision_skip_reason"] == "audio_active"
