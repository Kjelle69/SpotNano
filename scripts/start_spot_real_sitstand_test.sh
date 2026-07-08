#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

missing=()
[[ -n "${SPOT_USERNAME:-}" ]] || missing+=("SPOT_USERNAME")
[[ -n "${SPOT_PASSWORD:-}" ]] || missing+=("SPOT_PASSWORD")

if (( ${#missing[@]} > 0 )); then
  echo "Refusing to start real Spot mode. Missing: ${missing[*]}" >&2
  echo "Required: SPOT_USERNAME SPOT_PASSWORD" >&2
  exit 2
fi

export SPOT_HOST="${SPOT_HOST:-spot-rear}"
echo "REAL SPOT MODE - only SIT/STAND/POWER_OFF/MOTION_STOP/APP_ESTOP enabled"
echo "Spot mode: real"
echo "Spot host: $SPOT_HOST"
echo "SPOT_ENABLE_POWER_ON=${SPOT_ENABLE_POWER_ON:-false}"
echo "Audio input is enabled for: Spot stop, Spot sit, Spot stand, Spot stand up."
echo "Auto vision is off for the real robot voice test."
echo "Joystick/turn commands are disabled by default. Override SPOT_REAL_ALLOWED_COMMANDS only in a clear test area."

export SPOT_MODE=real
export SPOT_ENABLE_POWER_ON="${SPOT_ENABLE_POWER_ON:-false}"
export SPOT_COMMAND_TIMEOUT_S="${SPOT_COMMAND_TIMEOUT_S:-10.0}"
export SPOT_SDK_CLIENT_NAME="${SPOT_SDK_CLIENT_NAME:-spot-orin-nano}"
export SPOT_REAL_ALLOWED_COMMANDS="${SPOT_REAL_ALLOWED_COMMANDS:-SIT,STAND,POWER_OFF,MOTION_STOP,APP_ESTOP}"
export SPOT_REAL_TURN_RATE_RAD_S="${SPOT_REAL_TURN_RATE_RAD_S:-0.25}"
export SPOT_REAL_TURN_DURATION_S="${SPOT_REAL_TURN_DURATION_S:-0.6}"
export AUDIO_IN_ENABLED="${AUDIO_IN_ENABLED:-true}"
export AUDIO_IN_BACKEND="${AUDIO_IN_BACKEND:-faster_whisper}"
export AUDIO_DEVICE="${AUDIO_DEVICE:-auto}"
export AUDIO_DEVICE_MATCH="${AUDIO_DEVICE_MATCH:-logitech}"
export AUDIO_CHANNELS="${AUDIO_CHANNELS:-2}"
export WHISPER_MODEL="${WHISPER_MODEL:-base.en}"
export WHISPER_LANGUAGE="${WHISPER_LANGUAGE:-en}"
export WHISPER_DEVICE="${WHISPER_DEVICE:-cpu}"
export WHISPER_COMPUTE_TYPE="${WHISPER_COMPUTE_TYPE:-int8}"
export WHISPER_CHUNK_S="${WHISPER_CHUNK_S:-2.0}"
export WHISPER_BEAM_SIZE="${WHISPER_BEAM_SIZE:-1}"
export AUDIO_SPEECH_RMS_THRESHOLD="${AUDIO_SPEECH_RMS_THRESHOLD:-0.3}"
export AUDIO_SPEECH_PEAK_THRESHOLD="${AUDIO_SPEECH_PEAK_THRESHOLD:-0.65}"
export AUDIO_ACTIVITY_HOLD_S="${AUDIO_ACTIVITY_HOLD_S:-2.0}"
export AUDIO_SPEECH_QUEUE_MAX="${AUDIO_SPEECH_QUEUE_MAX:-2}"
export AUDIO_INFERENCE_WAIT_TIMEOUT_S="${AUDIO_INFERENCE_WAIT_TIMEOUT_S:-10.0}"
export WHISPER_HOTWORDS="${WHISPER_HOTWORDS:-spot stop, spot emergency stop, spot sit, spot sit down, spot seat, spot stand, spot stand up}"
export WHISPER_INITIAL_PROMPT="${WHISPER_INITIAL_PROMPT:-Short English robot commands only: spot stop, spot emergency stop, spot sit, spot sit down, spot seat, spot stand, spot stand up. Spot stop means stop current motion. Spot emergency stop is latched.}"
export AUTO_VISION_ENABLED="${AUTO_VISION_ENABLED:-true}"
export VISION_ENABLED="${VISION_ENABLED:-true}"
export AUTO_VISION_INTERVAL="${AUTO_VISION_INTERVAL:-5}"
export AUTO_VISION_INTERVAL_S="${AUTO_VISION_INTERVAL_S:-5}"
export APP_VERSION="${APP_VERSION:-v20260707h-spot-real-test}"

exec "$ROOT/scripts/_run_profile.sh"
