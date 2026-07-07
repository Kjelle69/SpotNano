#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

missing=()
[[ -n "${SPOT_HOST:-}" ]] || missing+=("SPOT_HOST")
[[ -n "${SPOT_USERNAME:-}" ]] || missing+=("SPOT_USERNAME")
[[ -n "${SPOT_PASSWORD:-}" ]] || missing+=("SPOT_PASSWORD")

if (( ${#missing[@]} > 0 )); then
  echo "Refusing to start real Spot mode. Missing: ${missing[*]}" >&2
  echo "Required: SPOT_HOST SPOT_USERNAME SPOT_PASSWORD" >&2
  exit 2
fi

echo "REAL SPOT MODE - only SIT/STAND/STOP enabled"
echo "Host: $SPOT_HOST"
echo "SPOT_ENABLE_POWER_ON=${SPOT_ENABLE_POWER_ON:-false}"
echo "Audio input and auto vision are off for the first real robot test."

export SPOT_MODE=real
export SPOT_ENABLE_POWER_ON="${SPOT_ENABLE_POWER_ON:-false}"
export SPOT_COMMAND_TIMEOUT_S="${SPOT_COMMAND_TIMEOUT_S:-10.0}"
export SPOT_SDK_CLIENT_NAME="${SPOT_SDK_CLIENT_NAME:-spot-orin-nano}"
export SPOT_REAL_ALLOWED_COMMANDS="${SPOT_REAL_ALLOWED_COMMANDS:-SIT,STAND,STOP}"
export AUDIO_IN_ENABLED="${AUDIO_IN_ENABLED:-false}"
export AUTO_VISION_ENABLED="${AUTO_VISION_ENABLED:-false}"
export VISION_ENABLED="${VISION_ENABLED:-false}"
export APP_VERSION="${APP_VERSION:-v20260707h-spot-real-test}"

exec "$ROOT/scripts/_run_profile.sh"
