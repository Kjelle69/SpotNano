import app.audio_out as audio_out


def test_play_wav_uses_paplay(monkeypatch):
    calls = []

    monkeypatch.setattr(audio_out.shutil, "which", lambda name: "/usr/bin/paplay" if name == "paplay" else None)
    monkeypatch.setattr(audio_out.subprocess, "Popen", lambda args, **kwargs: calls.append(args))

    assert audio_out.play_wav("/tmp/test.wav")
    assert calls == [["paplay", "/tmp/test.wav"]]


def test_play_wav_falls_back_without_paplay(monkeypatch):
    bells = []

    monkeypatch.setattr(audio_out.shutil, "which", lambda name: None)
    monkeypatch.setattr(audio_out.sys.stdout, "write", lambda value: bells.append(value))
    monkeypatch.setattr(audio_out.sys.stdout, "flush", lambda: None)

    assert not audio_out.play_wav()
    assert bells == ["\a"]


def test_beep_and_bark_can_be_called_without_crashing(monkeypatch):
    calls = []

    class ImmediateThread:
        def __init__(self, target, daemon):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(audio_out.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(audio_out.shutil, "which", lambda name: None)
    monkeypatch.setattr(audio_out, "play_wav", lambda path=audio_out.DEFAULT_WAV_PATH: calls.append(path) or True)
    monkeypatch.setattr(audio_out, "play_audio_file", lambda path: calls.append(path) or True)

    assert audio_out.beep(count=2, delay_s=0)
    assert audio_out.bark()
    assert len(calls) == 3


def test_speak_uses_espeak_when_available(monkeypatch):
    calls = []

    monkeypatch.setattr(audio_out.shutil, "which", lambda name: "/usr/bin/espeak-ng" if name == "espeak-ng" else None)
    monkeypatch.setattr(audio_out.subprocess, "Popen", lambda args, **kwargs: calls.append(args))

    assert audio_out.speak("hej", lang="sv")
    assert calls == [["espeak-ng", "-v", "sv", "hej"]]


def test_bark_ok_uses_one_time_file(monkeypatch):
    calls = []

    monkeypatch.setattr(audio_out, "play_audio_file", lambda path: calls.append(path) or True)

    assert audio_out.bark_ok()
    assert calls == [str(audio_out.BARK_OK_PATH)]


def test_bark_no_uses_two_times_file(monkeypatch):
    calls = []

    monkeypatch.setattr(audio_out, "play_audio_file", lambda path: calls.append(path) or True)

    assert audio_out.bark_no()
    assert calls == [str(audio_out.BARK_NO_PATH)]


def test_bark_warn_uses_three_times_file(monkeypatch):
    calls = []

    monkeypatch.setattr(audio_out, "play_audio_file", lambda path: calls.append(path) or True)

    assert audio_out.bark_warn()
    assert calls == [str(audio_out.BARK_WARN_PATH)]


def test_bark_snake_uses_snake_file(monkeypatch):
    calls = []

    monkeypatch.setattr(audio_out, "play_audio_file", lambda path: calls.append(path) or True)

    assert audio_out.bark_snake()
    assert calls == [str(audio_out.BARK_SNAKE_PATH)]


def test_bark_keeps_backward_compatibility(monkeypatch):
    calls = []

    monkeypatch.setattr(audio_out, "bark_ok", lambda: calls.append("ok") or True)

    assert audio_out.bark()
    assert calls == ["ok"]


def test_missing_audio_file_fallback_does_not_crash(monkeypatch, tmp_path):
    calls = []

    monkeypatch.setattr(audio_out.shutil, "which", lambda name: "/usr/bin/espeak-ng" if name == "espeak-ng" else None)
    monkeypatch.setattr(audio_out.subprocess, "Popen", lambda args, **kwargs: calls.append(args))

    assert audio_out.play_audio_file(str(tmp_path / "missing.wav"))
    assert calls == [["espeak-ng", "-v", "sv", "-s", "220", "-p", "80", "voff"]]
