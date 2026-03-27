"""XTTS-v2 Text-to-Speech Engine

High-quality neural TTS with voice cloning capabilities.

Features:
- Voice cloning from 6-second audio sample
- 17 language support (en, es, fr, de, it, pt, pl, tr, ru, nl, cs, ar, zh-cn, ja, hu, ko, hi)
- Emotional/expressive speech
- Streaming audio generation
- GPU acceleration (CUDA)

Environment variables:
- XTTS_VOICE_SAMPLE: Path to voice clone sample (default: ~/.lada/voices/default.wav)
- XTTS_LANGUAGE: Default language (default: en)
- XTTS_DEVICE: Force device (cuda/cpu, default: auto)
- TTS_ENGINE: Primary engine selection (xtts/kokoro/gtts/pyttsx3)

Fallback chain: XTTS-v2 → Kokoro → gTTS → pyttsx3
"""

from __future__ import annotations

import os
import logging
import tempfile
import hashlib
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Callable, Iterator
import threading

logger = logging.getLogger(__name__)

# Optional dependencies
try:
    from TTS.api import TTS  # type: ignore
    XTTS_AVAILABLE = True
except ImportError:
    TTS = None  # type: ignore
    XTTS_AVAILABLE = False

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    torch = None  # type: ignore
    TORCH_AVAILABLE = False

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    pygame = None  # type: ignore
    PYGAME_AVAILABLE = False


@dataclass
class TTSResult:
    """Result of TTS synthesis."""
    audio_path: str
    engine: str
    duration_seconds: float = 0.0
    cached: bool = False


class XTTSEngine:
    """XTTS-v2 TTS engine with voice cloning.
    
    Usage:
        engine = XTTSEngine()
        engine.speak("Hello, I am LADA")
        
        # With voice cloning
        engine = XTTSEngine(voice_sample="path/to/voice.wav")
        engine.speak("This sounds like the cloned voice")
    """
    
    # Supported languages
    LANGUAGES = [
        "en", "es", "fr", "de", "it", "pt", "pl", "tr", "ru",
        "nl", "cs", "ar", "zh-cn", "ja", "hu", "ko", "hi"
    ]
    
    def __init__(
        self,
        voice_sample: Optional[str] = None,
        language: str = "en",
        device: str = "auto",
        cache_dir: Optional[str] = None,
        enable_cache: bool = True,
    ):
        """Initialize XTTS-v2 engine.
        
        Args:
            voice_sample: Path to voice clone sample (6+ seconds WAV/MP3)
            language: Default language code
            device: Device to use (auto/cuda/cpu)
            cache_dir: Directory for audio cache
            enable_cache: Whether to cache generated audio
        """
        self.language = os.getenv("XTTS_LANGUAGE", language)
        self.enable_cache = enable_cache
        
        # Voice sample path
        env_sample = os.getenv("XTTS_VOICE_SAMPLE", "")
        if env_sample:
            self.voice_sample = env_sample
        elif voice_sample:
            self.voice_sample = voice_sample
        else:
            # Default voice sample location
            default_path = Path.home() / ".lada" / "voices" / "default.wav"
            self.voice_sample = str(default_path) if default_path.exists() else None
        
        # Device selection
        env_device = os.getenv("XTTS_DEVICE", "").lower()
        if env_device in ("cuda", "cpu"):
            self.device = env_device
        elif device == "auto":
            if TORCH_AVAILABLE and torch.cuda.is_available():
                self.device = "cuda"
            else:
                self.device = "cpu"
        else:
            self.device = device
        
        # Cache directory
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path.home() / ".lada" / "tts_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Model instance (lazy loaded)
        self._model = None
        self._lock = threading.Lock()
        
        # Audio playback
        self._pygame_initialized = False
        
        logger.info(
            f"[XTTS] Initialized: device={self.device}, language={self.language}, "
            f"voice_sample={self.voice_sample}, available={XTTS_AVAILABLE}"
        )
    
    def is_available(self) -> bool:
        """Check if XTTS-v2 is available."""
        return XTTS_AVAILABLE and TORCH_AVAILABLE
    
    def _load_model(self) -> bool:
        """Load XTTS-v2 model (lazy loading)."""
        if not XTTS_AVAILABLE:
            return False
        
        with self._lock:
            if self._model is not None:
                return True
            
            try:
                logger.info("[XTTS] Loading XTTS-v2 model...")
                self._model = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
                
                # Move to GPU if available
                if self.device == "cuda" and TORCH_AVAILABLE:
                    self._model = self._model.to(self.device)
                
                logger.info("[XTTS] Model loaded successfully")
                return True
                
            except Exception as e:
                logger.error(f"[XTTS] Failed to load model: {e}")
                self._model = None
                return False
    
    def _get_cache_path(self, text: str, language: str) -> Path:
        """Generate cache path for text."""
        # Hash text + language + voice sample
        key = f"{text}:{language}:{self.voice_sample or 'default'}"
        hash_key = hashlib.md5(key.encode()).hexdigest()[:16]
        return self.cache_dir / f"xtts_{hash_key}.wav"
    
    def synthesize(
        self,
        text: str,
        language: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> Optional[TTSResult]:
        """Synthesize speech from text.
        
        Args:
            text: Text to synthesize
            language: Language code (default: instance language)
            output_path: Output file path (default: temp file)
            
        Returns:
            TTSResult with audio path, or None on failure
        """
        if not text or not text.strip():
            return None
        
        lang = language or self.language
        text = text.strip()
        
        # Check cache
        if self.enable_cache and not output_path:
            cache_path = self._get_cache_path(text, lang)
            if cache_path.exists():
                logger.debug(f"[XTTS] Cache hit: {cache_path}")
                return TTSResult(
                    audio_path=str(cache_path),
                    engine="xtts-v2:cached",
                    cached=True,
                )
        
        # Load model
        if not self._load_model():
            logger.warning("[XTTS] Model not available, falling back")
            return None
        
        try:
            # Determine output path
            if output_path:
                out_file = output_path
            elif self.enable_cache:
                out_file = str(self._get_cache_path(text, lang))
            else:
                fd, out_file = tempfile.mkstemp(suffix=".wav")
                os.close(fd)
            
            # Synthesize
            if self.voice_sample and Path(self.voice_sample).exists():
                # Voice cloning mode
                self._model.tts_to_file(
                    text=text,
                    file_path=out_file,
                    speaker_wav=self.voice_sample,
                    language=lang,
                )
                engine_name = "xtts-v2:cloned"
            else:
                # Default voice
                self._model.tts_to_file(
                    text=text,
                    file_path=out_file,
                    language=lang,
                )
                engine_name = "xtts-v2:default"
            
            # Get duration
            duration = self._get_audio_duration(out_file)
            
            return TTSResult(
                audio_path=out_file,
                engine=engine_name,
                duration_seconds=duration,
                cached=False,
            )
            
        except Exception as e:
            logger.error(f"[XTTS] Synthesis failed: {e}")
            return None
    
    def _get_audio_duration(self, path: str) -> float:
        """Get audio duration in seconds."""
        try:
            import wave
            with wave.open(path, 'rb') as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                return frames / float(rate)
        except Exception:
            return 0.0
    
    def _init_pygame(self) -> bool:
        """Initialize pygame for audio playback."""
        if self._pygame_initialized:
            return True
        
        if not PYGAME_AVAILABLE:
            return False
        
        try:
            pygame.mixer.init()
            self._pygame_initialized = True
            return True
        except Exception as e:
            logger.warning(f"[XTTS] Failed to init pygame: {e}")
            return False
    
    def play(self, audio_path: str, blocking: bool = True) -> bool:
        """Play audio file.
        
        Args:
            audio_path: Path to audio file
            blocking: Wait for playback to complete
            
        Returns:
            True if playback started successfully
        """
        if not self._init_pygame():
            logger.warning("[XTTS] Pygame not available for playback")
            return False
        
        try:
            pygame.mixer.music.load(audio_path)
            pygame.mixer.music.play()
            
            if blocking:
                while pygame.mixer.music.get_busy():
                    pygame.time.wait(50)
            
            return True
            
        except Exception as e:
            logger.error(f"[XTTS] Playback failed: {e}")
            return False
    
    def stop(self):
        """Stop current playback."""
        if self._pygame_initialized:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
    
    def speak(
        self,
        text: str,
        language: Optional[str] = None,
        blocking: bool = True,
    ) -> bool:
        """Synthesize and play text.
        
        Convenience method combining synthesize() and play().
        
        Args:
            text: Text to speak
            language: Language code
            blocking: Wait for playback to complete
            
        Returns:
            True if speech was played successfully
        """
        result = self.synthesize(text, language)
        if result:
            return self.play(result.audio_path, blocking)
        return False
    
    def synthesize_streaming(
        self,
        text: str,
        language: Optional[str] = None,
        chunk_callback: Optional[Callable[[bytes], None]] = None,
    ) -> Iterator[bytes]:
        """Streaming synthesis - yields audio chunks as they're generated.
        
        Note: XTTS-v2 doesn't natively support true streaming, but this
        simulates streaming by synthesizing and yielding in chunks.
        
        Args:
            text: Text to synthesize
            language: Language code
            chunk_callback: Optional callback for each chunk
            
        Yields:
            Audio data chunks (WAV format)
        """
        result = self.synthesize(text, language)
        if not result:
            return
        
        try:
            with open(result.audio_path, 'rb') as f:
                # Read and yield in 4KB chunks
                while chunk := f.read(4096):
                    if chunk_callback:
                        chunk_callback(chunk)
                    yield chunk
        except Exception as e:
            logger.error(f"[XTTS] Streaming read failed: {e}")
    
    def set_voice_sample(self, path: str) -> bool:
        """Set voice cloning sample.
        
        Args:
            path: Path to voice sample (WAV/MP3, 6+ seconds)
            
        Returns:
            True if sample is valid and set
        """
        if not Path(path).exists():
            logger.error(f"[XTTS] Voice sample not found: {path}")
            return False
        
        self.voice_sample = path
        logger.info(f"[XTTS] Voice sample set: {path}")
        return True
    
    def clear_cache(self) -> int:
        """Clear the TTS cache.
        
        Returns:
            Number of files deleted
        """
        count = 0
        for f in self.cache_dir.glob("xtts_*.wav"):
            try:
                f.unlink()
                count += 1
            except Exception:
                pass
        
        logger.info(f"[XTTS] Cleared {count} cached files")
        return count
    
    def warmup(self) -> bool:
        """Pre-load model to avoid cold start latency."""
        logger.info("[XTTS] Warming up model...")
        return self._load_model()
    
    def get_info(self) -> dict:
        """Get engine info."""
        return {
            "available": self.is_available(),
            "device": self.device,
            "language": self.language,
            "voice_sample": self.voice_sample,
            "cache_dir": str(self.cache_dir),
            "cache_enabled": self.enable_cache,
            "model_loaded": self._model is not None,
            "languages": self.LANGUAGES,
        }


class FallbackTTSEngine:
    """TTS engine with fallback chain: XTTS-v2 → Kokoro → gTTS → pyttsx3.
    
    Automatically selects the best available engine.
    """
    
    def __init__(self, **kwargs):
        """Initialize with fallback chain.
        
        All kwargs are passed to XTTSEngine if available.
        """
        self.engines = []
        
        # Try XTTS-v2
        if XTTS_AVAILABLE:
            self.engines.append(("xtts", XTTSEngine(**kwargs)))
        
        # Kokoro, gTTS, pyttsx3 will be tried via voice_tamil_free.py
        self._primary_engine = os.getenv("TTS_ENGINE", "auto").lower()
        
        logger.info(f"[FallbackTTS] Engines available: {[e[0] for e in self.engines]}")
    
    def speak(self, text: str, language: str = "en", blocking: bool = True) -> bool:
        """Speak text using best available engine."""
        # Try primary engine first
        if self._primary_engine != "auto":
            for name, engine in self.engines:
                if name == self._primary_engine:
                    if engine.speak(text, language, blocking):
                        return True
                    break
        
        # Try all engines in order
        for name, engine in self.engines:
            try:
                if engine.speak(text, language, blocking):
                    return True
            except Exception as e:
                logger.debug(f"[FallbackTTS] {name} failed: {e}")
                continue
        
        # All failed
        logger.warning("[FallbackTTS] All engines failed")
        return False
    
    def synthesize(self, text: str, language: str = "en") -> Optional[TTSResult]:
        """Synthesize using best available engine."""
        for name, engine in self.engines:
            try:
                result = engine.synthesize(text, language)
                if result:
                    return result
            except Exception as e:
                logger.debug(f"[FallbackTTS] {name} synthesis failed: {e}")
                continue
        
        return None


# Convenience functions
_default_engine: Optional[XTTSEngine] = None


def get_xtts_engine(**kwargs) -> XTTSEngine:
    """Get or create default XTTS engine (singleton)."""
    global _default_engine
    if _default_engine is None:
        _default_engine = XTTSEngine(**kwargs)
    return _default_engine


def speak(text: str, language: str = "en", blocking: bool = True) -> bool:
    """Speak text using default engine."""
    return get_xtts_engine().speak(text, language, blocking)


def synthesize(text: str, language: str = "en") -> Optional[TTSResult]:
    """Synthesize text using default engine."""
    return get_xtts_engine().synthesize(text, language)
