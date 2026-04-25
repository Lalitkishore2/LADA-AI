from types import SimpleNamespace

import pytest

import modules.hybrid_stt as hybrid_stt


def test_transcribe_file_returns_none_when_no_engines(monkeypatch):
    monkeypatch.setattr(hybrid_stt, "FASTER_WHISPER_AVAILABLE", False)
    monkeypatch.setattr(hybrid_stt, "WHISPER_AVAILABLE", False)
    monkeypatch.setattr(hybrid_stt, "SR_AVAILABLE", False)

    r = hybrid_stt.HybridSpeechRecognizer()
    assert r.is_available() is False
    assert r.transcribe_file("dummy.wav") is None


def test_transcribe_file_prefers_faster_whisper(monkeypatch):
    r = hybrid_stt.HybridSpeechRecognizer(prefer="faster-whisper")

    class Seg:
        def __init__(self, text):
            self.text = text

    fake_info = SimpleNamespace(model="tiny")

    def fake_transcribe(path, language=None):
        assert path == "audio.wav"
        return [Seg("hello"), Seg("world")], fake_info

    monkeypatch.setattr(r, "_load_faster_whisper", lambda: True)
    r._fw_model = SimpleNamespace(transcribe=fake_transcribe)

    out = r.transcribe_file("audio.wav", language="en")
    assert out is not None
    assert out.text == "hello world"
    assert out.engine.startswith("faster-whisper")


def test_transcribe_file_falls_back_to_whisper(monkeypatch):
    r = hybrid_stt.HybridSpeechRecognizer(prefer="faster-whisper")

    monkeypatch.setattr(r, "_transcribe_faster_whisper", lambda path, language=None: None)
    monkeypatch.setattr(
        r,
        "_transcribe_whisper",
        lambda path, language=None: hybrid_stt.TranscriptionResult(text="ok", engine="whisper:tiny"),
    )

    out = r.transcribe_file("audio.wav", language="en")
    assert out is not None
    assert out.text == "ok"
    assert out.engine == "whisper:tiny"
