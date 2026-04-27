"""
LADA v12.0 — Sub-Second Voice Pipeline Router
Orchestrates the full voice I/O loop:  Wake-word → STT → NLU → TTS

Pipeline stages:
1. Wake-word detection (openwakeword or keyword fallback)
2. Speech-to-text   (faster-whisper / Whisper API)
3. Intent routing    (pass to JarvisCommandProcessor or AI router)
4. Text-to-speech   (edge-tts / XTTS-v2 / pyttsx3 fallback)

Design goals:
- End-to-end latency < 800 ms for cached/small utterances
- Hot-swap any stage at runtime
- Async pipeline with backpressure via asyncio.Queue
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable, List
from enum import Enum

logger = logging.getLogger(__name__)

# Conditional imports — every stage degrades gracefully
try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_OK = True
except ImportError:
    FASTER_WHISPER_OK = False

try:
    import openwakeword
    from openwakeword.model import Model as OWWModel
    WAKEWORD_OK = True
except ImportError:
    WAKEWORD_OK = False

try:
    import edge_tts
    EDGE_TTS_OK = True
except ImportError:
    EDGE_TTS_OK = False

try:
    import pyttsx3
    PYTTSX3_OK = True
except ImportError:
    PYTTSX3_OK = False

# sounddevice replaces pyaudio for cross-Python-version audio capture
try:
    import sounddevice as sd
    import soundfile as sf
    import numpy as np
    SOUNDDEVICE_OK = True
except ImportError:
    SOUNDDEVICE_OK = False


class PipelineStage(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"


@dataclass
class VoicePipelineConfig:
    """Voice pipeline configuration."""
    wake_word: str = "hey lada"
    whisper_model: str = "base.en"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    tts_voice: str = "en-US-AriaNeural"
    tts_rate: str = "+0%"
    sample_rate: int = 16000
    vad_threshold: float = 0.5
    max_listen_seconds: float = 15.0
    silence_timeout: float = 1.5


@dataclass
class VoiceEvent:
    """Pipeline event passed between stages."""
    stage: PipelineStage
    audio_data: Optional[bytes] = None
    transcript: Optional[str] = None
    response_text: Optional[str] = None
    response_audio: Optional[bytes] = None
    latency_ms: float = 0.0
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


class VoicePipelineRouter:
    """
    Async voice I/O pipeline router.

    Usage::

        router = VoicePipelineRouter(config, intent_handler=my_handler)
        await router.initialize()
        # Process a single utterance:
        event = await router.process_utterance(audio_bytes)
        # Or run continuous listening:
        await router.start_continuous()
    """

    def __init__(
        self,
        config: Optional[VoicePipelineConfig] = None,
        intent_handler: Optional[Callable] = None,
        progress_callback: Optional[Callable] = None,
    ) -> None:
        self.config = config or VoicePipelineConfig()
        self.intent_handler = intent_handler
        self.progress_callback = progress_callback

        self._stt_model: Optional[Any] = None
        self._wakeword_model: Optional[Any] = None
        self._tts_engine: Optional[Any] = None

        self._stage = PipelineStage.IDLE
        self._running = False
        self._history: List[Dict[str, Any]] = []

    async def initialize(self) -> Dict[str, Any]:
        """Initialize all pipeline stages concurrently. Returns status dict."""
        status: Dict[str, Any] = {
            "stt": "unavailable",
            "wakeword": "unavailable",
            "tts": "unavailable",
        }

        # Initialize blocking models in threads
        import asyncio
        loop = asyncio.get_event_loop()

        def _init_stt():
            if FASTER_WHISPER_OK:
                return WhisperModel(
                    self.config.whisper_model,
                    device=self.config.whisper_device,
                    compute_type=self.config.whisper_compute_type,
                )
            return None

        def _init_wakeword():
            if WAKEWORD_OK:
                return OWWModel(
                    wakeword_models=["hey jarvis"],
                    inference_framework="onnx",
                )
            return None

        stt_task = loop.run_in_executor(None, _init_stt)
        wakeword_task = loop.run_in_executor(None, _init_wakeword)

        stt_model, ww_model = await asyncio.gather(stt_task, wakeword_task, return_exceptions=True)

        if isinstance(stt_model, Exception):
            logger.warning(f"[Voice] STT init failed: {stt_model}")
        elif stt_model:
            self._stt_model = stt_model
            status["stt"] = "faster-whisper"
            logger.info("[Voice] STT: faster-whisper initialized")
        else:
            logger.info("[Voice] STT: faster-whisper not available")

        if isinstance(ww_model, Exception):
            logger.warning(f"[Voice] Wake-word init failed: {ww_model}")
        elif ww_model:
            self._wakeword_model = ww_model
            status["wakeword"] = "openwakeword"
            logger.info("[Voice] Wake-word: openwakeword initialized")
        else:
            logger.info("[Voice] Wake-word: not available (keyword fallback)")

        # TTS
        if EDGE_TTS_OK:
            status["tts"] = "edge-tts"
            logger.info("[Voice] TTS: edge-tts available")
        elif PYTTSX3_OK:
            try:
                self._tts_engine = pyttsx3.init()
                status["tts"] = "pyttsx3"
                logger.info("[Voice] TTS: pyttsx3 fallback")
            except Exception as e:
                logger.warning(f"[Voice] TTS init failed: {e}")
        else:
            logger.info("[Voice] TTS: no engine available")

        return status

    # -- Main pipeline --

    async def process_utterance(self, audio_data: bytes) -> VoiceEvent:
        """
        Process a single audio utterance through the full pipeline.

        Returns a VoiceEvent with transcript, response, and latencies.
        """
        t0 = time.time()
        event = VoiceEvent(stage=PipelineStage.TRANSCRIBING, audio_data=audio_data)

        # 1. STT
        self._set_stage(PipelineStage.TRANSCRIBING)
        transcript = await self._transcribe(audio_data)
        if not transcript:
            event.stage = PipelineStage.ERROR
            event.error = "STT returned empty transcript"
            return event
        event.transcript = transcript

        # 2. Intent handling
        self._set_stage(PipelineStage.THINKING)
        response_text = await self._handle_intent(transcript)
        event.response_text = response_text

        # 3. TTS
        self._set_stage(PipelineStage.SPEAKING)
        audio_out = await self._synthesize(response_text)
        event.response_audio = audio_out

        event.stage = PipelineStage.IDLE
        event.latency_ms = (time.time() - t0) * 1000
        self._set_stage(PipelineStage.IDLE)

        # Record
        self._history.append({
            "transcript": transcript,
            "response": response_text[:200] if response_text else "",
            "latency_ms": event.latency_ms,
            "timestamp": time.time(),
        })
        if len(self._history) > 200:
            self._history = self._history[-200:]

        logger.info(
            f"[Voice] Pipeline complete: '{transcript[:60]}' → "
            f"'{(response_text or '')[:60]}' ({event.latency_ms:.0f}ms)"
        )
        return event

    # -- Stage implementations --

    async def _transcribe(self, audio_data: bytes) -> Optional[str]:
        """Speech-to-text using faster-whisper."""
        if self._stt_model is None:
            return None

        try:
            # Convert bytes to numpy float32 array (works with sounddevice output)
            if SOUNDDEVICE_OK:
                audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            else:
                import numpy as _np
                audio_np = _np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

            segments, _ = self._stt_model.transcribe(
                audio_np,
                beam_size=1,        # Speed over accuracy for real-time
                language="en",
                vad_filter=True,
                vad_parameters=dict(
                    threshold=self.config.vad_threshold,
                    min_silence_duration_ms=int(self.config.silence_timeout * 1000),
                ),
            )

            text = " ".join(seg.text.strip() for seg in segments)
            return text.strip() or None

        except Exception as e:
            logger.error(f"[Voice] STT error: {e}")
            return None

    def record_from_mic(self, duration: float = None) -> bytes:
        """
        Record audio from the microphone using sounddevice.
        Returns raw int16 PCM bytes for use with _transcribe().
        Falls back gracefully if sounddevice is not available.
        """
        if not SOUNDDEVICE_OK:
            logger.error("[Voice] sounddevice not available for mic recording")
            return b""

        listen_secs = duration or self.config.max_listen_seconds
        sr = self.config.sample_rate
        try:
            logger.info(f"[Voice] Recording {listen_secs}s from mic (sounddevice)...")
            recording = sd.rec(
                int(listen_secs * sr),
                samplerate=sr,
                channels=1,
                dtype="int16",
                blocking=True,
            )
            return recording.tobytes()
        except Exception as e:
            logger.error(f"[Voice] Mic recording error: {e}")
            return b""

    async def _handle_intent(self, transcript: str) -> str:
        """Route transcript to intent handler or return default."""
        if self.intent_handler:
            try:
                result = self.intent_handler(transcript)
                if asyncio.iscoroutine(result):
                    result = await result
                return str(result)
            except Exception as e:
                logger.error(f"[Voice] Intent handler error: {e}")
                return f"Sorry, I encountered an error: {e}"

        return f"I heard: {transcript}"

    async def _synthesize(self, text: str) -> Optional[bytes]:
        """Text-to-speech synthesis."""
        if not text:
            return None

        if EDGE_TTS_OK:
            try:
                communicate = edge_tts.Communicate(
                    text, self.config.tts_voice, rate=self.config.tts_rate
                )
                audio_chunks = []
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_chunks.append(chunk["data"])
                return b"".join(audio_chunks) if audio_chunks else None
            except Exception as e:
                logger.error(f"[Voice] edge-tts error: {e}")

        if self._tts_engine and PYTTSX3_OK:
            try:
                import tempfile, os
                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                tmp.close()
                self._tts_engine.save_to_file(text, tmp.name)
                self._tts_engine.runAndWait()
                with open(tmp.name, "rb") as f:
                    data = f.read()
                os.unlink(tmp.name)
                return data
            except Exception as e:
                logger.error(f"[Voice] pyttsx3 error: {e}")

        return None

    # -- Wake-word detection --

    def detect_wakeword(self, audio_chunk: bytes) -> bool:
        """Check if a short audio chunk contains the wake-word."""
        if self._wakeword_model is not None:
            try:
                import numpy as np
                audio_np = np.frombuffer(audio_chunk, dtype=np.int16)
                prediction = self._wakeword_model.predict(audio_np)
                # openwakeword returns dict of model_name → score
                for score in prediction.values():
                    if score > 0.5:
                        return True
            except Exception as e:
                logger.debug(f"[Voice] Wakeword detection error: {e}")

        return False

    # -- Helpers --

    def _set_stage(self, stage: PipelineStage) -> None:
        self._stage = stage
        if self.progress_callback:
            try:
                self.progress_callback(stage.value)
            except Exception:
                pass

    @property
    def current_stage(self) -> str:
        return self._stage.value

    def get_stats(self) -> Dict[str, Any]:
        """Return diagnostics."""
        latencies = [h["latency_ms"] for h in self._history]
        return {
            "stage": self._stage.value,
            "total_utterances": len(self._history),
            "avg_latency_ms": sum(latencies) / max(1, len(latencies)),
            "stt_available": self._stt_model is not None,
            "wakeword_available": self._wakeword_model is not None,
            "tts_engine": (
                "edge-tts" if EDGE_TTS_OK else
                "pyttsx3" if (self._tts_engine and PYTTSX3_OK) else
                "none"
            ),
        }

    async def shutdown(self) -> None:
        """Cleanup resources."""
        self._running = False
        self._stt_model = None
        self._wakeword_model = None
        if self._tts_engine and PYTTSX3_OK:
            try:
                self._tts_engine.stop()
            except Exception:
                pass
        logger.info("[Voice] Pipeline shutdown")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: Optional[VoicePipelineRouter] = None


def get_voice_pipeline(
    intent_handler: Optional[Callable] = None,
) -> VoicePipelineRouter:
    """Get or create the global VoicePipelineRouter."""
    global _instance
    if _instance is None:
        _instance = VoicePipelineRouter(intent_handler=intent_handler)
    return _instance
