"""Hybrid Speech-to-Text - Local & Online STT

Integrated into LADA voice pipeline for GPU-accelerated local transcription.

Supported engines (with automatic fallback):
- Faster-Whisper (`faster_whisper`) - Primary: Fast local GPU transcription
  - large-v3-turbo: Best quality (6GB+ VRAM, 809M params, 6x faster than large-v3)
  - medium: Good balance (4GB VRAM)
  - small: Lightweight (2GB VRAM, Tamil+English support)
  - tiny: Minimal (CPU fallback)
- OpenAI Whisper (`whisper`) - Fallback: Local CPU/GPU transcription
- SpeechRecognition (`speech_recognition`) - Last resort: Google Speech API online

Optimizations:
- Auto-detects CUDA availability and optimal compute type
- VRAM auto-detection for model selection
- Persistent model instances (no reload per command)
- Supports multilingual (99+ languages with large-v3-turbo)
- Streaming transcription support
- Graceful degradation if dependencies unavailable

Environment variables:
- WHISPER_MODEL: Override model selection (large-v3-turbo, medium, small, tiny)
- WHISPER_DEVICE: Override device (cuda, cpu)
- WHISPER_COMPUTE_TYPE: Override compute type (float16, int8_float16, int8)

All imports are optional; the class degrades gracefully.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional, Iterator, List
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
    language: str = ""
    confidence: float = 0.0
    duration_seconds: float = 0.0


@dataclass
class StreamingSegment:
    """A single segment from streaming transcription."""
    text: str
    start: float
    end: float
    is_final: bool = False


# Model selection based on VRAM
VRAM_MODEL_MAP = {
    8: "large-v3-turbo",   # 8GB+ VRAM: Use turbo (best quality, 6x faster than large-v3)
    6: "large-v3-turbo",   # 6GB VRAM: Turbo works with int8_float16
    4: "medium",           # 4GB VRAM: Medium model
    2: "small",            # 2GB VRAM: Small model (good Tamil support)
    0: "tiny",             # CPU/minimal: Tiny model
}

def _detect_vram_gb() -> int:
    """Detect available VRAM in GB. Returns 0 if no GPU or detection fails."""
    try:
        import torch
        if torch.cuda.is_available():
            # Get total memory of first GPU in GB
            total_mem = torch.cuda.get_device_properties(0).total_memory
            return int(total_mem / (1024 ** 3))
    except Exception:
        pass
    return 0


def _select_model_for_vram(vram_gb: int) -> str:
    """Select best Whisper model based on available VRAM."""
    for threshold, model in sorted(VRAM_MODEL_MAP.items(), reverse=True):
        if vram_gb >= threshold:
            return model
    return "tiny"


class HybridSpeechRecognizer:
    """Hybrid STT wrapper with VRAM-aware model selection.

    Supports:
    - Faster-Whisper large-v3-turbo (6x faster than large-v3, 809M params)
    - Automatic VRAM detection for optimal model selection
    - Streaming transcription for real-time output
    - Multilingual support (99+ languages)

    Notes:
    - This class operates on an audio file path (wav/mp3/etc depending on backend).
    - For online recognition it expects SpeechRecognition-style audio capture in the caller.
    """

    def __init__(
        self,
        prefer: str = "faster-whisper",
        faster_whisper_model: str = "auto",  # Auto-select based on VRAM
        whisper_model: str = "auto",
        device: str = "auto",  # Will auto-detect cuda -> cpu
        compute_type: str = "auto",  # Will use int8_float16 on cuda, int8 on cpu
    ):
        self.prefer = prefer
        
        # Auto-detect best device
        env_device = os.getenv("WHISPER_DEVICE", "").lower()
        if env_device in ("cuda", "cpu"):
            self.device = env_device
        elif device == "auto":
            try:
                import torch
                self.device = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                self.device = "cpu"
        else:
            self.device = device
        
        # Detect VRAM for model selection
        self._vram_gb = _detect_vram_gb() if self.device == "cuda" else 0
        
        # Model selection: env var > explicit param > auto-detect
        env_model = os.getenv("WHISPER_MODEL", "").lower()
        if env_model:
            self.faster_whisper_model_name = env_model
            self.whisper_model_name = env_model
        elif faster_whisper_model == "auto":
            self.faster_whisper_model_name = _select_model_for_vram(self._vram_gb)
            self.whisper_model_name = self.faster_whisper_model_name
        else:
            self.faster_whisper_model_name = faster_whisper_model
            self.whisper_model_name = whisper_model if whisper_model != "auto" else faster_whisper_model
        
        # Compute type selection
        env_compute = os.getenv("WHISPER_COMPUTE_TYPE", "").lower()
        if env_compute:
            self.compute_type = env_compute
        elif compute_type == "auto":
            if self.device == "cuda":
                # int8_float16 is optimal for most GPUs (faster + less VRAM)
                self.compute_type = "int8_float16"
            else:
                # CPU: int8 is fastest
                self.compute_type = "int8"
        else:
            self.compute_type = compute_type

        self._fw_model = None
        self._whisper_model = None
        
        logger.info(
            f"[HybridSTT] Initialized: device={self.device}, model={self.faster_whisper_model_name}, "
            f"compute_type={self.compute_type}, vram={self._vram_gb}GB"
        )

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

    def transcribe_streaming(
        self, path: str, language: Optional[str] = None
    ) -> Iterator[StreamingSegment]:
        """Streaming transcription - yields segments as they're processed.
        
        Useful for real-time voice UI feedback.
        Only supported with Faster-Whisper.
        """
        if not self._load_faster_whisper():
            logger.warning("[HybridSTT] Streaming requires Faster-Whisper")
            return
        
        try:
            segments, info = self._fw_model.transcribe(  # type: ignore[union-attr]
                path,
                language=language,
                word_timestamps=True,
                vad_filter=True,  # Filter out silence
            )
            
            for i, seg in enumerate(segments):
                text = (seg.text or "").strip()
                if text:
                    yield StreamingSegment(
                        text=text,
                        start=seg.start,
                        end=seg.end,
                        is_final=False,
                    )
            
            # Mark final segment
            yield StreamingSegment(text="", start=0, end=0, is_final=True)
            
        except Exception as e:
            logger.error(f"[HybridSTT] Streaming transcription failed: {e}")
            return

    def get_model_info(self) -> dict:
        """Return current model configuration."""
        return {
            "device": self.device,
            "vram_gb": self._vram_gb,
            "model": self.faster_whisper_model_name,
            "compute_type": self.compute_type,
            "faster_whisper_available": FASTER_WHISPER_AVAILABLE,
            "whisper_available": WHISPER_AVAILABLE,
            "sr_available": SR_AVAILABLE,
        }

    def warmup(self) -> bool:
        """Pre-load model to avoid cold start latency on first transcription."""
        logger.info(f"[HybridSTT] Warming up {self.faster_whisper_model_name} model...")
        return self._load_faster_whisper() or self._load_whisper()
