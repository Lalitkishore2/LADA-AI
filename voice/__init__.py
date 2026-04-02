"""LADA Voice Stack

This package provides the voice pipeline components:
- STT: Faster-Whisper large-v3-turbo (primary) with fallbacks
- TTS: XTTS-v2 (voice cloning) with Kokoro/gTTS/pyttsx3 fallbacks
- Wake Word: openwakeword with "LADA WAKEUP" / "LADA TURN OFF"
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .xtts_engine import XTTSEngine

__all__ = ["XTTSEngine"]
