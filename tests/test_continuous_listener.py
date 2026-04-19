import threading
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
    listener.running = True
    
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


def test_start_reuses_alive_listener_thread(monkeypatch):
    listener = continuous_listener.ContinuousListener()
    listener.running = False
    listener.paused = True

    class AliveThread:
        def is_alive(self):
            return True

    alive_thread = AliveThread()
    listener.thread = alive_thread

    def fail_if_new_thread(*args, **kwargs):
        raise AssertionError("start() should not create a second listener thread")

    monkeypatch.setattr(continuous_listener.threading, "Thread", fail_if_new_thread)

    assert listener.start() is True
    assert listener.thread is alive_thread
    assert listener.running is True
    assert listener.paused is False


def test_listen_once_does_not_emit_when_stopped_mid_capture():
    heard = []
    listener = continuous_listener.ContinuousListener(on_command=heard.append)
    listener.microphone = _FakeMic()
    listener.running = True
    listener.paused = False

    fake_audio = SimpleNamespace(get_wav_data=lambda: b"wav")

    class FakeRecognizer:
        def listen(self, source, timeout=None, phrase_time_limit=None):
            listener.running = False
            return fake_audio

        def recognize_google(self, audio, language=None):
            return "Open calculator"

    listener.recognizer = FakeRecognizer()
    listener.offline_mode = False

    listener._listen_once()
    assert heard == []


def test_resume_is_ignored_when_listener_not_running():
    listener = continuous_listener.ContinuousListener()
    listener.running = False
    listener.paused = True

    resumed = listener.resume()

    assert resumed is False
    assert listener.paused is True


def test_stop_skips_join_when_called_from_listener_thread():
    listener = continuous_listener.ContinuousListener()
    listener.running = True
    listener.paused = False
    listener.thread = threading.current_thread()

    listener.stop()

    assert listener.running is False
    assert listener.paused is True
