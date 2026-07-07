# Spot Skill

Initial implementation is fake only.

Fake functions:
- `sit()`
- `stand()`
- `stop()`
- `move_forward_short()`
- `move_backward_short()`
- `rotate_left_short()`
- `rotate_right_short()`
- `bark()`
- `approach_blue_snake_step()`

Each fake function logs what would have happened.

Later real implementation:
- Boston Dynamics Spot SDK
- lease handling
- estop integration if available
- low speed only
- short timed velocity commands
- never continuous open-ended movement

Do not import the Spot SDK while fake mode is active.

