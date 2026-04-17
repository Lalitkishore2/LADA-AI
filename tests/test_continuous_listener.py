from types import SimpleNamespace

import modules.continuous_listener as continuous_listener


class _FakeMic:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return False


def test_start_returns_false_when_speech_recognition_unavailable(monkeypatch):
    monkeypatch.setattr(continuous_listener, "SR_AVAILABLE", False)
    listener = continuous_listener.ContinuousListener()
    assert listener.start() is False


def test_listen_once_online_success_triggers_callback(monkeypatch):
    heard = []

    def on_command(text):
        heard.append(text)

    listener = continuous_listener.ContinuousListener(on_command=on_command)
    listener.microphone = _FakeMic()

    fake_audio = SimpleNamespace(get_wav_data=lambda: b"wav")

    class FakeRecognizer:
        def listen(self, source, timeout=None, phrase_time_limit=None):
            return fake_audio

        def recognize_google(self, audio, language=None):
            return "Hello LADA"

    listener.recognizer = FakeRecognizer()
    listener.offline_mode = False

    listener._listen_once()
    assert heard == ["Hello LADA"]


def test_invalid_mic_device_index_ignored(monkeypatch):
    monkeypatch.setenv("LADA_MIC_DEVICE_INDEX", "invalid")
    listener = continuous_listener.ContinuousListener()
    assert listener.mic_device_index is None
