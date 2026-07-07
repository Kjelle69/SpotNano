# Safety Skill

This project controls or may later control a real Boston Dynamics Spot robot.

Safety requirements:

1. No perception, audio, web, AI, or language model component may command the robot directly.
2. All commands must go through `CommandManager`.
3. Emergency stop has highest priority.
4. The word `STOPP` must trigger emergency stop even without wake word.
5. Web emergency stop must be available.
6. Motion commands must be short, slow, and time-limited.
7. Never implement open-ended continuous motion.
8. If a tracked visual target is lost, stop immediately.
9. If an exception occurs in vision/audio/command flow, fail safe.
10. Initial implementation must use fake Spot mode only.
11. Real Spot SDK control must require an explicit config flag.
12. Log every command, accepted or rejected.

Allowed internal commands:

- `SIT`
- `STAND`
- `STOP`
- `MOVE_FORWARD_SHORT`
- `MOVE_BACKWARD_SHORT`
- `ROTATE_LEFT_SHORT`
- `ROTATE_RIGHT_SHORT`
- `BARK`
- `APPROACH_BLUE_SNAKE`

Never add a new motion command without also adding safety gating in `CommandManager`.

