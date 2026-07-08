import builtins
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.command_manager as command_manager
import app.spot_interface as spot_interface
from app.config import Config
from app.command_manager import CommandManager
from app.main import app
from app.spot_interface import FakeSpotInterface, RealSpotInterface, SpotCommandError, _battery_percentage_value
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

    def power_off(self):
        self.calls.append("POWER_OFF")
        return "REAL SPOT: POWER_OFF"

    def rotate_left_short(self):
        self.calls.append("ROTATE_LEFT_SHORT")
        return "REAL SPOT: ROTATE_LEFT_SHORT"

    def rotate_right_short(self):
        self.calls.append("ROTATE_RIGHT_SHORT")
        return "REAL SPOT: ROTATE_RIGHT_SHORT"


def real_config():
    return SimpleNamespace(
        spot_real_allowed_commands="SIT,STAND,POWER_OFF,MOTION_STOP,APP_ESTOP",
        command_rate_limit_s=0.0,
    )


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
        SimpleNamespace(spot_host="spot-rear", spot_username="", spot_password=""),
    )

    real = RealSpotInterface(state)
    status = real.status()

    assert not status["spot_real_available"]
    assert not status["spot_connected"]
    assert "Missing Spot config" in status["spot_last_error"]


def test_default_spot_host_is_spot_rear(monkeypatch):
    monkeypatch.delenv("SPOT_HOST", raising=False)

    assert Config().spot_host == "spot-rear"


def test_spot_host_env_overrides_default(monkeypatch):
    monkeypatch.setenv("SPOT_HOST", "10.0.0.3")

    assert Config().spot_host == "10.0.0.3"


def test_real_mode_missing_sdk_does_not_crash(monkeypatch):
    state = SharedState()

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("bosdyn"):
            raise ImportError("simulated missing bosdyn SDK")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
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
    assert manager.handle("POWER_OFF").accepted
    assert manager.handle("MOTION_STOP").accepted
    assert manager.handle("APP_ESTOP").accepted
    assert spot.calls == ["SIT", "STAND", "POWER_OFF", "STOP", "STOP"]


def test_command_manager_real_mode_blocks_short_rotation_by_default(monkeypatch):
    state = SharedState()
    spot = RealTestSpot()
    monkeypatch.setattr(command_manager, "config", real_config())
    monkeypatch.setattr(command_manager.audio_out, "bark_no", lambda: True)
    manager = CommandManager(state, spot)

    assert not manager.handle("ROTATE_LEFT_SHORT").accepted
    assert not manager.handle("ROTATE_RIGHT_SHORT").accepted
    assert spot.calls == []


def test_command_manager_real_mode_blocks_movement_and_approach(monkeypatch):
    state = SharedState()
    spot = RealTestSpot()
    monkeypatch.setattr(command_manager, "config", real_config())
    monkeypatch.setattr(command_manager.audio_out, "bark_no", lambda: True)
    manager = CommandManager(state, spot)

    for command in [
        "MOVE_FORWARD_SHORT",
        "MOVE_BACKWARD_SHORT",
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
    assert result.command == "APP_ESTOP"
    assert state.snapshot()["emergency_stop"]


def test_real_spot_reconnect_shuts_down_existing_lease_keepalive(monkeypatch):
    state = SharedState()
    monkeypatch.setattr(
        spot_interface,
        "config",
        SimpleNamespace(
            spot_host="spot-rear",
            spot_username="user",
            spot_password="secret",
        ),
    )
    real = RealSpotInterface(state)
    old_keepalive = SimpleNamespace(shutdown_called=False)

    def shutdown():
        old_keepalive.shutdown_called = True

    old_keepalive.shutdown = shutdown
    real._lease_keepalive = old_keepalive

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("bosdyn"):
            raise ImportError("simulated missing bosdyn SDK")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    real.connect()

    assert old_keepalive.shutdown_called
    assert real._lease_keepalive is None


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


def test_real_spot_script_enables_limited_voice_commands():
    script = open("scripts/start_spot_real_sitstand_test.sh", encoding="utf-8").read()

    assert 'AUDIO_IN_ENABLED="${AUDIO_IN_ENABLED:-true}"' in script
    assert 'AUDIO_DEVICE="${AUDIO_DEVICE:-auto}"' in script
    assert 'AUDIO_DEVICE_MATCH="${AUDIO_DEVICE_MATCH:-logitech}"' in script
    assert "AUDIO_SPEECH_RMS_THRESHOLD" in script
    assert "AUDIO_SPEECH_PEAK_THRESHOLD" in script
    assert "spot stop, spot emergency stop, spot sit, spot sit down, spot seat, spot stand, spot stand up" in script
    assert "ROTATE_LEFT_SHORT" not in script
    assert "ROTATE_RIGHT_SHORT" not in script
    assert "AUTO_VISION_ENABLED" in script
    assert "VISION_ENABLED" in script


def test_startup_scripts_do_not_use_old_spot_wifi_host_as_active_default():
    script_text = "\n".join(path.read_text(encoding="utf-8") for path in Path("scripts").glob("*.sh"))

    assert "192.168.80.3" not in script_text
    assert 'SPOT_HOST="${SPOT_HOST:-spot-rear}"' in script_text
    assert "Spot host: $SPOT_HOST" in script_text


def test_battery_percentage_value_accepts_proto_wrappers():
    assert _battery_percentage_value(SimpleNamespace(value=73.5)) == 73.5
    assert _battery_percentage_value(42) == 42.0
    assert _battery_percentage_value(None) is None
