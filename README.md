# Spot Orin Nano

Safe experimental AI control and perception system for a Jetson Orin Nano connected to a Boston Dynamics Spot robot.

The first implementation is fake-robot only. It provides a local web dashboard, shared state, command manager, fake Spot interface, and placeholders for camera, vision, and audio.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

If `python3 -m venv` fails because `ensurepip` is unavailable, install `python3-venv` with apt, or use the current machine's fallback:

```bash
python3 -m pip install --user --break-system-packages -r requirements.txt
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open:

```text
http://localhost:8000
```

## Vision

Vision is off by default. To enable one-shot Ollama/Moondream analysis:

```bash
VISION_ENABLED=true python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The default model and API endpoint are:

```text
VISION_MODEL=moondream
OLLAMA_URL=http://127.0.0.1:11434
```

The dashboard button `VISION` calls `POST /api/vision/analyze_once`.

## Audio Input

Audio input is off by default. To enable local `faster-whisper` speech-to-text:

```bash
AUDIO_IN_ENABLED=true python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Useful settings:

```text
AUDIO_DEVICE=24
WHISPER_MODEL=base.en
WHISPER_LANGUAGE=en
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_CHUNK_S=2.0
WHISPER_BEAM_SIZE=1
```

The transcribed text still goes through the fixed voice command whitelist before `CommandManager` sees it.
Audio input never commands Spot directly.

## Best Known Start Command

Current optimized command for Jetson Orin Nano, English voice commands, camera, vision, auto vision, and fake Spot mode:

```bash
CAMERA_INDEX=0 CAMERA_WIDTH=640 CAMERA_HEIGHT=480 CAMERA_FPS=8 MJPEG_FPS=6 CAMERA_JPEG_QUALITY=65 AUDIO_IN_ENABLED=true AUDIO_IN_BACKEND=faster_whisper AUDIO_DEVICE=24 WHISPER_MODEL=base.en WHISPER_LANGUAGE=en WHISPER_DEVICE=cpu WHISPER_COMPUTE_TYPE=int8 WHISPER_CHUNK_S=2.0 WHISPER_BEAM_SIZE=1 AUDIO_SPEECH_RMS_THRESHOLD=0.03 AUDIO_SPEECH_PEAK_THRESHOLD=0.15 AUDIO_ACTIVITY_HOLD_S=2.0 AUDIO_SPEECH_QUEUE_MAX=2 AUDIO_INFERENCE_WAIT_TIMEOUT_S=10.0 VISION_ENABLED=true AUTO_VISION_ENABLED=true AUTO_VISION_INTERVAL_S=15 VISION_IMAGE_MAX_WIDTH=640 VISION_JPEG_QUALITY=85 APP_VERSION=v20260707h python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

This profile uses the Logitech C930e webcam mic as input (`AUDIO_DEVICE=24`) and leaves bark output on the system/default output.

Voice-only demo command:

```bash
CAMERA_INDEX=0 CAMERA_WIDTH=640 CAMERA_HEIGHT=480 CAMERA_FPS=8 MJPEG_FPS=6 CAMERA_JPEG_QUALITY=65 AUDIO_IN_ENABLED=true AUDIO_IN_BACKEND=faster_whisper AUDIO_DEVICE=24 WHISPER_MODEL=base.en WHISPER_LANGUAGE=en WHISPER_DEVICE=cpu WHISPER_COMPUTE_TYPE=int8 WHISPER_CHUNK_S=2.0 WHISPER_BEAM_SIZE=1 VISION_ENABLED=true AUTO_VISION_ENABLED=false VISION_IMAGE_MAX_WIDTH=640 VISION_JPEG_QUALITY=85 APP_VERSION=v20260707h python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Run profiles:

```bash
scripts/start_web_only.sh
scripts/start_voice_demo.sh
scripts/start_vision_demo.sh
scripts/start_full_demo.sh
scripts/start_spot_real_sitstand_test.sh
scripts/stop_server.sh
```

## Real Spot SIT/STAND/STOP Test

Real Spot mode is opt-in and only enables `SIT`, `STAND`, and `STOP`. Walking, turning, approach/come, velocity commands, audio-to-motion, and vision-to-motion are blocked.

Install the Boston Dynamics SDK on the machine before real mode:

```bash
python3 -m pip install bosdyn-client
```

```bash
SPOT_HOST=192.168.80.3 SPOT_USERNAME=user SPOT_PASSWORD='password' scripts/start_spot_real_sitstand_test.sh
```

Optional power-on behavior:

```bash
SPOT_ENABLE_POWER_ON=true SPOT_HOST=192.168.80.3 SPOT_USERNAME=user SPOT_PASSWORD='password' scripts/start_spot_real_sitstand_test.sh
```

Connect without commanding movement:

```bash
curl -X POST http://127.0.0.1:8000/api/spot/connect
curl http://127.0.0.1:8000/api/spot/status
```

Before pressing `STAND`:

- Spot is on flat, clear ground with space around it.
- Tablet/operator is present and ready.
- Physical/robot safety systems are normal.
- Dashboard shows `spot_mode=real` and `spot_connected=true`.
- First command tested is `STOP`, then `SIT`, then `STAND`.

## Bark Audio

Local bark files live in `sounds/`:

```text
BarkOneTime.wav   OK / command accepted
BarkTwoTimes.wav  NO / command blocked
BarkThreeTimes.wav WARNING / STOP
BarkSnake.wav     blue snake detected
```

Test endpoints:

```bash
curl -X POST http://127.0.0.1:8000/api/audio/bark_ok
curl -X POST http://127.0.0.1:8000/api/audio/bark_no
curl -X POST http://127.0.0.1:8000/api/audio/bark_warn
curl -X POST http://127.0.0.1:8000/api/audio/bark_snake
```

Accepted voice commands:

```text
stop
spot stop
spot sit
spot stand
spot stand up
spot go
spot forward
spot move forward
spot back
spot move back
spot left
spot right
spot come
```

## Safety Position

- No vision, audio, web, or AI module commands Spot directly.
- All commands pass through `CommandManager`.
- Real Spot SDK movement is not implemented in this scaffold.
- `SPOT_REAL_MODE=true` is reserved for later and currently fails closed.
