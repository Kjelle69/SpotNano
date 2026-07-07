from app.audio_in import (
    _handle_phrase,
    _has_audio_level,
    _queue_speech_chunk,
    _select_matching_input_device,
    collapse_repeated_words,
    command_phrases,
    extract_wake_command,
    normalize_text,
    parse_voice_command,
    transcript_rejection_reason,
)
import app.audio_in as audio_in
import numpy as np
from types import SimpleNamespace
from app.inference_gate import clear_audio_activity, clear_cancel_vision


def test_parse_stopp():
    assert parse_voice_command("stopp") == "STOP"


def test_parse_spot_stopp():
    assert parse_voice_command("spot stopp") == "STOP"


def test_parse_spot_sit():
    assert parse_voice_command("spot sit") == "SIT"


def test_parse_spot_stand():
    assert parse_voice_command("spot stand") == "STAND"


def test_parse_spot_stand_up():
    assert parse_voice_command("spot stand up") == "STAND"


def test_parse_bare_sta_requires_wake_word():
    assert parse_voice_command("stå") is None


def test_parse_spot_go():
    assert parse_voice_command("spot go") == "MOVE_FORWARD_SHORT"


def test_parse_spot_move_forward():
    assert parse_voice_command("spot move forward") == "MOVE_FORWARD_SHORT"


def test_parse_spot_move_back():
    assert parse_voice_command("spot move back") == "MOVE_BACKWARD_SHORT"


def test_parse_kom_requires_wake_word():
    assert parse_voice_command("kom") is None


def test_parse_come():
    assert parse_voice_command("come") == "APPROACH_BLUE_SNAKE"


def test_parse_spot_come():
    assert parse_voice_command("spot come") == "APPROACH_BLUE_SNAKE"


def test_parse_unknown_returns_none():
    assert parse_voice_command("kan du dansa lite") is None


def test_parse_stopp_inside_phrase_triggers_stop():
    assert parse_voice_command("say stop now") is None


def test_parse_stoppa_triggers_stop():
    assert parse_voice_command("emergency stop") == "STOP"


def test_parse_sto_fails_safe_to_stop():
    assert parse_voice_command("stop stop stop") == "STOP"


def test_stop_it_is_not_stop():
    assert parse_voice_command("stop it") is None


def test_parse_repeated_sta_requires_wake_word():
    assert parse_voice_command("stå, stå, stå, stå, stå") is None


def test_parse_repeated_sta_after_wake_word():
    assert transcript_rejection_reason("spot stand stand stand stand", None, None) == "repeated_pattern"


def test_collapse_repeated_words():
    assert collapse_repeated_words("stå stå stå") == "stå"


def test_normalize_text_handles_case_punctuation_and_spaces():
    assert normalize_text("  SPOT,  Stand! ") == "spot stand"


def test_extract_wake_command_uses_text_after_spot():
    assert extract_wake_command("hello spot stand up") == "stand up"


def test_command_phrases_are_limited_to_whitelist_phrases():
    phrases = command_phrases()
    assert "spot sit" in phrases
    assert "stop" in phrases
    assert "kan du dansa lite" not in phrases


def test_filtered_phrase_does_not_call_callbacks():
    phrases = []
    commands = []

    _handle_phrase(
        "alright",
        command_callback=lambda command, phrase: commands.append((command, phrase)),
        phrase_callback=lambda phrase: phrases.append(phrase),
    )

    assert phrases == []
    assert commands == []


def test_command_phrase_calls_callbacks():
    phrases = []
    commands = []

    _handle_phrase(
        "spot sit",
        command_callback=lambda command, phrase: commands.append((command, phrase)),
        phrase_callback=lambda phrase: phrases.append(phrase),
    )

    assert phrases == ["spot sit"]
    assert commands == [("SIT", "spot sit")]


def test_reject_long_irrelevant_transcript():
    assert transcript_rejection_reason("this is a long irrelevant sentence that should not become a robot command", None, None) == "too_long"


def test_reject_low_logprob_unless_exact_command():
    assert transcript_rejection_reason("alright", -1.2, None) == "low_logprob"
    assert transcript_rejection_reason("spot sit", -1.2, None) is None


def test_reject_no_speech_unless_exact_command():
    assert transcript_rejection_reason("alright", None, 0.5) == "no_speech"
    assert transcript_rejection_reason("spot sit", None, 0.5) is None


class FakeSoundDevice:
    def query_devices(self):
        return [
            {"name": "NVIDIA APE", "max_input_channels": 16},
            {"name": "Jabra SPEAK 510 USB", "max_input_channels": 1},
        ]


def test_audio_device_matching_by_name():
    assert _select_matching_input_device(FakeSoundDevice(), "jabra") == 1
    assert _select_matching_input_device(FakeSoundDevice(), "missing") is None


def test_audio_level_detection_does_not_acquire_inference(monkeypatch):
    calls = []
    monkeypatch.setattr(audio_in.event_logger, "event", lambda event_type, **payload: calls.append(event_type))
    audio = np.ones(100, dtype=np.float32) * 0.02

    assert _has_audio_level(audio, np)
    assert "audio_in_level" in calls
    assert "inference_acquired" not in calls


def test_speech_chunk_is_queued(monkeypatch):
    audio_in._speech_queue.clear()
    monkeypatch.setattr(
        audio_in,
        "config",
        SimpleNamespace(audio_speech_queue_max=2, audio_activity_hold_s=4.0),
    )

    _queue_speech_chunk(np.ones(10, dtype=np.float32))

    assert len(audio_in._speech_queue) == 1
    audio_in._speech_queue.clear()
    clear_audio_activity()
    clear_cancel_vision()
