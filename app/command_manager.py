import time
from dataclasses import dataclass

from app import audio_out
from app.config import config
from app.logger import event_logger
from app.spot_interface import FakeSpotInterface
from app.state import SharedState, SystemMode


ALLOWED_COMMANDS = {
    "SIT",
    "STAND",
    "STOP",
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
        self.state.update(emergency_stop=True, last_command="STOP", last_command_status="accepted")
        self.state.set_mode(SystemMode.STOPPED)
        message = self.spot.stop()
        event_logger.event("emergency_stop", source=source)
        return CommandResult(True, "STOP", "accepted", message)

    def reset_stop(self) -> CommandResult:
        self.state.update(emergency_stop=False, last_command="RESET_STOP", last_command_status="accepted")
        self.state.set_mode(SystemMode.IDLE)
        self.state.append_command_log("RESET STOP")
        event_logger.event("reset_stop")
        return CommandResult(True, "RESET_STOP", "accepted", "Emergency stop reset")

    def handle(self, command: str, source: str = "web") -> CommandResult:
        normalized = command.strip().upper()
        now = time.time()

        if normalized == "STOP":
            result = self.emergency_stop(source)
            self._record_result(result, now, source)
            return result

        if normalized not in ALLOWED_COMMANDS:
            result = CommandResult(False, normalized, "rejected", "Command is not in whitelist")
            self._record_result(result, now, source)
            return result

        snapshot = self.state.snapshot()
        if snapshot["emergency_stop"] and normalized in MOTION_COMMANDS | {"SIT", "STAND", "BARK"}:
            result = CommandResult(False, normalized, "blocked", "Emergency stop is active")
            self._record_result(result, now, source)
            return result

        if config.real_spot_mode:
            result = CommandResult(False, normalized, "blocked", "Real Spot mode is not implemented yet")
            self._record_result(result, now, source)
            return result

        if normalized in MOTION_COMMANDS and now - self._last_motion_time < config.command_rate_limit_s:
            result = CommandResult(False, normalized, "rate_limited", "Motion command rate limit")
            self._record_result(result, now, source)
            return result

        result = self._execute(normalized)
        if normalized in MOTION_COMMANDS:
            self._last_motion_time = now
        self._record_result(result, now, source)
        return result

    def _execute(self, command: str) -> CommandResult:
        actions = {
            "SIT": self.spot.sit,
            "STAND": self.spot.stand,
            "MOVE_FORWARD_SHORT": self.spot.move_forward_short,
            "MOVE_BACKWARD_SHORT": self.spot.move_backward_short,
            "ROTATE_LEFT_SHORT": self.spot.rotate_left_short,
            "ROTATE_RIGHT_SHORT": self.spot.rotate_right_short,
            "BARK": self.spot.bark,
        }
        if command == "APPROACH_BLUE_SNAKE":
            snapshot = self.state.snapshot()
            if not snapshot["blue_snake_stable"]:
                return CommandResult(False, command, "blocked", "Blue snake is not stable")
            self.state.set_mode(SystemMode.APPROACHING_SNAKE)
            return CommandResult(True, command, "accepted", self.spot.approach_blue_snake_step())

        action = actions[command]
        return CommandResult(True, command, "accepted", action())

    def _record_result(self, result: CommandResult, now: float, source: str) -> None:
        self.state.update(
            last_command=result.command,
            last_command_status=result.status,
            last_command_time=now,
        )
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
        if result.accepted and result.command == "STOP":
            audio_out.bark_warn()
        elif result.accepted:
            audio_out.bark_ok()
        elif result.status == "blocked":
            audio_out.bark_no()
