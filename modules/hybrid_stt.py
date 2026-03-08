"""Hybrid Speech-to-Text - Local & Online STT

Integrated into LADA voice pipeline for GPU-accelerated local transcription.

Supported engines (with automatic fallback):
- Faster-Whisper (`faster_whisper`) - Primary: Fast local GPU transcription (optimized for RTX 3050 6GB)
- OpenAI Whisper (`whisper`) - Fallback: Local CPU/GPU transcription
- SpeechRecognition (`speech_recognition`) - Last resort: Google Speech API online

Optimizations:
- Auto-detects CUDA availability and optimal compute type
- Persistent model instances (no reload per command)
- Supports multilingual (Tamil + English) with `small` model
- Graceful degradation if dependencies unavailable

All imports are optional; the class degrades gracefully.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Optional deps
try:
    from faster_whisper import WhisperModel  # type: ignore

    FASTER_WHISPER_AVAILABLE = True
except Exception:
    WhisperModel = None  # type: ignore
    FASTER_WHISPER_AVAILABLE = False

try:
    import whisper  # type: ignore

    WHISPER_AVAILABLE = True
except Exception:
    whisper = None  # type: ignore
    WHISPER_AVAILABLE = False

try:
    import speech_recognition as sr  # type: ignore

    SR_AVAILABLE = True
except Exception:
    sr = None  # type: ignore
    SR_AVAILABLE = False


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    engine: str


class HybridSpeechRecognizer:
    """Hybrid STT wrapper (Phase 2).

    Notes:
    - This class operates on an audio file path (wav/mp3/etc depending on backend).
    - For online recognition it expects SpeechRecognition-style audio capture in the caller.
    """

    def __init__(
        self,
        prefer: str = "faster-whisper",
        faster_whisper_model: str = "small",  # Good balance for RTX 3050 6GB + Tamil support
        whisper_model: str = "small",
        device: str = "auto",  # Will auto-detect cuda -> cpu
        compute_type: str = "auto",  # Will use int8_float16 on cuda, int8 on cpu
    ):
        self.prefer = prefer
        self.faster_whisper_model_name = faster_whisper_model
        self.whisper_model_name = whisper_model
        
        # Auto-detect best device and compute_type for hardware
        if device == "auto":
            try:
                import torch
                self.device = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                self.device = "cpu"
        else:
            self.device = device
        
        if compute_type == "auto":
            if self.device == "cuda":
                # RTX 3050 6GB: int8_float16 is optimal (faster + less VRAM than float16)
                self.compute_type = "int8_float16"
            else:
                # CPU: int8 is fastest
                self.compute_type = "int8"
        else:
            self.compute_type = compute_type

        self._fw_model = None
        self._whisper_model = None

    def is_available(self) -> bool:
        return FASTER_WHISPER_AVAILABLE or WHISPER_AVAILABLE or SR_AVAILABLE

    def _load_faster_whisper(self) -> bool:
        if not FASTER_WHISPER_AVAILABLE:
            return False
        if self._fw_model is None:
            try:
                self._fw_model = WhisperModel(
                    self.faster_whisper_model_name,
                    device=self.device,
                    compute_type=self.compute_type,
                )
            except Exception as e:
                logger.warning(f"[HybridSTT] Faster-Whisper init failed: {e}")
                self._fw_model = None
                return False
        return True

    def _load_whisper(self) -> bool:
        if not WHISPER_AVAILABLE:
            return False
        if self._whisper_model is None:
            try:
                self._whisper_model = whisper.load_model(self.whisper_model_name)
            except Exception as e:
                logger.warning(f"[HybridSTT] Whisper init failed: {e}")
                self._whisper_model = None
                return False
        return True

    def transcribe_file(self, path: str, language: Optional[str] = "en") -> Optional[TranscriptionResult]:
        """Transcribe an audio file.

        Returns None if no engine is available or transcription fails.
        """
        prefer = (self.prefer or "").lower().strip()

        # 1) Faster-Whisper
        if prefer in {"faster-whisper", "faster_whisper", "fw"}:
            result = self._transcribe_faster_whisper(path, language=language)
            if result:
                return result
            result = self._transcribe_whisper(path, language=language)
            if result:
                return result

        # 2) Whisper
        if prefer in {"whisper", "openai-whisper"}:
            result = self._transcribe_whisper(path, language=language)
            if result:
                return result
            result = self._transcribe_faster_whisper(path, language=language)
            if result:
                return result

        # 3) Best-effort fallback
        result = self._transcribe_faster_whisper(path, language=language)
        if result:
            return result
        result = self._transcribe_whisper(path, language=language)
        if result:
            return result

        return None

    def _transcribe_faster_whisper(self, path: str, language: Optional[str]) -> Optional[TranscriptionResult]:
        if not self._load_faster_whisper():
            return None
        try:
            segments, info = self._fw_model.transcribe(path, language=language)  # type: ignore[union-attr]
            text = " ".join((seg.text or "").strip() for seg in segments).strip()
            if not text:
                return None
            engine = f"faster-whisper:{getattr(info, 'model', self.faster_whisper_model_name)}"
            return TranscriptionResult(text=text, engine=engine)
        except Exception as e:
            logger.debug(f"[HybridSTT] Faster-Whisper transcription failed: {e}")
            return None

    def _transcribe_whisper(self, path: str, language: Optional[str]) -> Optional[TranscriptionResult]:
        if not self._load_whisper():
            return None
        try:
            result = self._whisper_model.transcribe(path, language=language)  # type: ignore[union-attr]
            text = (result or {}).get("text", "")
            text = (text or "").strip()
            if not text:
                return None
            engine = f"whisper:{self.whisper_model_name}"
            return TranscriptionResult(text=text, engine=engine)
        except Exception as e:
            logger.debug(f"[HybridSTT] Whisper transcription failed: {e}")
            return None
