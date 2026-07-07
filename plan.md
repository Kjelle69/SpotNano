# Spot Orin Nano Control System Plan

## Purpose

This project builds a safe experimental control and perception system for a Boston Dynamics Spot robot using a Jetson Orin Nano, a USB webcam with microphone, local vision models, audio commands, and a browser-based operator dashboard.

The system starts in simulation/fake-robot mode. Real Spot movement must only be enabled after the safety layer, web emergency stop, audio stop command, and fake command flow are verified.

## Core Idea

The Jetson Orin Nano acts as a local edge-AI module.

Inputs:
- USB webcam video
- USB webcam microphone
- browser/operator commands
- later: Spot robot state

Outputs:
- browser dashboard
- text/log output
- audio feedback through speaker/TTS
- later: Spot SDK commands

## Main Features

### Web Dashboard

The system provides a local web interface with:
- live camera feed
- current system state
- blue snake detection status
- last audio phrase
- last interpreted command
- fake/real Spot command log
- emergency stop button
- test command buttons
- recent logs

Routes:
- `/` dashboard
- `/video_feed` MJPEG camera stream
- `/api/status` JSON status
- `/api/logs` recent logs
- `/api/stop` emergency stop
- `/api/reset_stop` reset emergency stop
- `/api/command` test command endpoint

### Vision

The system detects whether a blue toy snake or blue dog toy shaped like a snake is visible in the webcam image.

Initial implementation:
- camera frames via OpenCV/V4L2
- optional digital brightness enhancement
- Moondream through Ollama API
- simple YES/NO prompt:
  - `BLUE_SNAKE: YES`
  - `BLUE_SNAKE: NO`

Vision updates shared state only and never commands Spot directly.

### Audio

Audio output uses `espeak-ng` if available. Audio input starts as web/keyboard-simulated commands before later Vosk integration.

Voice commands must map to a fixed whitelist. `STOPP` must work even without saying `SPOT`.

### Command Manager

All commands must pass through the command manager.

No audio, vision, web, or AI component may command Spot directly.

The command manager is responsible for:
- emergency stop
- command whitelist
- state machine
- rate limiting
- movement timeout
- fake/real Spot mode
- logging every accepted or rejected command

### Emergency Stop

Emergency stop has highest priority.

When emergency stop is active:
- all motion commands are blocked
- only safe commands may run
- system requires explicit reset before motion can resume

### State Machine

Initial states:
- `IDLE`
- `BLUE_SNAKE_DETECTED`
- `APPROACHING_SNAKE`
- `STOPPED`

Suggested transitions:

```text
IDLE
 ├── blue_snake_stable -> BLUE_SNAKE_DETECTED + bark/audio feedback
 ├── SIT command       -> fake/real Spot sit
 ├── STAND command     -> fake/real Spot stand
 └── STOP command      -> STOPPED

BLUE_SNAKE_DETECTED
 ├── KOM command       -> APPROACHING_SNAKE
 ├── snake lost        -> IDLE
 └── STOP command      -> STOPPED

APPROACHING_SNAKE
 ├── snake centered    -> move forward slowly
 ├── snake left        -> rotate left slowly
 ├── snake right       -> rotate right slowly
 ├── snake lost        -> stop -> IDLE
 ├── timeout           -> stop -> IDLE
 └── STOP command      -> STOPPED

STOPPED
 └── reset_stop        -> IDLE
```

## Development Phases

1. Project skeleton
2. Live camera web feed
3. Vision service
4. Web emergency stop and command buttons
5. Audio output
6. Audio input
7. Fake Spot behavior
8. Real Spot SDK

## Safety Rules

- No direct AI-to-robot movement.
- All commands pass through Command Manager.
- STOPP overrides everything.
- Movement commands must be short and time-limited.
- No continuous movement without repeated safety checks.
- Lost target means stop.
- Web STOP must always be available.
- In fake mode, never import or call Spot SDK movement.
- Real mode must require explicit configuration flag.

