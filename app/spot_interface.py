from __future__ import annotations

import time
from typing import Any

from app.config import config
from app.logger import event_logger
from app.state import SharedState


class SpotCommandError(RuntimeError):
    pass


class FakeSpotInterface:
    is_real = False

    def __init__(self, state: SharedState) -> None:
        self.state = state
        self.state.update(
            fake_spot_mode=True,
            spot_mode="fake",
            spot_real_available=False,
            spot_connected=False,
            spot_host="",
            spot_last_error="",
        )

    def _fake(self, action: str) -> str:
        message = f"FAKE SPOT: {action}"
        self.state.append_command_log(message)
        self.state.update(spot_last_action=action, spot_last_action_status="fake")
        event_logger.event("fake_spot_action", action=action)
        return message

    def sit(self) -> str:
        return self._fake("SIT")

    def stand(self) -> str:
        return self._fake("STAND")

    def stop(self) -> str:
        return self._fake("STOP")

    def move_forward_short(self) -> str:
        return self._fake("MOVE_FORWARD_SHORT")

    def move_backward_short(self) -> str:
        return self._fake("MOVE_BACKWARD_SHORT")

    def rotate_left_short(self) -> str:
        return self._fake("ROTATE_LEFT_SHORT")

    def rotate_right_short(self) -> str:
        return self._fake("ROTATE_RIGHT_SHORT")

    def bark(self) -> str:
        return self._fake("BARK")

    def approach_blue_snake_step(self) -> str:
        return self._fake("APPROACH_BLUE_SNAKE_STEP")

    def status(self) -> dict[str, Any]:
        return {
            "spot_mode": "fake",
            "spot_real_available": False,
            "spot_connected": False,
            "spot_host": "",
            "spot_last_error": "",
            "spot_last_action": self.state.snapshot().get("spot_last_action", ""),
            "spot_last_action_status": self.state.snapshot().get("spot_last_action_status", ""),
            "spot_powered_on": None,
            "spot_estopped": None,
            "spot_lease_status": "",
        }

    def close(self) -> None:
        return None


class RealSpotInterface:
    is_real = True

    def __init__(self, state: SharedState) -> None:
        self.state = state
        self._sdk = None
        self._robot = None
        self._command_client = None
        self._state_client = None
        self._lease_client = None
        self._lease_keepalive = None
        self._connected = False
        self._available = False
        self._last_error = ""
        self._last_action = ""
        self._last_action_status = ""
        self._lease_status = ""
        self._powered_on: bool | None = None
        self._estopped: bool | None = None
        self.state.update(
            fake_spot_mode=False,
            spot_mode="real",
            spot_real_available=False,
            spot_connected=False,
            spot_host=config.spot_host,
        )
        self._check_config()

    def _check_config(self) -> bool:
        missing = []
        if not config.spot_host:
            missing.append("SPOT_HOST")
        if not config.spot_username:
            missing.append("SPOT_USERNAME")
        if not config.spot_password:
            missing.append("SPOT_PASSWORD")
        if missing:
            self._set_error(f"Missing Spot config: {', '.join(missing)}")
            event_logger.event("spot_real_config_missing", missing=missing)
            return False
        return True

    def connect(self) -> dict[str, Any]:
        if not self._check_config():
            return self.status()

        try:
            import bosdyn.client
            from bosdyn.client.lease import LeaseClient, LeaseKeepAlive
            from bosdyn.client.robot_command import RobotCommandClient
            from bosdyn.client.robot_state import RobotStateClient
        except ImportError as exc:
            self._set_error(f"bosdyn SDK missing: {exc}")
            event_logger.event("spot_sdk_missing", error=str(exc))
            return self.status()

        try:
            self._sdk = bosdyn.client.create_standard_sdk(config.spot_sdk_client_name)
            self._robot = self._sdk.create_robot(config.spot_host)
            self._robot.authenticate(config.spot_username, config.spot_password)
            if hasattr(self._robot, "time_sync"):
                self._robot.time_sync.wait_for_sync()
            self._command_client = self._robot.ensure_client(RobotCommandClient.default_service_name)
            self._state_client = self._robot.ensure_client(RobotStateClient.default_service_name)
            self._lease_client = self._robot.ensure_client(LeaseClient.default_service_name)
            lease = self._lease_client.take()
            self._lease_keepalive = LeaseKeepAlive(self._lease_client, must_acquire=True, return_at_exit=True)
            self._lease_status = f"acquired:{getattr(lease, 'lease_proto', 'lease')}"
            self._connected = True
            self._available = True
            self._last_error = ""
            self._update_robot_state()
            event_logger.event("spot_real_connected", host=config.spot_host, lease_status=self._lease_status)
        except Exception as exc:
            self._connected = False
            self._available = False
            self._set_error(str(exc))
            event_logger.event("spot_real_connect_failed", host=config.spot_host, error=str(exc))
        self._sync_state()
        return self.status()

    def ensure_connected(self) -> bool:
        if self._connected and self._command_client is not None:
            return True
        self.connect()
        return self._connected and self._command_client is not None

    def sit(self) -> str:
        return self._run_robot_command("SIT", self._sit_command)

    def stand(self) -> str:
        if not self.ensure_connected():
            raise SpotCommandError(self._last_error or "Real Spot unavailable")
        self._update_robot_state()
        if self._powered_on is False:
            if not config.spot_enable_power_on:
                raise SpotCommandError("Robot not powered. Enable SPOT_ENABLE_POWER_ON or power on from tablet.")
            self._power_on()
        return self._run_robot_command("STAND", self._stand_command, already_connected=True)

    def stop(self) -> str:
        return self._run_robot_command("STOP", self._stop_command)

    def status(self) -> dict[str, Any]:
        self._sync_state()
        return {
            "spot_mode": "real",
            "spot_real_available": self._available,
            "spot_connected": self._connected,
            "spot_host": config.spot_host,
            "spot_last_error": self._last_error,
            "spot_last_action": self._last_action,
            "spot_last_action_status": self._last_action_status,
            "spot_powered_on": self._powered_on,
            "spot_estopped": self._estopped,
            "spot_lease_status": self._lease_status,
        }

    def close(self) -> None:
        try:
            if self._lease_keepalive is not None:
                self._lease_keepalive.shutdown()
        except Exception as exc:
            event_logger.event("spot_real_close_error", error=str(exc))
        self._lease_keepalive = None
        self._connected = False
        self._sync_state()

    def _run_robot_command(self, action: str, builder, already_connected: bool = False) -> str:
        if not already_connected and not self.ensure_connected():
            raise SpotCommandError(self._last_error or "Real Spot unavailable")
        try:
            command = builder()
            self._command_client.robot_command(command=command)
            self._last_action = action
            self._last_action_status = "accepted"
            self._last_error = ""
            self._sync_state()
            event_logger.event("spot_real_action", action=action, status="accepted")
            return f"REAL SPOT: {action}"
        except Exception as exc:
            self._last_action = action
            self._last_action_status = "error"
            self._set_error(str(exc))
            event_logger.event("spot_real_action", action=action, status="error", error=str(exc))
            raise SpotCommandError(str(exc)) from exc

    def _sit_command(self):
        from bosdyn.client.robot_command import RobotCommandBuilder

        return RobotCommandBuilder.synchro_sit_command()

    def _stand_command(self):
        from bosdyn.client.robot_command import RobotCommandBuilder

        return RobotCommandBuilder.synchro_stand_command()

    def _stop_command(self):
        from bosdyn.client.robot_command import RobotCommandBuilder

        return RobotCommandBuilder.stop_command()

    def _power_on(self) -> None:
        if self._robot is None:
            raise SpotCommandError("Robot is not connected")
        event_logger.event("spot_real_power_on_started")
        self._robot.power_on(timeout_sec=config.spot_command_timeout_s)
        started = time.time()
        while time.time() - started < config.spot_command_timeout_s:
            self._update_robot_state()
            if self._powered_on:
                event_logger.event("spot_real_power_on_complete")
                return
            time.sleep(0.25)
        raise SpotCommandError("Timed out waiting for robot power on")

    def _update_robot_state(self) -> None:
        if self._robot is not None and hasattr(self._robot, "is_powered_on"):
            try:
                self._powered_on = bool(self._robot.is_powered_on())
            except Exception:
                self._powered_on = None
        if self._state_client is None:
            return
        try:
            robot_state = self._state_client.get_robot_state()
            estop_states = getattr(getattr(robot_state, "estop_states", None), "estop_states", None)
            if estop_states is not None:
                self._estopped = any("ESTOP" in str(state).upper() for state in estop_states)
        except Exception as exc:
            event_logger.event("spot_real_status_error", error=str(exc))

    def _set_error(self, error: str) -> None:
        self._last_error = error
        self._available = False
        self._sync_state()

    def _sync_state(self) -> None:
        self.state.update(
            fake_spot_mode=False,
            spot_mode="real",
            spot_real_available=self._available,
            spot_connected=self._connected,
            spot_host=config.spot_host,
            spot_last_error=self._last_error,
            spot_last_action=self._last_action,
            spot_last_action_status=self._last_action_status,
            spot_powered_on=self._powered_on,
            spot_estopped=self._estopped,
            spot_lease_status=self._lease_status,
        )


def create_spot_interface(state: SharedState):
    if config.spot_mode == "real":
        return RealSpotInterface(state)
    return FakeSpotInterface(state)
