"""Tests for modules/advanced_voice.py"""
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest


class TestWakeWordDetector:
    """Tests for WakeWordDetector class"""

    def test_init_default_wake_words(self, monkeypatch):
        monkeypatch.setattr("modules.advanced_voice.PYAUDIO_OK", False)
        monkeypatch.setattr("modules.advanced_voice.SPEECH_RECOGNITION_OK", False)
        monkeypatch.setattr("modules.advanced_voice.PVPORCUPINE_OK", False)

        from modules.advanced_voice import WakeWordDetector

        detector = WakeWordDetector()
        assert "lada" in detector.wake_words
        assert detector.is_listening is False

    def test_init_custom_wake_words(self, monkeypatch):
        monkeypatch.setattr("modules.advanced_voice.PYAUDIO_OK", False)
        monkeypatch.setattr("modules.advanced_voice.SPEECH_RECOGNITION_OK", False)
        monkeypatch.setattr("modules.advanced_voice.PVPORCUPINE_OK", False)

        from modules.advanced_voice import WakeWordDetector

        custom_words = ["hey assistant", "computer"]
        detector = WakeWordDetector(wake_words=custom_words)
        assert detector.wake_words == custom_words

    def test_init_with_callback(self, monkeypatch):
        monkeypatch.setattr("modules.advanced_voice.PYAUDIO_OK", False)
        monkeypatch.setattr("modules.advanced_voice.SPEECH_RECOGNITION_OK", False)
        monkeypatch.setattr("modules.advanced_voice.PVPORCUPINE_OK", False)

        from modules.advanced_voice import WakeWordDetector

        callback = MagicMock()
        detector = WakeWordDetector(callback=callback)
        assert detector.callback == callback

    def test_start_no_library(self, monkeypatch):
        monkeypatch.setattr("modules.advanced_voice.PYAUDIO_OK", False)
        monkeypatch.setattr("modules.advanced_voice.SPEECH_RECOGNITION_OK", False)
        monkeypatch.setattr("modules.advanced_voice.PVPORCUPINE_OK", False)

        from modules.advanced_voice import WakeWordDetector

        detector = WakeWordDetector()
        detector.start()
        assert detector.is_listening is False

    def test_start_without_pyaudio(self, monkeypatch):
        monkeypatch.setattr("modules.advanced_voice.PYAUDIO_OK", False)
        monkeypatch.setattr("modules.advanced_voice.SPEECH_RECOGNITION_OK", True)
        monkeypatch.setattr("modules.advanced_voice.PVPORCUPINE_OK", False)

        from modules.advanced_voice import WakeWordDetector

        detector = WakeWordDetector()
        detector.start()
        assert detector.is_listening is False

    def test_stop(self, monkeypatch):
        monkeypatch.setattr("modules.advanced_voice.PYAUDIO_OK", False)
        monkeypatch.setattr("modules.advanced_voice.SPEECH_RECOGNITION_OK", False)
        monkeypatch.setattr("modules.advanced_voice.PVPORCUPINE_OK", False)

        from modules.advanced_voice import WakeWordDetector

        detector = WakeWordDetector()
        detector.is_listening = True
        detector.stop()
        assert detector._stop_event.is_set()

    def test_stop_releases_audio_resources_and_joins_thread(self, monkeypatch):
        monkeypatch.setattr("modules.advanced_voice.PYAUDIO_OK", False)
        monkeypatch.setattr("modules.advanced_voice.SPEECH_RECOGNITION_OK", False)
        monkeypatch.setattr("modules.advanced_voice.PVPORCUPINE_OK", False)

        from modules.advanced_voice import WakeWordDetector

        class _FakeThread:
            def __init__(self):
                self._alive = True
                self.join_calls = []

            def is_alive(self):
                return self._alive

            def join(self, timeout=None):
                self.join_calls.append(timeout)
                self._alive = False

        class _FakeStream:
            def __init__(self):
                self.stop_called = False
                self.close_called = False

            def stop_stream(self):
                self.stop_called = True

            def close(self):
                self.close_called = True

        class _FakePyAudio:
            def __init__(self):
                self.terminated = False

            def terminate(self):
                self.terminated = True

        class _FakePorcupine:
            def __init__(self):
                self.deleted = False

            def delete(self):
                self.deleted = True

        detector = WakeWordDetector()
        fake_thread = _FakeThread()
        fake_stream = _FakeStream()
        fake_pa = _FakePyAudio()
        fake_porcupine = _FakePorcupine()

        detector._thread = fake_thread
        detector.audio_stream = fake_stream
        detector.pa = fake_pa
        detector.porcupine = fake_porcupine

        detector.stop()

        assert fake_thread.join_calls == [2]
        assert fake_stream.stop_called is True
        assert fake_stream.close_called is True
        assert fake_pa.terminated is True
        assert fake_porcupine.deleted is True
        assert detector._thread is None
        assert detector.audio_stream is None
        assert detector.pa is None
        assert detector.porcupine is None

    def test_stop_from_same_thread_does_not_join_self(self, monkeypatch):
        monkeypatch.setattr("modules.advanced_voice.PYAUDIO_OK", False)
        monkeypatch.setattr("modules.advanced_voice.SPEECH_RECOGNITION_OK", False)
        monkeypatch.setattr("modules.advanced_voice.PVPORCUPINE_OK", False)

        from modules.advanced_voice import WakeWordDetector

        detector = WakeWordDetector()
        detector._thread = threading.current_thread()

        detector.stop()
        assert detector._stop_event.is_set()


class TestContinuousListener:
    """Tests for ContinuousListener class"""

    def test_init(self, monkeypatch):
        monkeypatch.setattr("modules.advanced_voice.PYAUDIO_OK", False)
        monkeypatch.setattr("modules.advanced_voice.SPEECH_RECOGNITION_OK", False)
        monkeypatch.setattr("modules.advanced_voice.PVPORCUPINE_OK", False)
        monkeypatch.setattr("modules.advanced_voice.WHISPER_OK", False)

        from modules.advanced_voice import ContinuousListener

        listener = ContinuousListener()
        assert listener.is_listening is False

    def test_init_with_whisper(self, monkeypatch):
        monkeypatch.setattr("modules.advanced_voice.PYAUDIO_OK", False)
        monkeypatch.setattr("modules.advanced_voice.SPEECH_RECOGNITION_OK", False)
        monkeypatch.setattr("modules.advanced_voice.PVPORCUPINE_OK", False)
        monkeypatch.setattr("modules.advanced_voice.WHISPER_OK", False)

        from modules.advanced_voice import ContinuousListener

        listener = ContinuousListener(use_whisper=True)
        # Whisper not available, so use_whisper should be False
        assert listener.use_whisper is False

    def test_stop(self, monkeypatch):
        monkeypatch.setattr("modules.advanced_voice.PYAUDIO_OK", False)
        monkeypatch.setattr("modules.advanced_voice.SPEECH_RECOGNITION_OK", False)
        monkeypatch.setattr("modules.advanced_voice.PVPORCUPINE_OK", False)
        monkeypatch.setattr("modules.advanced_voice.WHISPER_OK", False)

        from modules.advanced_voice import ContinuousListener

        listener = ContinuousListener()
        listener.is_listening = True
        listener.stop()
        assert listener._stop_event.is_set()

    def test_command_queue(self, monkeypatch):
        monkeypatch.setattr("modules.advanced_voice.PYAUDIO_OK", False)
        monkeypatch.setattr("modules.advanced_voice.SPEECH_RECOGNITION_OK", False)
        monkeypatch.setattr("modules.advanced_voice.PVPORCUPINE_OK", False)
        monkeypatch.setattr("modules.advanced_voice.WHISPER_OK", False)

        from modules.advanced_voice import ContinuousListener

        listener = ContinuousListener()
        assert listener.command_queue is not None
        # Should be empty initially
        assert listener.command_queue.empty()

    def test_start_does_not_spawn_duplicate_threads(self, monkeypatch):
        monkeypatch.setattr("modules.advanced_voice.PYAUDIO_OK", False)
        monkeypatch.setattr("modules.advanced_voice.SPEECH_RECOGNITION_OK", True)
        monkeypatch.setattr("modules.advanced_voice.PVPORCUPINE_OK", False)
        monkeypatch.setattr("modules.advanced_voice.WHISPER_OK", False)

        class _FakeRecognizer:
            pass

        class _FakeSR:
            @staticmethod
            def Recognizer():
                return _FakeRecognizer()

        thread_instances = []

        class _FakeThread:
            def __init__(self, *args, **kwargs):
                self._alive = False
                thread_instances.append(self)

            def start(self):
                self._alive = True

            def is_alive(self):
                return self._alive

            def join(self, timeout=None):
                self._alive = False

        monkeypatch.setattr("modules.advanced_voice.sr", _FakeSR(), raising=False)
        monkeypatch.setattr("modules.advanced_voice.threading.Thread", _FakeThread)

        from modules.advanced_voice import ContinuousListener

        listener = ContinuousListener()
        listener.start()
        listener.start()
        assert len(thread_instances) == 1

        # Simulate inconsistent state where running flag dropped while thread is still alive.
        listener.is_listening = False
        listener.start()
        assert len(thread_instances) == 1

    def test_stop_from_same_thread_does_not_join_self(self, monkeypatch):
        monkeypatch.setattr("modules.advanced_voice.PYAUDIO_OK", False)
        monkeypatch.setattr("modules.advanced_voice.SPEECH_RECOGNITION_OK", False)
        monkeypatch.setattr("modules.advanced_voice.PVPORCUPINE_OK", False)
        monkeypatch.setattr("modules.advanced_voice.WHISPER_OK", False)

        from modules.advanced_voice import ContinuousListener

        listener = ContinuousListener()
        listener._thread = threading.current_thread()

        listener.stop()
        assert listener._stop_event.is_set()


class TestVoiceModuleFlags:
    """Tests for voice module feature flags"""

    def test_pyaudio_flag(self, monkeypatch):
        monkeypatch.setattr("modules.advanced_voice.PYAUDIO_OK", True)

        from modules import advanced_voice

        assert hasattr(advanced_voice, "PYAUDIO_OK")

    def test_speech_recognition_flag(self, monkeypatch):
        monkeypatch.setattr("modules.advanced_voice.SPEECH_RECOGNITION_OK", True)

        from modules import advanced_voice

        assert hasattr(advanced_voice, "SPEECH_RECOGNITION_OK")

    def test_whisper_flag(self, monkeypatch):
        monkeypatch.setattr("modules.advanced_voice.WHISPER_OK", False)

        from modules import advanced_voice

        assert hasattr(advanced_voice, "WHISPER_OK")
