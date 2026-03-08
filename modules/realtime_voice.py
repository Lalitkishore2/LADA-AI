"""
LADA v11.0 - LiveKit Real-Time Voice Engine
Ultra-low-latency bidirectional voice with barge-in support.

Uses LiveKit Agents SDK for real-time audio streaming,
voice activity detection, and natural conversation flow.
Falls back to traditional STT/TTS pipeline when LiveKit unavailable.
"""

import os
import json
import asyncio
import logging
import time
import threading
import queue
from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# Conditional imports
try:
    from livekit import agents, rtc
    from livekit.agents import (
        AutoSubscribe, JobContext, WorkerOptions,
        llm as lk_llm, stt as lk_stt, tts as lk_tts,
        voice_assistant,
    )
    LIVEKIT_OK = True
except ImportError:
    LIVEKIT_OK = False

try:
    from livekit.plugins import deepgram, silero, cartesia, openai as lk_openai
    LIVEKIT_PLUGINS_OK = True
except ImportError:
    LIVEKIT_PLUGINS_OK = False

try:
    import speech_recognition as sr
    SR_OK = True
except ImportError:
    SR_OK = False

try:
    import pyttsx3
    PYTTSX3_OK = True
except ImportError:
    PYTTSX3_OK = False


class VoiceState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    BARGE_IN = "barge_in"  # User interrupted mid-speech


@dataclass
class VoiceConfig:
    """Voice engine configuration."""
    # LiveKit settings
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    room_name: str = "lada-voice"

    # STT settings
    stt_provider: str = "google"  # "google", "deepgram", "whisper"
    stt_language: str = "en-US"

    # TTS settings
    tts_provider: str = "pyttsx3"  # "pyttsx3", "elevenlabs", "cartesia"
    tts_voice: str = ""
    tts_rate: int = 160
    tts_volume: float = 0.9

    # Barge-in settings
    barge_in_enabled: bool = True
    barge_in_threshold_ms: int = 600  # Min speech duration to trigger barge-in
    vad_sensitivity: float = 0.5  # Voice activity detection sensitivity

    # Performance
    min_endpointing_delay_ms: int = 300
    max_silence_ms: int = 1500


class BargeInDetector:
    """
    Detects when user starts speaking while TTS is playing.
    Implements smart barge-in with configurable threshold.
    """

    def __init__(self, threshold_ms: int = 600):
        self.threshold_ms = threshold_ms
        self._speech_start: Optional[float] = None
        self._is_tts_playing = False
        self._barge_in_count = 0

    def on_tts_start(self):
        self._is_tts_playing = True

    def on_tts_end(self):
        self._is_tts_playing = False
        self._speech_start = None

    def on_speech_detected(self) -> bool:
        """
        Called when voice activity is detected.
        Returns True if this constitutes a barge-in.
        """
        if not self._is_tts_playing:
            return False

        now = time.time() * 1000  # ms

        if self._speech_start is None:
            self._speech_start = now
            return False

        duration = now - self._speech_start
        if duration >= self.threshold_ms:
            self._barge_in_count += 1
            logger.info(f"[Voice] Barge-in detected (#{self._barge_in_count}, {duration:.0f}ms)")
            return True

        return False

    def reset(self):
        self._speech_start = None

    @property
    def stats(self) -> Dict[str, Any]:
        return {"barge_in_count": self._barge_in_count}


class TraditionalVoiceEngine:
    """
    Fallback voice engine using SpeechRecognition + pyttsx3.
    Enhanced with barge-in support via threading.
    """

    def __init__(self, config: VoiceConfig):
        self.config = config
        self.state = VoiceState.IDLE
        self._tts_engine = None
        self._recognizer = None
        self._barge_in = BargeInDetector(config.barge_in_threshold_ms)
        self._stop_speaking = threading.Event()
        self._on_transcript: Optional[Callable] = None
        self._on_state_change: Optional[Callable] = None
        self._tts_lock = threading.Lock()

        self._init_engines()

    def _init_engines(self):
        """Initialize STT and TTS engines."""
        if SR_OK:
            self._recognizer = sr.Recognizer()
            self._recognizer.dynamic_energy_threshold = True
            self._recognizer.energy_threshold = 300

        if PYTTSX3_OK:
            try:
                self._tts_engine = pyttsx3.init()
                self._tts_engine.setProperty('rate', self.config.tts_rate)
                self._tts_engine.setProperty('volume', self.config.tts_volume)
            except Exception as e:
                logger.error(f"[Voice] pyttsx3 init error: {e}")

    def set_callbacks(self, on_transcript: Optional[Callable] = None,
                      on_state_change: Optional[Callable] = None):
        """Set callback functions for events."""
        self._on_transcript = on_transcript
        self._on_state_change = on_state_change

    def _set_state(self, state: VoiceState):
        old = self.state
        self.state = state
        if self._on_state_change and old != state:
            self._on_state_change(state)

    def listen_once(self, timeout: int = 10) -> Optional[str]:
        """Listen for a single voice command."""
        if not SR_OK or not self._recognizer:
            return None

        self._set_state(VoiceState.LISTENING)
        try:
            with sr.Microphone() as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self._recognizer.listen(source, timeout=timeout, phrase_time_limit=15)

            self._set_state(VoiceState.PROCESSING)

            # Try Google STT
            try:
                text = self._recognizer.recognize_google(audio, language=self.config.stt_language)
                logger.info(f"[Voice] Recognized: {text}")
                if self._on_transcript:
                    self._on_transcript(text)
                return text
            except sr.UnknownValueError:
                return None
            except sr.RequestError as e:
                logger.error(f"[Voice] Google STT error: {e}")
                return None

        except sr.WaitTimeoutError:
            return None
        except Exception as e:
            logger.error(f"[Voice] Listen error: {e}")
            return None
        finally:
            self._set_state(VoiceState.IDLE)

    def speak(self, text: str, interruptible: bool = True):
        """
        Speak text with optional barge-in support.

        If interruptible=True, speech can be stopped mid-sentence
        when the user starts speaking.
        """
        if not text or not self._tts_engine:
            return

        self._stop_speaking.clear()
        self._barge_in.on_tts_start()
        self._set_state(VoiceState.SPEAKING)

        def _speak_thread():
            with self._tts_lock:
                try:
                    if interruptible:
                        # Speak sentence by sentence for interruptibility
                        sentences = self._split_sentences(text)
                        for sentence in sentences:
                            if self._stop_speaking.is_set():
                                logger.info("[Voice] Speech interrupted by user")
                                self._set_state(VoiceState.BARGE_IN)
                                break
                            self._tts_engine.say(sentence)
                            self._tts_engine.runAndWait()
                    else:
                        self._tts_engine.say(text)
                        self._tts_engine.runAndWait()
                except Exception as e:
                    logger.error(f"[Voice] TTS error: {e}")
                finally:
                    self._barge_in.on_tts_end()
                    if self.state != VoiceState.BARGE_IN:
                        self._set_state(VoiceState.IDLE)

        thread = threading.Thread(target=_speak_thread, daemon=True)
        thread.start()

    def interrupt(self):
        """Interrupt current speech (barge-in)."""
        self._stop_speaking.set()
        try:
            if self._tts_engine:
                self._tts_engine.stop()
        except Exception:
            pass

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences for interruptible TTS."""
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s for s in sentences if s.strip()]


class LiveKitVoiceEngine:
    """
    LiveKit-based real-time voice engine.
    Ultra-low-latency bidirectional voice with VAD and barge-in.
    """

    def __init__(self, config: VoiceConfig):
        self.config = config
        self.state = VoiceState.IDLE
        self._barge_in = BargeInDetector(config.barge_in_threshold_ms)
        self._on_transcript: Optional[Callable] = None
        self._on_state_change: Optional[Callable] = None
        self._assistant = None
        self._room = None

    def set_callbacks(self, on_transcript: Optional[Callable] = None,
                      on_state_change: Optional[Callable] = None):
        self._on_transcript = on_transcript
        self._on_state_change = on_state_change

    async def connect(self, process_query_fn: Optional[Callable] = None):
        """
        Connect to LiveKit room and start voice assistant.

        process_query_fn: async function that takes user text and returns response text
        """
        if not LIVEKIT_OK:
            raise RuntimeError("LiveKit SDK not installed")

        self._room = rtc.Room()

        try:
            await self._room.connect(
                self.config.livekit_url,
                self.config.livekit_api_key,
            )
            logger.info(f"[Voice] Connected to LiveKit room: {self.config.room_name}")

            # Setup VAD
            vad = None
            if LIVEKIT_PLUGINS_OK:
                try:
                    vad = silero.VAD.load(
                        min_speech_duration=0.1,
                        min_silence_duration=self.config.max_silence_ms / 1000,
                    )
                except Exception:
                    pass

            # Setup STT
            stt_engine = None
            if LIVEKIT_PLUGINS_OK:
                try:
                    stt_engine = deepgram.STT()
                except Exception:
                    pass

            # Setup TTS
            tts_engine = None
            if LIVEKIT_PLUGINS_OK:
                try:
                    tts_engine = cartesia.TTS()
                except Exception:
                    try:
                        tts_engine = lk_openai.TTS()
                    except Exception:
                        pass

            # Create voice assistant pipeline
            if stt_engine and tts_engine:
                self._assistant = voice_assistant.VoiceAssistant(
                    vad=vad,
                    stt=stt_engine,
                    tts=tts_engine,
                    min_endpointing_delay=self.config.min_endpointing_delay_ms / 1000,
                    allow_interruptions=self.config.barge_in_enabled,
                    interrupt_speech_duration=self.config.barge_in_threshold_ms / 1000,
                )

                @self._assistant.on("user_speech_committed")
                def on_speech(ev):
                    text = ev.get("text", "")
                    if text and self._on_transcript:
                        self._on_transcript(text)

                self._assistant.start(self._room)
                logger.info("[Voice] LiveKit voice assistant started")

        except Exception as e:
            logger.error(f"[Voice] LiveKit connection failed: {e}")
            raise

    async def disconnect(self):
        """Disconnect from LiveKit room."""
        if self._room:
            await self._room.disconnect()
            self._room = None

    def interrupt(self):
        """Interrupt current speech."""
        if self._assistant and hasattr(self._assistant, 'interrupt'):
            self._assistant.interrupt()


class RealTimeVoiceEngine:
    """
    Unified voice engine with LiveKit primary and traditional fallback.

    Automatically selects the best available voice backend.
    """

    def __init__(self, config: Optional[VoiceConfig] = None):
        self.config = config or VoiceConfig()
        self._livekit_engine: Optional[LiveKitVoiceEngine] = None
        self._traditional_engine: Optional[TraditionalVoiceEngine] = None
        self._active_engine: str = "none"
        self._on_transcript: Optional[Callable] = None
        self._on_state_change: Optional[Callable] = None

        self._init_best_engine()

    def _init_best_engine(self):
        """Initialize the best available voice engine."""
        # Try LiveKit first
        if LIVEKIT_OK and self.config.livekit_url:
            try:
                self._livekit_engine = LiveKitVoiceEngine(self.config)
                self._active_engine = "livekit"
                logger.info("[Voice] Using LiveKit real-time voice engine")
                return
            except Exception as e:
                logger.warning(f"[Voice] LiveKit init failed: {e}")

        # Fallback to traditional
        self._traditional_engine = TraditionalVoiceEngine(self.config)
        self._active_engine = "traditional"
        logger.info("[Voice] Using traditional STT/TTS voice engine")

    def set_callbacks(self, on_transcript: Optional[Callable] = None,
                      on_state_change: Optional[Callable] = None):
        """Set event callbacks."""
        self._on_transcript = on_transcript
        self._on_state_change = on_state_change
        if self._traditional_engine:
            self._traditional_engine.set_callbacks(on_transcript, on_state_change)
        if self._livekit_engine:
            self._livekit_engine.set_callbacks(on_transcript, on_state_change)

    def listen_once(self, timeout: int = 10) -> Optional[str]:
        """Listen for a single voice command."""
        if self._traditional_engine:
            return self._traditional_engine.listen_once(timeout)
        return None

    def speak(self, text: str, interruptible: bool = True):
        """Speak text with barge-in support."""
        if self._traditional_engine:
            self._traditional_engine.speak(text, interruptible)

    def interrupt(self):
        """Interrupt current speech (barge-in)."""
        if self._traditional_engine:
            self._traditional_engine.interrupt()
        if self._livekit_engine:
            self._livekit_engine.interrupt()

    @property
    def state(self) -> VoiceState:
        if self._traditional_engine:
            return self._traditional_engine.state
        return VoiceState.IDLE

    @property
    def engine_type(self) -> str:
        return self._active_engine

    def get_stats(self) -> Dict[str, Any]:
        stats = {
            "active_engine": self._active_engine,
            "livekit_available": LIVEKIT_OK,
            "traditional_available": SR_OK and PYTTSX3_OK,
            "barge_in_enabled": self.config.barge_in_enabled,
        }
        if self._traditional_engine:
            stats["barge_in_stats"] = self._traditional_engine._barge_in.stats
        return stats


# Singleton and factory
_voice_engine: Optional[RealTimeVoiceEngine] = None

def get_realtime_voice(config: Optional[VoiceConfig] = None) -> RealTimeVoiceEngine:
    global _voice_engine
    if _voice_engine is None:
        _voice_engine = RealTimeVoiceEngine(config=config)
    return _voice_engine
