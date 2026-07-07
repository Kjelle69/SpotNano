import re
import threading
import time
from collections import deque
from typing import Callable

from app.command_manager import ALLOWED_COMMANDS
from app.config import config
from app.inference_gate import acquire_inference, mark_audio_activity, request_cancel_vision
from app.logger import event_logger
from app.state import shared_state


STOP_COMMANDS = {
    "stop",
    "spot stop",
    "emergency stop",
    "spot emergency stop",
    "abort",
    "spot abort",
    "stop stop",
    "stop stop stop",
    "stopp",
    "spot stopp",
    "nödstopp",
    "nodstopp",
    "avbryt",
}
WAKE_WORDS = {"spot", "sport"}
MAX_TRANSCRIPT_CHARS = 40

COMMAND_AFTER_WAKE = {
    "stop": "STOP",
    "sit": "SIT",
    "seat": "SIT",
    "sit down": "SIT",
    "stand": "STAND",
    "stand up": "STAND",
    "go": "MOVE_FORWARD_SHORT",
    "move forward": "MOVE_FORWARD_SHORT",
    "forward": "MOVE_FORWARD_SHORT",
    "back": "MOVE_BACKWARD_SHORT",
    "move back": "MOVE_BACKWARD_SHORT",
    "move backward": "MOVE_BACKWARD_SHORT",
    "backward": "MOVE_BACKWARD_SHORT",
    "left": "ROTATE_LEFT_SHORT",
    "right": "ROTATE_RIGHT_SHORT",
    "come": "APPROACH_BLUE_SNAKE",
}

_listener_thread: threading.Thread | None = None
_transcriber_thread: threading.Thread | None = None
_stop_event = threading.Event()
_mic_test_event = threading.Event()
_recording_lock = threading.Lock()
_queue_condition = threading.Condition()
_speech_queue = deque()
_last_silence_log_time = 0.0


def normalize_text(text: str) -> str:
    lowered = text.strip().lower()
    lowered = lowered.replace(",", " ")
    cleaned = re.sub(r"[^a-zåäö0-9 ]+", " ", lowered)
    return " ".join(cleaned.split())


def parse_voice_command(text: str) -> str | None:
    normalized = collapse_repeated_words(normalize_text(text))
    if normalized in STOP_COMMANDS:
        return "STOP"
    if normalized == "come":
        return "APPROACH_BLUE_SNAKE"
    wake_command = extract_wake_command(normalized)
    if wake_command is None:
        return None
    command = COMMAND_AFTER_WAKE.get(wake_command)
    if command in ALLOWED_COMMANDS:
        return command
    return None


def parse_phrase(phrase: str) -> str | None:
    return parse_voice_command(phrase)


def collapse_repeated_words(text: str) -> str:
    words = text.split()
    if len(words) <= 1:
        return text
    collapsed: list[str] = []
    for word in words:
        if not collapsed or collapsed[-1] != word:
            collapsed.append(word)
    return " ".join(collapsed)


def extract_wake_command(text: str) -> str | None:
    words = text.split()
    for index, word in enumerate(words):
        if word in WAKE_WORDS:
            command = " ".join(words[index + 1 :])
            return collapse_repeated_words(command) if command else None
    return None


def start_audio_listener(
    command_callback: Callable[[str, str], object] | None = None,
    phrase_callback: Callable[[str], object] | None = None,
) -> bool:
    global _listener_thread, _transcriber_thread

    if not config.audio_in_enabled:
        event_logger.event("audio_in_disabled")
        return False

    if config.audio_in_backend != "faster_whisper":
        event_logger.event("audio_in_unavailable", reason="unsupported backend", backend=config.audio_in_backend)
        return False

    if _listener_thread and _listener_thread.is_alive():
        return True

    try:
        import numpy as np
        import sounddevice as sd
        from faster_whisper import WhisperModel
    except ImportError as exc:
        event_logger.event("audio_in_unavailable", reason=f"missing dependency: {exc}")
        return False

    device = _sounddevice_device(sd)
    if device is None:
        event_logger.event("audio_in_unavailable", reason="no input device selected")
        return False
    _stop_event.clear()
    _listener_thread = threading.Thread(
        target=_listener_loop,
        args=(np, sd, device),
        daemon=True,
    )
    _transcriber_thread = threading.Thread(
        target=_transcriber_loop,
        args=(WhisperModel, command_callback, phrase_callback),
        daemon=True,
    )
    _listener_thread.start()
    _transcriber_thread.start()
    event_logger.event(
        "audio_in_started",
        backend=config.audio_in_backend,
        model=config.whisper_model,
        language=config.whisper_language,
        sample_rate=config.audio_sample_rate,
        device=device,
        chunk_s=config.whisper_chunk_s,
    )
    return True


def stop_audio_listener() -> None:
    _stop_event.set()
    with _queue_condition:
        _queue_condition.notify_all()
    if _listener_thread and _listener_thread.is_alive():
        _listener_thread.join(timeout=2)
    if _transcriber_thread and _transcriber_thread.is_alive():
        _transcriber_thread.join(timeout=2)


def _listener_loop(np, sd, device) -> None:
    try:
        sample_count = max(1, int(config.audio_sample_rate * config.whisper_chunk_s))
        while not _stop_event.is_set():
            if _mic_test_event.is_set():
                time.sleep(0.1)
                continue
            if config.audio_debug_logs:
                event_logger.event("audio_in_record_started", chunk_s=config.whisper_chunk_s)
            if _stop_event.is_set():
                break
            with _recording_lock:
                if _mic_test_event.is_set():
                    continue
                recording = sd.rec(
                    sample_count,
                    samplerate=config.audio_sample_rate,
                    channels=1,
                    dtype="float32",
                    device=device,
                )
                sd.wait()
            if _stop_event.is_set():
                break

            audio = np.asarray(recording, dtype=np.float32).reshape(-1)
            if not _has_audio_level(audio, np):
                continue
            _queue_speech_chunk(audio)
    except Exception as exc:
        event_logger.event("audio_in_unavailable", reason=str(exc))
    finally:
        event_logger.event("audio_in_stopped")


def _transcriber_loop(whisper_model_cls, command_callback, phrase_callback) -> None:
    try:
        model = whisper_model_cls(
            config.whisper_model,
            device=config.whisper_device,
            compute_type=config.whisper_compute_type,
        )
        event_logger.event(
            "audio_in_model_loaded",
            backend=config.audio_in_backend,
            model=config.whisper_model,
            device=config.whisper_device,
            compute_type=config.whisper_compute_type,
        )

        while not _stop_event.is_set():
            audio = _dequeue_speech_chunk()
            if audio is None:
                break
            if _stop_event.is_set():
                break

            request_cancel_vision("audio_waiting")
            event_logger.event("audio_in_waiting_for_inference")
            with acquire_inference(
                "audio_whisper",
                priority="high",
                timeout=config.audio_inference_wait_timeout_s,
            ) as acquired:
                if not acquired:
                    event_logger.event("audio_transcription_dropped_busy", timeout_s=config.audio_inference_wait_timeout_s)
                    continue
                if _stop_event.is_set():
                    continue
                event_logger.event("audio_in_acquired_inference")
                segments, info = model.transcribe(
                    audio,
                    language=config.whisper_language,
                    beam_size=config.whisper_beam_size,
                    vad_filter=config.whisper_vad_filter,
                    vad_parameters={"min_silence_duration_ms": 350},
                    condition_on_previous_text=config.whisper_condition_on_previous_text,
                    temperature=config.whisper_temperature,
                    initial_prompt=config.whisper_initial_prompt,
                    hotwords=config.whisper_hotwords,
                    no_speech_threshold=0.5,
                    log_prob_threshold=-0.8,
                    hallucination_silence_threshold=0.5,
                )
                if _stop_event.is_set():
                    break
            segment_list = list(segments)
            phrase = " ".join(segment.text.strip() for segment in segment_list).strip()
            avg_logprob = _avg_segment_attr(segment_list, "avg_logprob")
            no_speech_prob = _max_segment_attr(segment_list, "no_speech_prob")
            if phrase or config.audio_debug_logs:
                event_logger.event(
                    "audio_in_transcribed",
                    phrase=phrase,
                    language=getattr(info, "language", None),
                    duration=getattr(info, "duration", None),
                    avg_logprob=avg_logprob,
                    no_speech_prob=no_speech_prob,
                )
            if transcript_rejection_reason(phrase, avg_logprob, no_speech_prob) is not None:
                event_logger.event(
                    "audio_transcript_rejected",
                    phrase=phrase,
                    reason=transcript_rejection_reason(phrase, avg_logprob, no_speech_prob),
                    avg_logprob=avg_logprob,
                    no_speech_prob=no_speech_prob,
                )
                continue
            _handle_phrase(phrase, command_callback, phrase_callback)
    except Exception as exc:
        event_logger.event("audio_in_unavailable", reason=str(exc))
    finally:
        event_logger.event("audio_in_transcriber_stopped")


def _queue_speech_chunk(audio) -> None:
    mark_audio_activity(config.audio_activity_hold_s)
    with _queue_condition:
        queue_max = max(1, int(config.audio_speech_queue_max))
        if len(_speech_queue) >= queue_max:
            _speech_queue.popleft()
            event_logger.event("audio_chunk_dropped_queue_full", queue_max=queue_max)
        _speech_queue.append(audio.copy())
        shared_state.update(audio_queue_length=len(_speech_queue))
        event_logger.event("audio_chunk_queued", queue_length=len(_speech_queue), queue_max=queue_max)
        _queue_condition.notify()


def _dequeue_speech_chunk():
    with _queue_condition:
        while not _stop_event.is_set() and not _speech_queue:
            _queue_condition.wait(timeout=0.2)
        if _stop_event.is_set():
            return None
        audio = _speech_queue.popleft()
        shared_state.update(audio_queue_length=len(_speech_queue))
        return audio


def _handle_phrase(phrase: str, command_callback, phrase_callback) -> None:
    if not phrase:
        return
    command = parse_voice_command(phrase)
    event_logger.event("audio_in_recognized", phrase=phrase, command=command)
    if command is None:
        event_logger.event("audio_in_filtered", phrase=phrase)
        return
    if phrase_callback is not None:
        phrase_callback(phrase)
    if command is not None and command_callback is not None:
        command_callback(command, phrase)


def command_phrases() -> list[str]:
    phrases = set(STOP_COMMANDS)
    phrases.update(f"spot {phrase}" for phrase in COMMAND_AFTER_WAKE)
    phrases.add("come")
    return sorted(phrases)


def _sounddevice_device(sd) -> int | str | None:
    device = config.audio_device.strip()
    if device.isdigit():
        selected = int(device)
        _log_selected_device(sd, selected, requested=device)
        return selected
    if config.audio_device_match.strip():
        selected = _select_matching_input_device(sd, config.audio_device_match.strip())
        if selected is None:
            _log_input_devices(sd)
        else:
            _log_selected_device(sd, selected, requested=f"match:{config.audio_device_match}")
        return selected
    if not device or device in {"auto", "default"}:
        selected = _select_input_device(sd)
        _log_selected_device(sd, selected, requested=device or "auto")
        return selected
    return device


def _select_matching_input_device(sd, match: str) -> int | None:
    needle = match.lower()
    for index, info in enumerate(sd.query_devices()):
        if int(info.get("max_input_channels", 0)) > 0 and needle in str(info.get("name", "")).lower():
            return index
    return None


def _log_selected_device(sd, selected, requested: str) -> None:
    info = _selected_device_info(sd, selected)
    name = info.get("name")
    max_input_channels = info.get("max_input_channels")
    default_samplerate = info.get("default_samplerate")
    shared_state.update(
        audio_input_device=selected,
        audio_input_device_name=str(name or ""),
        audio_input_max_channels=_safe_int(max_input_channels),
        audio_input_default_samplerate=_safe_float(default_samplerate),
        audio_input_requested_samplerate=config.audio_sample_rate,
        audio_input_chunk_s=config.whisper_chunk_s,
    )
    event_logger.event(
        "audio_in_device_selected",
        requested=requested,
        device=selected,
        name=name,
        max_input_channels=max_input_channels,
        default_samplerate=default_samplerate,
        requested_samplerate=config.audio_sample_rate,
        chunk_s=config.whisper_chunk_s,
    )


def _selected_device_info(sd, selected) -> dict:
    try:
        if isinstance(selected, int):
            return dict(sd.query_devices()[selected])
    except Exception:
        return {}
    return {"name": str(selected)} if selected is not None else {}


def _log_input_devices(sd) -> None:
    devices = []
    for index, info in enumerate(sd.query_devices()):
        if int(info.get("max_input_channels", 0)) > 0:
            devices.append({"index": index, "name": info.get("name"), "inputs": info.get("max_input_channels")})
    event_logger.event("audio_in_device_match_failed", match=config.audio_device_match, devices=devices)


def _select_input_device(sd) -> int | None:
    devices = sd.query_devices()
    preferred_terms = ("logitech", "webcam", "usb")
    fallback: int | None = None
    for index, info in enumerate(devices):
        max_inputs = int(info.get("max_input_channels", 0))
        if max_inputs <= 0:
            continue
        if fallback is None:
            fallback = index
        name = str(info.get("name", "")).lower()
        if any(term in name for term in preferred_terms):
            return index
    if fallback is not None:
        return fallback
    default_input = sd.default.device[0] if isinstance(sd.default.device, (list, tuple)) else sd.default.device
    if default_input is not None and default_input >= 0:
        return int(default_input)
    return None


def _has_audio_level(audio, np) -> bool:
    global _last_silence_log_time
    if audio.size == 0:
        return False
    rms, peak = compute_audio_levels(audio, np)
    shared_state.update(last_audio_rms=rms, last_audio_peak=peak)
    event_logger.event("audio_in_level", rms=rms, peak=peak)
    speech_active = rms >= config.audio_speech_rms_threshold or peak >= config.audio_speech_peak_threshold
    if not speech_active:
        now = time.time()
        if config.audio_debug_logs and now - _last_silence_log_time >= 10.0:
            event_logger.event("audio_in_silence", rms=rms, peak=peak)
            _last_silence_log_time = now
        return False
    return True


def compute_audio_levels(audio, np) -> tuple[float, float]:
    if audio.size == 0:
        return 0.0, 0.0
    rms = float(np.sqrt(np.mean(np.square(audio))))
    peak = float(np.max(np.abs(audio)))
    return rms, peak


def record_mic_test(duration_s: float = 3.0) -> dict:
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as exc:
        event_logger.event("audio_mic_test_unavailable", reason=f"missing dependency: {exc}")
        return {"accepted": False, "status": "unavailable", "message": f"missing dependency: {exc}"}

    device = _sounddevice_device(sd)
    if device is None:
        event_logger.event("audio_mic_test_unavailable", reason="no input device selected")
        return {"accepted": False, "status": "no_device", "message": "No input device selected"}

    _mic_test_event.set()
    acquired = _recording_lock.acquire(timeout=max(3.0, duration_s + 1.0))
    if not acquired:
        _mic_test_event.clear()
        event_logger.event("audio_mic_test_unavailable", reason="recording device busy")
        return {"accepted": False, "status": "busy", "message": "Recording device is busy"}

    try:
        sample_rate = config.audio_sample_rate
        sample_count = max(1, int(sample_rate * duration_s))
        recording = sd.rec(
            sample_count,
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            device=device,
        )
        sd.wait()
        audio = np.asarray(recording, dtype=np.float32).reshape(-1)
        rms, peak = compute_audio_levels(audio, np)
        shared_state.update(last_audio_rms=rms, last_audio_peak=peak)
        info = _selected_device_info(sd, device)
        result = {
            "accepted": True,
            "status": "recorded",
            "device": device,
            "device_name": info.get("name", ""),
            "max_input_channels": info.get("max_input_channels"),
            "default_samplerate": info.get("default_samplerate"),
            "sample_rate": sample_rate,
            "duration_s": duration_s,
            "rms": rms,
            "peak": peak,
        }
        event_logger.event("audio_mic_test", **result)
        return result
    except Exception as exc:
        event_logger.event("audio_mic_test_unavailable", reason=str(exc))
        return {"accepted": False, "status": "error", "message": str(exc), "device": device}
    finally:
        _recording_lock.release()
        _mic_test_event.clear()


def _safe_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def transcript_rejection_reason(phrase: str, avg_logprob: float | None, no_speech_prob: float | None) -> str | None:
    raw_normalized = normalize_text(phrase)
    if is_repeated_hallucination(raw_normalized):
        return "repeated_pattern"
    normalized = collapse_repeated_words(raw_normalized)
    if not normalized:
        return "empty"
    exact = normalized in command_phrases()
    if len(normalized) > MAX_TRANSCRIPT_CHARS and normalized not in STOP_COMMANDS:
        return "too_long"
    if avg_logprob is not None and avg_logprob < -1.1 and not exact:
        return "low_logprob"
    if no_speech_prob is not None and no_speech_prob > 0.35 and not exact:
        return "no_speech"
    return None


def is_repeated_hallucination(text: str) -> bool:
    words = text.split()
    return len(words) >= 4 and len(set(words)) <= 2


def _avg_segment_attr(segments, attr: str) -> float | None:
    values = [getattr(segment, attr, None) for segment in segments]
    values = [float(value) for value in values if value is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _max_segment_attr(segments, attr: str) -> float | None:
    values = [getattr(segment, attr, None) for segment in segments]
    values = [float(value) for value in values if value is not None]
    if not values:
        return None
    return max(values)
