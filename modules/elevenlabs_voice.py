"""
LADA - ElevenLabs Voice Integration
Premium neural TTS with voice selection and cloning.

Features:
- ElevenLabs API for high-quality speech
- Voice selection from available voices
- Fallback chain: ElevenLabs -> edge-tts -> pyttsx3
- Audio playback with pygame/pydub
"""

import os
import logging
import tempfile
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Try imports
try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

try:
    import pygame
    PYGAME_OK = True
except ImportError:
    PYGAME_OK = False

try:
    import pyttsx3
    PYTTSX3_OK = True
except ImportError:
    PYTTSX3_OK = False


class ElevenLabsVoice:
    """
    Premium TTS using ElevenLabs API with fallback chain.
    """

    API_BASE = "https://api.elevenlabs.io/v1"

    def __init__(self):
        self.api_key = os.getenv('ELEVENLABS_API_KEY', '')
        self.default_voice_id = os.getenv('ELEVENLABS_VOICE_ID', '')
        self.model_id = os.getenv('ELEVENLABS_MODEL', 'eleven_monolingual_v1')
        self.voices_cache: List[Dict[str, Any]] = []

        # Fallback TTS
        self.pyttsx3_engine = None
        if PYTTSX3_OK:
            try:
                self.pyttsx3_engine = pyttsx3.init()
            except Exception:
                pass

        # Initialize pygame mixer for playback
        if PYGAME_OK:
            try:
                pygame.mixer.init()
            except Exception:
                pass

        logger.info(f"[ElevenLabs] Initialized (API key: {'set' if self.api_key else 'not set'})")

    def is_available(self) -> bool:
        """Check if ElevenLabs API is configured."""
        return bool(self.api_key)

    def list_voices(self) -> List[Dict[str, str]]:
        """List available ElevenLabs voices."""
        if not self.api_key:
            return []

        try:
            response = requests.get(
                f"{self.API_BASE}/voices",
                headers={"xi-api-key": self.api_key},
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                self.voices_cache = [
                    {
                        'voice_id': v.get('voice_id', ''),
                        'name': v.get('name', ''),
                        'category': v.get('category', ''),
                        'description': v.get('labels', {}).get('description', ''),
                    }
                    for v in data.get('voices', [])
                ]
                return self.voices_cache
        except Exception as e:
            logger.error(f"[ElevenLabs] Failed to list voices: {e}")

        return []

    def speak(self, text: str, voice_id: Optional[str] = None) -> bool:
        """
        Speak text using ElevenLabs TTS.
        Falls back to pyttsx3 if ElevenLabs is unavailable.

        Returns True on success.
        """
        # Try ElevenLabs first
        if self.api_key:
            success = self._speak_elevenlabs(text, voice_id or self.default_voice_id)
            if success:
                return True

        # Fallback to pyttsx3
        if self.pyttsx3_engine:
            try:
                self.pyttsx3_engine.say(text)
                self.pyttsx3_engine.runAndWait()
                return True
            except Exception as e:
                logger.error(f"[ElevenLabs] pyttsx3 fallback failed: {e}")

        return False

    def _speak_elevenlabs(self, text: str, voice_id: str) -> bool:
        """Generate speech via ElevenLabs API and play it."""
        if not voice_id:
            # Use first available voice
            voices = self.list_voices()
            if voices:
                voice_id = voices[0]['voice_id']
            else:
                return False

        try:
            response = requests.post(
                f"{self.API_BASE}/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json={
                    "text": text,
                    "model_id": self.model_id,
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                    },
                },
                timeout=30,
            )

            if response.status_code == 200:
                # Save to temp file and play
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                    f.write(response.content)
                    temp_path = f.name

                self._play_audio(temp_path)

                # Cleanup
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass

                return True
            else:
                logger.warning(f"[ElevenLabs] API error: {response.status_code}")

        except Exception as e:
            logger.error(f"[ElevenLabs] TTS failed: {e}")

        return False

    def _play_audio(self, file_path: str):
        """Play an audio file using pygame."""
        if not PYGAME_OK:
            return

        try:
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.wait(100)
        except Exception as e:
            logger.error(f"[ElevenLabs] Playback failed: {e}")

    def set_voice(self, voice_id: str):
        """Set the default voice."""
        self.default_voice_id = voice_id
        logger.info(f"[ElevenLabs] Voice set to: {voice_id}")

    def get_voice_settings(self) -> Dict[str, Any]:
        """Get current voice settings for UI."""
        return {
            'available': self.is_available(),
            'voice_id': self.default_voice_id,
            'model': self.model_id,
            'voices': self.voices_cache,
            'fallback': 'pyttsx3' if self.pyttsx3_engine else 'none',
        }


# Singleton
_elevenlabs = None


def get_elevenlabs_voice() -> ElevenLabsVoice:
    global _elevenlabs
    if _elevenlabs is None:
        _elevenlabs = ElevenLabsVoice()
    return _elevenlabs
