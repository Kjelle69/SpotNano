from fastapi.testclient import TestClient

import app.audio_in as audio_in
import app.web_server as web_server
from app.config import config
from app.main import app
from app.state import SharedState


def test_default_vision_quality_restored_to_640_85():
    assert config.vision_image_max_width == 640
    assert config.vision_jpeg_quality == 85


def test_demo_scripts_use_logitech_webcam_input_device():
    voice = open("scripts/start_voice_demo.sh", encoding="utf-8").read()
    full = open("scripts/start_full_demo.sh", encoding="utf-8").read()

    assert 'AUDIO_DEVICE="${AUDIO_DEVICE:-auto}"' in voice
    assert 'AUDIO_DEVICE_MATCH="${AUDIO_DEVICE_MATCH:-logitech}"' in voice
    assert 'AUDIO_DEVICE="${AUDIO_DEVICE:-auto}"' in full
    assert 'AUDIO_DEVICE_MATCH="${AUDIO_DEVICE_MATCH:-logitech}"' in full


class FakeSoundDevice:
    def query_devices(self):
        return [
            {"name": "NVIDIA APE", "max_input_channels": 16, "default_samplerate": 48000},
            {"name": "Logitech Webcam C930e USB Audio", "max_input_channels": 2, "default_samplerate": 48000},
        ]


def test_audio_selected_device_diagnostics_populate_status(monkeypatch):
    state = SharedState()
    monkeypatch.setattr(audio_in, "shared_state", state)

    audio_in._log_selected_device(FakeSoundDevice(), 1, requested="24")

    status = state.snapshot()
    assert status["audio_input_device"] == 1
    assert status["audio_input_device_name"] == "Logitech Webcam C930e USB Audio"
    assert status["audio_input_max_channels"] == 2
    assert status["audio_input_default_samplerate"] == 48000.0
    assert status["audio_input_requested_samplerate"] == config.audio_sample_rate


def test_audio_device_match_selects_logitech_webcam():
    assert audio_in._select_matching_input_device(FakeSoundDevice(), "logitech") == 1


def test_mic_test_endpoint_returns_rms_peak(monkeypatch):
    monkeypatch.setattr(
        web_server,
        "record_mic_test",
        lambda duration_s=3.0: {
            "accepted": True,
            "status": "recorded",
            "device": 24,
            "device_name": "Logitech Webcam C930e USB Audio",
            "sample_rate": 16000,
            "duration_s": duration_s,
            "rms": 0.02,
            "peak": 0.3,
        },
    )

    client = TestClient(app)
    response = client.post("/api/audio/mic_test")
    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted"]
    assert payload["device"] == 24
    assert payload["rms"] == 0.02
    assert payload["peak"] == 0.3
