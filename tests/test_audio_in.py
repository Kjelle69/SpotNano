from app.audio_in import (
    _handle_phrase,
    _has_audio_level,
    _queue_speech_chunk,
    _select_matching_input_device,
    _is_audio_input_suppressed,
    collapse_repeated_words,
    command_phrases,
    estimate_stereo_direction,
    extract_wake_command,
    normalize_text,
    parse_voice_command,
    parse_voice_command_with_reason,
    reset_audio_direction_state,
    stereo_to_mono,
    transcript_rejection_reason,
)
import app.audio_in as audio_in
import numpy as np
from types import SimpleNamespace
from app.inference_gate import clear_audio_activity, clear_cancel_vision
from app.state import SharedState


def test_parse_stopp():
    assert parse_voice_command("stopp") is None


def test_parse_spot_stopp():
    assert parse_voice_command("spot stopp") == "MOTION_STOP"


def test_parse_spot_sit():
    assert parse_voice_command("spot sit") == "SIT"


def test_parse_spot_sit_down():
    assert parse_voice_command("spot sit down") == "SIT"


def test_parse_spot_sitt():
    assert parse_voice_command("spot sitt") == "SIT"


def test_parse_spot_seat_with_punctuation():
    assert parse_voice_command("spot, seat.") == "SIT"


def test_parse_spot_satt_dig():
    assert parse_voice_command("spot sätt dig") == "SIT"
    assert parse_voice_command("spot sat dig") == "SIT"


def test_parse_spot_stand():
    assert parse_voice_command("spot stand") == "STAND"


def test_parse_spot_stand_up():
    assert parse_voice_command("spot stand up") == "STAND"


def test_parse_stand_up_without_wake_word_is_rejected():
    command, reason = parse_voice_command_with_reason("Stand up.")
    assert command is None
    assert reason == "missing_wake_word"


def test_parse_spot_sta():
    assert parse_voice_command("spot stå") == "STAND"


def test_parse_spot_res_dig_and_sta_upp():
    assert parse_voice_command("spot res dig") == "STAND"
    assert parse_voice_command("spot sta upp") == "STAND"


def test_parse_bare_sta_requires_wake_word():
    assert parse_voice_command("stå") is None


def test_parse_spot_go():
    assert parse_voice_command("spot go") == "MOVE_FORWARD_SHORT"


def test_parse_spot_move_forward():
    assert parse_voice_command("spot move forward") == "MOVE_FORWARD_SHORT"


def test_parse_spot_framat():
    assert parse_voice_command("spot framåt") == "MOVE_FORWARD_SHORT"


def test_parse_spot_move_back():
    assert parse_voice_command("spot move back") == "MOVE_BACKWARD_SHORT"


def test_parse_spot_bakat():
    assert parse_voice_command("spot bakåt") == "MOVE_BACKWARD_SHORT"


def test_parse_spot_vanster_hoger():
    assert parse_voice_command("spot vänster") == "ROTATE_LEFT_SHORT"
    assert parse_voice_command("spot höger") == "ROTATE_RIGHT_SHORT"


def test_parse_kom_requires_wake_word():
    assert parse_voice_command("kom") is None


def test_parse_come():
    assert parse_voice_command("come") == "APPROACH_BLUE_SNAKE"


def test_parse_spot_come():
    assert parse_voice_command("spot come") == "APPROACH_BLUE_SNAKE"


def test_parse_spot_kom():
    assert parse_voice_command("spot kom") == "APPROACH_BLUE_SNAKE"


def test_parse_unknown_returns_none():
    assert parse_voice_command("kan du dansa lite") is None


def test_parse_multiple_commands_rejected():
    command, reason = parse_voice_command_with_reason("Stop, spot sit, spot stand up.")
    assert command is None
    assert reason == "multiple_commands"


def test_parse_stopp_inside_phrase_triggers_stop():
    assert parse_voice_command("say stop now") is None


def test_parse_stoppa_triggers_stop():
    assert parse_voice_command("emergency stop") == "APP_ESTOP"


def test_parse_sto_fails_safe_to_stop():
    assert parse_voice_command("stop stop stop") is None


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
    assert "spot stop" in phrases
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


def test_audio_input_suppressed_during_audio_out_window(monkeypatch):
    state = SharedState()
    events = []
    monkeypatch.setattr(audio_in, "shared_state", state)
    monkeypatch.setattr(audio_in.event_logger, "event", lambda event_type, **payload: events.append(event_type))
    state.update(audio_out_suppress_until=100.0)

    assert _is_audio_input_suppressed(99.0)
    assert not _is_audio_input_suppressed(101.0)
    assert state.snapshot()["last_rejected_voice_reason"] == "audio_out_suppression"
    assert "audio_in_suppressed_during_audio_out" in events


def test_stereo_direction_left_louder():
    reset_audio_direction_state()
    stereo = np.column_stack(
        [
            np.ones(1000, dtype=np.float32) * 0.2,
            np.ones(1000, dtype=np.float32) * 0.05,
        ]
    )

    result = estimate_stereo_direction(stereo, np, noise_gate_rms=0.01, db_threshold=3.0, smoothing_chunks=1)

    assert result["direction"] == "LEFT"
    assert result["lr_db"] < -3.0


def test_stereo_direction_right_louder():
    reset_audio_direction_state()
    stereo = np.column_stack(
        [
            np.ones(1000, dtype=np.float32) * 0.05,
            np.ones(1000, dtype=np.float32) * 0.2,
        ]
    )

    result = estimate_stereo_direction(stereo, np, noise_gate_rms=0.01, db_threshold=3.0, smoothing_chunks=1)

    assert result["direction"] == "RIGHT"
    assert result["lr_db"] > 3.0


def test_stereo_direction_equal_channels_center():
    reset_audio_direction_state()
    stereo = np.column_stack(
        [
            np.ones(1000, dtype=np.float32) * 0.1,
            np.ones(1000, dtype=np.float32) * 0.1,
        ]
    )

    result = estimate_stereo_direction(stereo, np, noise_gate_rms=0.01, db_threshold=3.0, smoothing_chunks=1)

    assert result["direction"] == "CENTER"
    assert abs(result["lr_db"]) < 0.1


def test_stereo_direction_low_level_is_quiet():
    reset_audio_direction_state()
    stereo = np.column_stack(
        [
            np.ones(1000, dtype=np.float32) * 0.001,
            np.ones(1000, dtype=np.float32) * 0.002,
        ]
    )

    result = estimate_stereo_direction(stereo, np, noise_gate_rms=0.01, db_threshold=3.0, smoothing_chunks=1)

    assert result["direction"] == "quiet"
    assert result["confidence"] == 0.0


def test_stereo_input_mixes_to_mono_for_whisper():
    stereo = np.column_stack(
        [
            np.ones(4, dtype=np.float32) * 0.2,
            np.ones(4, dtype=np.float32) * 0.4,
        ]
    )

    mono = stereo_to_mono(stereo, np)

    assert mono.shape == (4,)
    assert np.allclose(mono, np.ones(4, dtype=np.float32) * 0.3)
