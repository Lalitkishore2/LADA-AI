"""LADA Voice Stack

This package provides the voice pipeline components:
- STT: Faster-Whisper large-v3-turbo (primary) with fallbacks
- TTS: XTTS-v2 (voice cloning) with Kokoro/gTTS/pyttsx3 fallbacks
- Wake Word: openwakeword with "LADA WAKEUP" / "LADA TURN OFF"
- Alexa Hybrid: Auto-switch between Echo Dot and local voice
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .xtts_engine import XTTSEngine
    from .alexa_hybrid import AlexaHybridVoice

__all__ = ["XTTSEngine", "AlexaHybridVoice"]
