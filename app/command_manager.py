import time
from dataclasses import dataclass

from app import audio_out
from app.config import config
from app.logger import event_logger
from app.spot_interface import FakeSpotInterface, SpotCommandError
from app.state import SharedState, SystemMode


ALLOWED_COMMANDS = {
    "SIT",
    "STAND",
    "STOP",
    "APP_ESTOP",
    "MOTION_STOP",
    "POWER_OFF",
    "MOVE_FORWARD_SHORT",
    "MOVE_BACKWARD_SHORT",
    "ROTATE_LEFT_SHORT",
    "ROTATE_RIGHT_SHORT",
    "BARK",
    "APPROACH_BLUE_SNAKE",
}

MOTION_COMMANDS = {
    "MOVE_FORWARD_SHORT",
    "MOVE_BACKWARD_SHORT",
    "ROTATE_LEFT_SHORT",
    "ROTATE_RIGHT_SHORT",
    "APPROACH_BLUE_SNAKE",
}

REAL_MODE_BLOCKED_MESSAGE = "Real Spot mode: command not enabled in this milestone"


@dataclass
class CommandResult:
    accepted: bool
    command: str
    status: str
    message: str


class CommandManager:
    def __init__(self, state: SharedState, spot: FakeSpotInterface) -> None:
        self.state = state
        self.spot = spot
        self._last_motion_time = 0.0

    def emergency_stop(self, source: str = "unknown") -> CommandResult:
        self.state.update(emergency_stop=True, stop_state="app_estop", last_command="APP_ESTOP", last_command_status="accepted")
        self.state.set_mode(SystemMode.STOPPED)
        try:
            message = self.spot.stop()
        except SpotCommandError as exc:
            message = f"Emergency stop active locally; Spot STOP failed: {exc}"
            event_logger.event("spot_stop_failed", source=source, error=str(exc))
        event_logger.event("emergency_stop", source=source)
        return CommandResult(True, "APP_ESTOP", "accepted", message)

    def motion_stop(self, source: str = "unknown") -> CommandResult:
        self.state.update(emergency_stop=False, stop_state="motion_stop", last_command="MOTION_STOP", last_command_status="accepted")
        try:
            message = self.spot.stop()
        except SpotCommandError as exc:
            message = f"Motion stop requested locally; Spot STOP failed: {exc}"
            event_logger.event("spot_motion_stop_failed", source=source, error=str(exc))
        event_logger.event("motion_stop", source=source)
        return CommandResult(True, "MOTION_STOP", "accepted", message)

    def reset_stop(self) -> CommandResult:
        self.state.update(emergency_stop=False, stop_state="clear", last_command="RESET_STOP", last_command_status="accepted")
        self.state.set_mode(SystemMode.IDLE)
        self.state.append_command_log("RESET STOP")
        event_logger.event("reset_stop")
        return CommandResult(True, "RESET_STOP", "accepted", "Emergency stop reset")

    def handle(self, command: str, source: str = "web") -> CommandResult:
        normalized = command.strip().upper()
        if normalized == "STOP":
            normalized = "APP_ESTOP"
        now = time.time()

        if normalized == "APP_ESTOP":
            result = self.emergency_stop(source)
            self._record_result(result, now, source)
            return result

        if normalized == "MOTION_STOP":
            result = self.motion_stop(source)
            self._record_result(result, now, source)
            return result

        if normalized not in ALLOWED_COMMANDS:
            result = CommandResult(False, normalized, "rejected", "Command is not in whitelist")
            self._record_result(result, now, source)
            return result

        if self._is_real_mode() and normalized not in self._real_allowed_commands():
            result = CommandResult(False, normalized, "blocked", REAL_MODE_BLOCKED_MESSAGE)
            self._record_result(result, now, source)
            return result

        snapshot = self.state.snapshot()
        if snapshot["emergency_stop"] and normalized in MOTION_COMMANDS | {"SIT", "STAND", "BARK"}:
            result = CommandResult(False, normalized, "blocked", "Emergency stop is active")
            self._record_result(result, now, source)
            return result

        if normalized in MOTION_COMMANDS and now - self._last_motion_time < config.command_rate_limit_s:
            result = CommandResult(False, normalized, "rate_limited", "Motion command rate limit")
            self._record_result(result, now, source)
            return result

        try:
            result = self._execute(normalized)
        except SpotCommandError as exc:
            result = CommandResult(False, normalized, "blocked", str(exc))
        if normalized in MOTION_COMMANDS:
            self._last_motion_time = now
        self._record_result(result, now, source)
        return result

    def _execute(self, command: str) -> CommandResult:
        if command in {"APP_ESTOP", "MOTION_STOP"}:
            return CommandResult(True, command, "accepted", self.spot.stop())

        if command == "APPROACH_BLUE_SNAKE":
            snapshot = self.state.snapshot()
            if not snapshot["blue_snake_stable"]:
                return CommandResult(False, command, "blocked", "Blue snake is not stable")
            self.state.set_mode(SystemMode.APPROACHING_SNAKE)
            return CommandResult(True, command, "accepted", self.spot.approach_blue_snake_step())

        action_name = {
            "SIT": "sit",
            "STAND": "stand",
            "POWER_OFF": "power_off",
            "MOVE_FORWARD_SHORT": "move_forward_short",
            "MOVE_BACKWARD_SHORT": "move_backward_short",
            "ROTATE_LEFT_SHORT": "rotate_left_short",
            "ROTATE_RIGHT_SHORT": "rotate_right_short",
            "BARK": "bark",
        }[command]
        action = getattr(self.spot, action_name)
        return CommandResult(True, command, "accepted", action())

    def _record_result(self, result: CommandResult, now: float, source: str) -> None:
        updates = dict(
            last_command=result.command,
            last_command_status=result.status,
            last_command_time=now,
        )
        if result.accepted:
            updates["last_accepted_command"] = result.command
        self.state.update(**updates)
        self.state.append_command_log(f"{result.status.upper()} {result.command}: {result.message}")
        event_logger.event(
            "command",
            source=source,
            command=result.command,
            accepted=result.accepted,
            status=result.status,
            message=result.message,
        )
        self._play_audio_feedback(result)

    def _play_audio_feedback(self, result: CommandResult) -> None:
        if result.accepted and result.command == "APP_ESTOP":
            audio_out.bark_warn()
        elif result.accepted:
            audio_out.bark_ok()
        elif result.status == "blocked":
            audio_out.bark_no()

    def _is_real_mode(self) -> bool:
        return bool(getattr(self.spot, "is_real", False))

    def _real_allowed_commands(self) -> set[str]:
        return {item.strip().upper() for item in config.spot_real_allowed_commands.split(",") if item.strip()}
