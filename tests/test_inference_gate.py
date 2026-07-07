import time

from app.inference_gate import (
    acquire_inference,
    clear_audio_activity,
    clear_cancel_vision,
    get_current_owner,
    is_audio_activity_active,
    mark_audio_activity,
    request_cancel_vision,
    should_cancel_vision,
)


def test_inference_lock_skip_behavior():
    with acquire_inference("first", timeout=0.0) as first:
        assert first
        assert get_current_owner() == "first"
        with acquire_inference("second", timeout=0.0) as second:
            assert not second

    with acquire_inference("third", timeout=0.0) as third:
        assert third


def test_audio_activity_hold_and_vision_cancel():
    clear_audio_activity()
    clear_cancel_vision()
    mark_audio_activity(duration_s=0.2)
    assert is_audio_activity_active()
    assert should_cancel_vision()
    time.sleep(0.25)
    clear_cancel_vision()
    clear_audio_activity()
    assert not is_audio_activity_active()
    assert not should_cancel_vision()


def test_audio_requesting_lock_while_vision_owns_requests_cancel():
    clear_audio_activity()
    clear_cancel_vision()
    with acquire_inference("vision_moondream", timeout=0.0) as vision:
        assert vision
        with acquire_inference("audio_whisper", priority="high", timeout=0.0) as audio:
            assert not audio
        assert should_cancel_vision()
    clear_cancel_vision()
