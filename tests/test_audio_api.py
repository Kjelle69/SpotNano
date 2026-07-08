from fastapi.testclient import TestClient

from app import audio_out
from app.main import app


def test_voice_text_spot_stop_is_motion_stop_without_latch(monkeypatch):
    monkeypatch.setattr(audio_out, "bark_ok", lambda: True)
    client = TestClient(app)
    client.post("/api/reset_stop")

    response = client.post("/api/audio/voice_text", json={"text": "spot stop"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted"]
    assert payload["command"] == "MOTION_STOP"
    assert payload["parsed_command"] == "MOTION_STOP"
    assert payload["command_result"]["command"] == "MOTION_STOP"

    status = client.get("/api/status").json()
    assert not status["emergency_stop"]
    assert status["stop_state"] == "motion_stop"

    sit = client.post("/api/command", data={"command": "SIT"}).json()
    assert sit["accepted"]


def test_voice_text_emergency_stop_activates_latched_estop(monkeypatch):
    monkeypatch.setattr(audio_out, "bark_warn", lambda: True)
    monkeypatch.setattr(audio_out, "bark_no", lambda: True)
    client = TestClient(app)
    client.post("/api/reset_stop")

    response = client.post("/api/audio/voice_text", json={"text": "spot emergency stop"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted"]
    assert payload["command"] == "APP_ESTOP"
    assert payload["parsed_command"] == "APP_ESTOP"
    assert payload["command_result"]["command"] == "APP_ESTOP"

    status = client.get("/api/status").json()
    assert status["emergency_stop"]
    assert status["stop_state"] == "app_estop"

    blocked = client.post("/api/command", data={"command": "SIT"}).json()
    assert not blocked["accepted"]
    assert blocked["status"] == "blocked"

    client.post("/api/reset_stop")


def test_voice_text_multiple_commands_rejected():
    client = TestClient(app)
    response = client.post("/api/audio/voice_text", json={"text": "Stop, spot sit, spot stand up."})
    assert response.status_code == 200
    payload = response.json()
    assert not payload["accepted"]
    assert payload["reason"] == "multiple_commands"


def test_voice_text_movement_goes_through_command_manager(monkeypatch):
    from app.command_manager import CommandResult
    from app import web_server

    calls = []

    def fake_handle(command, source="web"):
        calls.append((command, source))
        return CommandResult(True, command, "accepted", "fake")

    monkeypatch.setattr(web_server.command_manager, "handle", fake_handle)

    client = TestClient(app)
    response = client.post("/api/audio/voice_text", json={"text": "spot sit"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["parsed_command"] == "SIT"
    assert payload["command_result"]["status"] == "accepted"
    assert calls == [("SIT", "voice_text")]


def test_command_json_goes_through_command_manager(monkeypatch):
    from app.command_manager import CommandResult
    from app import web_server

    calls = []

    def fake_handle(command, source="web"):
        calls.append((command, source))
        return CommandResult(True, command, "accepted", "fake")

    monkeypatch.setattr(web_server.command_manager, "handle", fake_handle)

    client = TestClient(app)
    response = client.post("/api/command_json", json={"command": "STAND"})
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert calls == [("STAND", "web")]


def test_bark_endpoints(monkeypatch):
    calls = []

    monkeypatch.setattr(audio_out, "bark_ok", lambda: calls.append("ok") or True)
    monkeypatch.setattr(audio_out, "bark_no", lambda: calls.append("no") or True)
    monkeypatch.setattr(audio_out, "bark_warn", lambda: calls.append("warn") or True)
    monkeypatch.setattr(audio_out, "bark_snake", lambda: calls.append("snake") or True)

    client = TestClient(app)
    for endpoint in ["bark_ok", "bark_no", "bark_warn", "bark_snake"]:
        response = client.post(f"/api/audio/{endpoint}")
        assert response.status_code == 200
        assert response.json()["action"] == endpoint

    assert calls == ["ok", "no", "warn", "snake"]
