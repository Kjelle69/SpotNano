# Audio Skill

The audio system has two parts:

1. Audio output
2. Audio input

Audio output:
- Use `espeak-ng` initially.
- Swedish phrases are acceptable.
- It may say "Jag ser den bla ormen", "Stopp aktiverat", or "Voff".

Audio input:
- Must use a fixed whitelist of commands.
- Do not use free-form LLM interpretation for robot motion.
- The word `STOPP` must trigger emergency stop even without wake word.
- `SPOT, stopp` and `STOPP` both map to `STOP`.

Initial recognized phrases:
- `spot sitt`
- `spot sta`
- `spot framåt`
- `spot bakåt`
- `spot vänster`
- `spot höger`
- `spot stopp`
- `stopp`
- `kom`

Mapping:
- `spot sitt` -> `SIT`
- `spot sta` -> `STAND`
- `spot framåt` -> `MOVE_FORWARD_SHORT`
- `spot bakåt` -> `MOVE_BACKWARD_SHORT`
- `spot vänster` -> `ROTATE_LEFT_SHORT`
- `spot höger` -> `ROTATE_RIGHT_SHORT`
- `spot stopp` -> `STOP`
- `stopp` -> `STOP`
- `kom` -> `APPROACH_BLUE_SNAKE`

All parsed commands must be passed to `CommandManager`.

