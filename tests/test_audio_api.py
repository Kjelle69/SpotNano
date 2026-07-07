from fastapi.testclient import TestClient

from app import audio_out
from app.main import app


def test_voice_text_stopp_activates_emergency_stop(monkeypatch):
    monkeypatch.setattr(audio_out, "bark_warn", lambda: True)
    monkeypatch.setattr(audio_out, "bark_no", lambda: True)
    client = TestClient(app)
    client.post("/api/reset_stop")

    response = client.post("/api/audio/voice_text", json={"text": "stopp"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["accepted"]
    assert payload["command"] == "STOP"
    assert payload["parsed_command"] == "STOP"
    assert payload["command_result"]["command"] == "STOP"

    status = client.get("/api/status").json()
    assert status["emergency_stop"]

    blocked = client.post("/api/command", data={"command": "MOVE_FORWARD_SHORT"}).json()
    assert not blocked["accepted"]
    assert blocked["status"] == "blocked"

    client.post("/api/reset_stop")


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
