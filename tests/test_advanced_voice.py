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

    def test_stop(self, monkeypatch):
        monkeypatch.setattr("modules.advanced_voice.PYAUDIO_OK", False)
        monkeypatch.setattr("modules.advanced_voice.SPEECH_RECOGNITION_OK", False)
        monkeypatch.setattr("modules.advanced_voice.PVPORCUPINE_OK", False)

        from modules.advanced_voice import WakeWordDetector

        detector = WakeWordDetector()
        detector.is_listening = True
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
