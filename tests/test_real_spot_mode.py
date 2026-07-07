from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.command_manager as command_manager
import app.spot_interface as spot_interface
from app.command_manager import CommandManager
from app.main import app
from app.spot_interface import FakeSpotInterface, RealSpotInterface, SpotCommandError
from app.state import SharedState


class RealTestSpot:
    is_real = True

    def __init__(self):
        self.calls = []

    def sit(self):
        self.calls.append("SIT")
        return "REAL SPOT: SIT"

    def stand(self):
        self.calls.append("STAND")
        return "REAL SPOT: STAND"

    def stop(self):
        self.calls.append("STOP")
        return "REAL SPOT: STOP"


def real_config():
    return SimpleNamespace(spot_real_allowed_commands="SIT,STAND,STOP", command_rate_limit_s=0.4)


def test_fake_mode_does_not_require_bosdyn_sdk():
    state = SharedState()
    fake = FakeSpotInterface(state)

    assert fake.sit() == "FAKE SPOT: SIT"
    assert state.snapshot()["spot_mode"] == "fake"


def test_real_mode_missing_config_sets_unavailable(monkeypatch):
    state = SharedState()
    monkeypatch.setattr(
        spot_interface,
        "config",
        SimpleNamespace(spot_host="", spot_username="", spot_password=""),
    )

    real = RealSpotInterface(state)
    status = real.status()

    assert not status["spot_real_available"]
    assert not status["spot_connected"]
    assert "Missing Spot config" in status["spot_last_error"]


def test_real_mode_missing_sdk_does_not_crash(monkeypatch):
    state = SharedState()
    monkeypatch.setattr(
        spot_interface,
        "config",
        SimpleNamespace(
            spot_host="192.0.2.10",
            spot_username="user",
            spot_password="secret",
            spot_sdk_client_name="test",
        ),
    )

    real = RealSpotInterface(state)
    status = real.connect()

    assert not status["spot_real_available"]
    assert not status["spot_connected"]
    assert "bosdyn SDK missing" in status["spot_last_error"]


def test_command_manager_real_mode_allows_sit_stand_stop(monkeypatch):
    state = SharedState()
    spot = RealTestSpot()
    monkeypatch.setattr(command_manager, "config", real_config())
    monkeypatch.setattr(command_manager.audio_out, "bark_ok", lambda: True)
    monkeypatch.setattr(command_manager.audio_out, "bark_warn", lambda: True)
    manager = CommandManager(state, spot)

    assert manager.handle("SIT").accepted
    assert manager.handle("STAND").accepted
    assert manager.handle("STOP").accepted
    assert spot.calls == ["SIT", "STAND", "STOP"]


def test_command_manager_real_mode_blocks_movement_and_approach(monkeypatch):
    state = SharedState()
    spot = RealTestSpot()
    monkeypatch.setattr(command_manager, "config", real_config())
    monkeypatch.setattr(command_manager.audio_out, "bark_no", lambda: True)
    manager = CommandManager(state, spot)

    for command in [
        "MOVE_FORWARD_SHORT",
        "MOVE_BACKWARD_SHORT",
        "ROTATE_LEFT_SHORT",
        "ROTATE_RIGHT_SHORT",
        "APPROACH_BLUE_SNAKE",
        "BARK",
    ]:
        result = manager.handle(command)
        assert not result.accepted
        assert result.status == "blocked"
        assert "not enabled" in result.message

    assert spot.calls == []


def test_stop_accepted_even_when_real_spot_stop_fails(monkeypatch):
    class FailingStopSpot(RealTestSpot):
        def stop(self):
            raise SpotCommandError("not connected")

    state = SharedState()
    monkeypatch.setattr(command_manager, "config", real_config())
    monkeypatch.setattr(command_manager.audio_out, "bark_warn", lambda: True)
    manager = CommandManager(state, FailingStopSpot())
    manager.handle("STOP")

    result = manager.handle("STOP")

    assert result.accepted
    assert result.command == "STOP"
    assert state.snapshot()["emergency_stop"]


def test_status_does_not_expose_spot_password():
    client = TestClient(app)
    status = client.get("/api/status").json()

    assert "spot_password" not in status
    assert "SPOT_PASSWORD" not in str(status)


def test_real_spot_script_requires_explicit_credentials():
    script = open("scripts/start_spot_real_sitstand_test.sh", encoding="utf-8").read()

    assert "SPOT_HOST" in script
    assert "SPOT_USERNAME" in script
    assert "SPOT_PASSWORD" in script
    assert "SPOT_MODE=real" in script
    assert "AUDIO_IN_ENABLED" in script
