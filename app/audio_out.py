import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

try:
    from app.logger import event_logger
except Exception:  # pragma: no cover
    event_logger = None


DEFAULT_WAV_PATH = "/usr/share/sounds/alsa/Front_Center.wav"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOUNDS_DIR = PROJECT_ROOT / "sounds"
BARK_OK_PATH = SOUNDS_DIR / "BarkOneTime.wav"
BARK_NO_PATH = SOUNDS_DIR / "BarkTwoTimes.wav"
BARK_WARN_PATH = SOUNDS_DIR / "BarkThreeTimes.wav"
BARK_SNAKE_PATH = SOUNDS_DIR / "BarkSnake.wav"


def _log(event_type: str, **fields: Any) -> None:
    if event_logger is not None:
        event_logger.event(event_type, **fields)


def _terminal_bell() -> None:
    sys.stdout.write("\a")
    sys.stdout.flush()


def _spawn_paplay(path: str) -> bool:
    if not shutil.which("paplay"):
        return False

    try:
        subprocess.Popen(
            ["paplay", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        _log("audio_out_fallback", action="paplay", reason=str(exc), path=path)
        return False

    return True


def _spawn_aplay(path: str) -> bool:
    if not shutil.which("aplay"):
        return False
    command = ["aplay"]
    if config_device := _audio_out_device():
        command.extend(["-D", config_device])
    command.append(path)
    try:
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        _log("audio_out_fallback", action="aplay", reason=str(exc), path=path)
        return False
    return True


def _audio_out_device() -> str:
    try:
        from app.config import config

        return config.audio_out_device.strip()
    except Exception:
        return ""


def _spawn_player(path: str) -> bool:
    try:
        from app.config import config

        player = config.audio_out_player.strip().lower()
    except Exception:
        player = "paplay"
    if player == "aplay":
        return _spawn_aplay(path) or _spawn_paplay(path)
    return _spawn_paplay(path) or _spawn_aplay(path)


def _fallback_voff(action: str, path: str, reason: str) -> bool:
    _log("audio_out_fallback", action=action, reason=reason, path=path)
    if _speak_voff(action):
        return True
    if play_wav(DEFAULT_WAV_PATH):
        return True
    return False


def _speak_voff(action: str) -> bool:
    if not shutil.which("espeak-ng"):
        return False
    try:
        subprocess.Popen(
            ["espeak-ng", "-v", "sv", "-s", "220", "-p", "80", "voff"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        _log("audio_out_fallback", action=action, reason=str(exc), method="espeak-ng")
        return False
    _log("audio_out", action=action, method="espeak-ng-fallback")
    return True


def _resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


def play_wav(path: str = DEFAULT_WAV_PATH) -> bool:
    if _spawn_player(path):
        _log("audio_out", action="play_wav", path=path)
        return True

    _terminal_bell()
    _log("audio_out_fallback", action="play_wav", reason="audio player unavailable", path=path)
    return False


def play_audio_file(path: str) -> bool:
    resolved = _resolve_path(path)
    path_text = str(resolved)
    if not resolved.exists():
        return _fallback_voff("play_audio_file", path_text, "missing file")

    if _spawn_player(path_text):
        _log("audio_out", action="play_audio_file", path=path_text)
        return True

    return _fallback_voff("play_audio_file", path_text, "audio player unavailable")


def speak(text: str, lang: str = "sv") -> bool:
    phrase = str(text)
    if shutil.which("espeak-ng"):
        try:
            subprocess.Popen(
                ["espeak-ng", "-v", lang, phrase],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _log("audio_out", action="speak", text=phrase, lang=lang)
            return True
        except OSError as exc:
            _log("audio_out_fallback", action="speak", reason=str(exc), text=phrase, lang=lang)

    played = play_wav()
    if not played:
        _log("audio_out_fallback", action="speak", reason="espeak-ng and paplay unavailable", text=phrase)
    return played


def beep(count: int = 1, delay_s: float = 0.15) -> bool:
    safe_count = max(1, int(count))
    safe_delay = max(0.0, float(delay_s))

    def worker() -> None:
        for index in range(safe_count):
            play_wav()
            if index < safe_count - 1:
                time.sleep(safe_delay)

    threading.Thread(target=worker, daemon=True).start()
    _log("audio_out", action="beep", count=safe_count, delay_s=safe_delay)
    return True


def bark_ok() -> bool:
    return play_audio_file(str(BARK_OK_PATH))


def bark_no() -> bool:
    return play_audio_file(str(BARK_NO_PATH))


def bark_warn() -> bool:
    return play_audio_file(str(BARK_WARN_PATH))


def bark_snake() -> bool:
    return play_audio_file(str(BARK_SNAKE_PATH))


def bark() -> bool:
    return bark_ok()


def bark_sound_status() -> dict[str, bool]:
    return {
        "BarkOneTime": BARK_OK_PATH.exists(),
        "BarkTwoTimes": BARK_NO_PATH.exists(),
        "BarkThreeTimes": BARK_WARN_PATH.exists(),
        "BarkSnake": BARK_SNAKE_PATH.exists(),
    }


def say(text: str) -> bool:
    return speak(text)
