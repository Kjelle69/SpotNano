import app.command_manager as command_manager
from app.command_manager import CommandManager
from app.spot_interface import FakeSpotInterface
from app.state import SharedState


def make_manager(monkeypatch=None, feedback=None):
    state = SharedState()
    spot = FakeSpotInterface(state)
    if monkeypatch is not None:
        feedback = feedback if feedback is not None else []
        monkeypatch.setattr(command_manager.audio_out, "bark_ok", lambda: feedback.append("ok") or True)
        monkeypatch.setattr(command_manager.audio_out, "bark_no", lambda: feedback.append("no") or True)
        monkeypatch.setattr(command_manager.audio_out, "bark_warn", lambda: feedback.append("warn") or True)
    return state, CommandManager(state, spot)


def test_rejects_unknown_command(monkeypatch):
    _, manager = make_manager(monkeypatch)
    result = manager.handle("DANCE")
    assert not result.accepted
    assert result.status == "rejected"


def test_stop_blocks_motion_until_reset(monkeypatch):
    _, manager = make_manager(monkeypatch)
    stop = manager.handle("STOP")
    assert stop.accepted
    assert stop.command == "APP_ESTOP"

    blocked = manager.handle("MOVE_FORWARD_SHORT")
    assert not blocked.accepted
    assert blocked.status == "blocked"

    reset = manager.reset_stop()
    assert reset.accepted


def test_stopp_still_blocks_movement_commands(monkeypatch):
    _, manager = make_manager(monkeypatch)
    stop = manager.handle("STOP", source="voice")
    assert stop.accepted

    blocked = manager.handle("ROTATE_LEFT_SHORT")
    assert not blocked.accepted
    assert blocked.status == "blocked"


def test_motion_stop_does_not_latch_and_allows_sit(monkeypatch):
    state, manager = make_manager(monkeypatch)
    stop = manager.handle("MOTION_STOP", source="voice")

    assert stop.accepted
    assert stop.command == "MOTION_STOP"
    assert not state.snapshot()["emergency_stop"]
    assert state.snapshot()["stop_state"] == "motion_stop"

    sit = manager.handle("SIT")
    assert sit.accepted


def test_app_estop_blocks_sit_until_reset(monkeypatch):
    state, manager = make_manager(monkeypatch)
    stop = manager.handle("APP_ESTOP", source="voice")

    assert stop.accepted
    assert state.snapshot()["emergency_stop"]
    assert state.snapshot()["stop_state"] == "app_estop"

    blocked = manager.handle("SIT")
    assert not blocked.accepted
    assert blocked.status == "blocked"

    manager.reset_stop()
    sit = manager.handle("SIT")
    assert sit.accepted


def test_approach_requires_stable_blue_snake(monkeypatch):
    _, manager = make_manager(monkeypatch)
    result = manager.handle("APPROACH_BLUE_SNAKE")
    assert not result.accepted
    assert result.status == "blocked"


def test_command_accepted_triggers_bark_ok(monkeypatch):
    feedback = []
    _, manager = make_manager(monkeypatch, feedback)

    result = manager.handle("SIT")

    assert result.accepted
    assert feedback == ["ok"]


def test_power_off_goes_through_command_manager(monkeypatch):
    feedback = []
    state, manager = make_manager(monkeypatch, feedback)

    result = manager.handle("POWER_OFF")

    assert result.accepted
    assert state.snapshot()["spot_last_action"] == "POWER_OFF"
    assert feedback == ["ok"]


def test_power_off_is_allowed_after_app_estop_for_safe_shutdown(monkeypatch):
    _, manager = make_manager(monkeypatch)
    manager.handle("APP_ESTOP")

    result = manager.handle("POWER_OFF")

    assert result.accepted
    assert result.command == "POWER_OFF"


def test_command_blocked_triggers_bark_no(monkeypatch):
    feedback = []
    _, manager = make_manager(monkeypatch, feedback)

    manager.handle("STOP")
    feedback.clear()
    result = manager.handle("SIT")

    assert not result.accepted
    assert result.status == "blocked"
    assert feedback == ["no"]


def test_stop_triggers_bark_warn(monkeypatch):
    feedback = []
    _, manager = make_manager(monkeypatch, feedback)

    result = manager.handle("STOP")

    assert result.accepted
    assert feedback == ["warn"]
