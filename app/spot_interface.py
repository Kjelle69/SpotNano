from app.logger import event_logger
from app.state import SharedState


class FakeSpotInterface:
    def __init__(self, state: SharedState) -> None:
        self.state = state

    def _fake(self, action: str) -> str:
        message = f"FAKE SPOT: {action}"
        self.state.append_command_log(message)
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

