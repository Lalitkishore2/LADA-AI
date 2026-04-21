"""
LADA v7.0 - Free Natural Voice System
Karen-style Voice (warm, friendly, supportive) like Spider-Man Homecoming
Tamil + English (Thanglish) Support with Auto Language Detection
100% FREE - Uses gTTS (online) + pyttsx3 (offline fallback)
"""

import os
import re
import time
import subprocess
import threading
import tempfile
import logging
from pathlib import Path
from typing import Optional

import speech_recognition as sr

# Import Hybrid STT for local transcription (Faster-Whisper)
try:
    from modules.hybrid_stt import HybridSpeechRecognizer
    HYBRID_STT_AVAILABLE = True
except Exception:
    HybridSpeechRecognizer = None
    HYBRID_STT_AVAILABLE = False

# Import Kokoro for local neural TTS
try:
    import kokoro_onnx  # type: ignore
    KOKORO_AVAILABLE = True
except Exception:
    kokoro_onnx = None
    KOKORO_AVAILABLE = False

logger = logging.getLogger(__name__)

# Try importing voice libraries
try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    logger.warning("gTTS not available - install with: pip install gTTS")

try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False
    logger.warning("pyttsx3 not available - install with: pip install pyttsx3")

try:
    from playsound import playsound
    PLAYSOUND_AVAILABLE = True
except ImportError:
    PLAYSOUND_AVAILABLE = False
    logger.warning("playsound not available - install with: pip install playsound==1.2.2")

try:
    import pygame
    pygame.mixer.init()
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

# openwakeword — local, offline wake word detection (no API calls)
# Falls back gracefully to existing Google STT if not installed.
_OWW_MODEL = None
_OWW_OK = False
try:
    import numpy as _np
    import pyaudio as _pyaudio
    from openwakeword.model import Model as _OWWModel
    # Use 'alexa' as a sensitive voice-activity trigger; validation is done via
    # local Whisper STT which checks for the actual wake phrase ("lada", "hey lada").
    _OWW_MODEL = _OWWModel(wakeword_models=["alexa"], inference_framework="onnx")
    _OWW_OK = True
    logger.info("[VoiceOWW] openwakeword loaded — local wake detection active")
except Exception as _oww_err:
    _OWW_OK = False
    logger.debug(f"[VoiceOWW] openwakeword not available, using Google STT fallback: {_oww_err}")


class FreeNaturalVoice:
    """
    Karen-style Voice System - Warm, Friendly, Supportive
    Like Karen from Spider-Man: Homecoming
    
    Features:
    - Warm female voice (Microsoft Zira or gTTS female)
    - Auto-detects Tamil/English from text
    - Uses gTTS for natural online voice
    - Falls back to pyttsx3 for offline use
    - Supports mixed language (Thanglish)
    - Wake word detection
    - Personality phrases for natural conversation
    """
    
    def __init__(self, tamil_mode: bool = True, auto_detect: bool = True):
        """
        Initialize the Karen-style voice system
        
        Args:
            tamil_mode: Enable Tamil language support
            auto_detect: Auto-detect language from input/output text
        """
        self.tamil_mode = tamil_mode
        self.auto_detect = auto_detect
        self.recognizer = sr.Recognizer()
        self.current_language = 'en'  # Default language
        self.mic_device_index = self._resolve_microphone_device_index()

        # Local STT (Faster-Whisper for RTX 3050 6GB)
        self._hybrid_stt = None
        
        # Local neural TTS (Kokoro)
        self._kokoro_model = None
        self._kokoro_enabled = os.getenv('USE_KOKORO', 'true').lower() == 'true'
        self._kokoro_assets_available = False
        self._kokoro_unavailable_reason = ""
        self._tts_lock = threading.Lock()

        # Tamil voice style
        # If enabled, when the language is Tamil ('ta'), we speak a romanized (Thanglish) version
        # using an English TTS voice, while still showing Tamil text in the UI.
        self.tamil_tts_style = os.getenv('TAMIL_TTS_STYLE', 'thanglish').strip().lower()
        self.speak_thanglish_for_tamil = self.tamil_tts_style in {'thanglish', 'romanized', 'rom', 'latin'}
        
        # Voice settings - Karen style: warm, clear, natural pace
        self.voice_speed = int(os.getenv('VOICE_RATE', '205'))
        self.voice_volume = float(os.getenv('VOICE_VOLUME', '0.9'))
        self.use_gtts = os.getenv('USE_GTTS', 'true').lower() == 'true'
        self.gtts_slow = os.getenv('GTTS_SLOW', 'false').lower() == 'true'
        
        # Temp directory for audio files
        self.temp_dir = Path(tempfile.gettempdir()) / "lada_voice"
        self.temp_dir.mkdir(exist_ok=True)
        
        # Initialize offline TTS engine (backup) with Karen-style voice
        self.offline_engine = None
        self._selected_voice_name = None
        if PYTTSX3_AVAILABLE:
            try:
                self.offline_engine = pyttsx3.init('sapi5')
                voices = self.offline_engine.getProperty('voices')

                selected_voice = None

                # Allow explicit voice ID override via env var
                explicit_voice_id = os.getenv('VOICE_ID', '').strip()
                if explicit_voice_id:
                    for voice in voices:
                        if voice.id == explicit_voice_id:
                            selected_voice = voice
                            break
                    if selected_voice:
                        logger.info(f"Using explicit VOICE_ID: {selected_voice.name}")
                    else:
                        logger.warning(f"VOICE_ID '{explicit_voice_id}' not found, falling back to auto-select")

                # Auto-select: Priority order for female voices (Karen-style)
                if not selected_voice:
                    preferred_voices = ['zira', 'eva', 'hazel', 'susan', 'female']
                    for preference in preferred_voices:
                        for voice in voices:
                            if preference in voice.name.lower():
                                selected_voice = voice
                                break
                        if selected_voice:
                            break
                
                if selected_voice:
                    self.offline_engine.setProperty('voice', selected_voice.id)
                    self._selected_voice_name = selected_voice.name
                    logger.info(f"✅ Selected voice: {selected_voice.name}")
                elif voices:
                    # Fallback to first voice
                    self.offline_engine.setProperty('voice', voices[0].id)
                    self._selected_voice_name = voices[0].name
                
                self.offline_engine.setProperty('rate', self.voice_speed)
                self.offline_engine.setProperty('volume', self.voice_volume)
                logger.info(f"✅ Offline voice (pyttsx3) initialized - Karen style")
            except Exception as e:
                logger.warning(f"⚠️ Could not initialize pyttsx3: {e}")
                self.offline_engine = None
        
        # Speech recognition settings
        self.speech_timeout = int(os.getenv('SPEECH_TIMEOUT_SEC', '5'))
        self.phrase_limit = int(os.getenv('PHRASE_TIME_LIMIT', '10'))
        
        # Wake words
        wake_words_str = os.getenv('WAKEWORDS', 'lada,hey lada,okay lada')
        self.wake_words = [w.strip().lower() for w in wake_words_str.split(',')]

        if self._kokoro_enabled and KOKORO_AVAILABLE:
            self._kokoro_assets_available = self._kokoro_assets_present()
            if not self._kokoro_assets_available:
                model_path, voices_path = self._kokoro_model_paths()
                self._kokoro_unavailable_reason = (
                    f"Kokoro model files not found: {model_path.name}, {voices_path.name}. "
                    "Using fallback TTS engines."
                )
                logger.info(self._kokoro_unavailable_reason)

        # Lock to best available TTS engine.
        self._locked_tts = self._select_locked_tts_engine()
        logger.info(f"TTS engine locked to: {self._locked_tts}")

        # Pre-load Kokoro model at startup to eliminate first-speak latency.
        if self._locked_tts == 'kokoro' and self._kokoro_assets_available:
            threading.Thread(target=self._preload_kokoro, daemon=True).start()

        logger.info(f"✅ FreeNaturalVoice initialized (Tamil: {tamil_mode}, Voice: Karen-style)")

    def _kokoro_model_paths(self) -> tuple[Path, Path]:
        model_dir = Path(__file__).parent / "models" / "kokoro"
        return model_dir / "kokoro-v1.0.int8.onnx", model_dir / "voices-v1.0.bin"

    def _kokoro_assets_present(self) -> bool:
        model_path, voices_path = self._kokoro_model_paths()
        return model_path.exists() and voices_path.exists()

    def _select_locked_tts_engine(self) -> Optional[str]:
        if self._kokoro_enabled and KOKORO_AVAILABLE and self._kokoro_assets_available:
            return 'kokoro'
        if self.use_gtts and GTTS_AVAILABLE:
            return 'gtts'
        if self.offline_engine:
            return 'pyttsx3'
        return None

    def _mark_kokoro_unavailable(self, reason: str) -> None:
        if self._kokoro_unavailable_reason:
            return
        self._kokoro_assets_available = False
        self._kokoro_unavailable_reason = reason
        logger.warning(reason)
        if self._locked_tts == 'kokoro':
            self._locked_tts = self._select_locked_tts_engine()
            logger.info(f"TTS engine locked to: {self._locked_tts}")

    def _resolve_microphone_device_index(self) -> Optional[int]:
        """Resolve preferred microphone device index from env var."""
        raw = os.getenv("LADA_MIC_DEVICE_INDEX", "").strip()
        if not raw:
            return None
        try:
            idx = int(raw)
            if idx < 0:
                logger.warning("LADA_MIC_DEVICE_INDEX must be >= 0, ignoring invalid value")
                return None
            return idx
        except ValueError:
            logger.warning("LADA_MIC_DEVICE_INDEX is not an integer, ignoring value")
            return None

    def _open_microphone(self):
        """Open microphone with configured device index, fallback to default."""
        if self.mic_device_index is None:
            return sr.Microphone()
        try:
            return sr.Microphone(device_index=self.mic_device_index)
        except Exception as exc:
            logger.warning(f"Configured microphone index {self.mic_device_index} unavailable: {exc}")
            return sr.Microphone()
    
    def detect_language(self, text: str) -> str:
        """
        Auto-detect if text is Tamil or English
        
        Tamil Unicode range: \u0B80 - \u0BFF
        
        Returns:
            'ta' for Tamil, 'en' for English
        """
        if not text:
            return 'en'
        
        # Count Tamil characters
        tamil_chars = sum(1 for char in text if '\u0B80' <= char <= '\u0BFF')
        total_alpha = sum(1 for char in text if char.isalpha())
        
        if total_alpha == 0:
            return 'en'
        
        # If more than 30% Tamil characters, it's Tamil
        tamil_ratio = tamil_chars / total_alpha
        
        if tamil_ratio > 0.3:
            return 'ta'
        return 'en'

    def tamil_to_thanglish(self, text: str) -> str:
        """Lightweight Tamil -> Latin (Thanglish) romanization for TTS.

        Not a perfect transliterator; it aims to create something English TTS can pronounce.
        """
        if not text:
            return text

        independent_vowels = {
            'அ': 'a', 'ஆ': 'aa', 'இ': 'i', 'ஈ': 'ii', 'உ': 'u', 'ஊ': 'uu', 'எ': 'e', 'ஏ': 'ee',
            'ஐ': 'ai', 'ஒ': 'o', 'ஓ': 'oo', 'ஔ': 'au'
        }
        vowel_signs = {
            'ா': 'aa', 'ி': 'i', 'ீ': 'ii', 'ு': 'u', 'ூ': 'uu', 'ெ': 'e', 'ே': 'ee',
            'ை': 'ai', 'ொ': 'o', 'ோ': 'oo', 'ௌ': 'au'
        }
        consonants = {
            'க': 'k', 'ங': 'ng', 'ச': 'ch', 'ஞ': 'nj', 'ட': 't', 'ண': 'n', 'த': 'th', 'ந': 'n',
            'ப': 'p', 'ம': 'm', 'ய': 'y', 'ர': 'r', 'ல': 'l', 'வ': 'v', 'ழ': 'zh', 'ள': 'l',
            'ற': 'r', 'ன': 'n', 'ஜ': 'j', 'ஷ': 'sh', 'ஸ': 's', 'ஹ': 'h'
        }
        virama = '்'

        out = []
        i = 0
        while i < len(text):
            ch = text[i]

            if not ('\u0B80' <= ch <= '\u0BFF'):
                out.append(ch)
                i += 1
                continue

            if ch in independent_vowels:
                out.append(independent_vowels[ch])
                i += 1
                continue

            if ch in consonants:
                base = consonants[ch]
                next_ch = text[i + 1] if i + 1 < len(text) else ''

                if next_ch == virama:
                    out.append(base)
                    i += 2
                    continue

                if next_ch in vowel_signs:
                    out.append(base + vowel_signs[next_ch])
                    i += 2
                    continue

                out.append(base + 'a')
                i += 1
                continue

            out.append(' ')
            i += 1

        romanized = ''.join(out)
        romanized = re.sub(r'\s+', ' ', romanized).strip()
        return romanized
    
    def speak(self, text: str, language: str = 'auto', blocking: bool = True) -> bool:
        """
        Speak text using Kokoro (local neural TTS, primary) with gTTS/pyttsx3 fallback.

        Priority: Kokoro (local, always-on) -> gTTS (online) -> pyttsx3 (offline system)

        Args:
            text: Text to speak
            language: 'en', 'ta', or 'auto' (auto-detect)
            blocking: Wait for speech to complete

        Returns:
            True if successful, False otherwise
        """
        if not text or len(text.strip()) == 0:
            return False
        
        # Clean text
        text = text.strip()
        
        # Auto-detect language
        if language == 'auto':
            language = self.detect_language(text)
        
        # Update current language
        self.current_language = language
        
        with self._tts_lock:
            # Print what we're saying
            lang_emoji = "🇮🇳" if language == 'ta' else "🇬🇧"
            print(f"\n{lang_emoji} 🔊 LADA: {text}")

            # For non-Kokoro engines, apply Thanglish conversion if needed
            tts_text = text
            tts_language = language
            if language == 'ta' and self.speak_thanglish_for_tamil:
                tts_text = self.tamil_to_thanglish(text)
                tts_language = 'en'

            # Build available engines then prefer the locked/default one first.
            tts_chain = []
            if self.use_gtts and GTTS_AVAILABLE:
                tts_chain.append(("gtts", lambda: self._speak_gtts(tts_text, tts_language, blocking)))
            if self.offline_engine:
                tts_chain.append(("pyttsx3", lambda: self._speak_offline(tts_text, blocking)))
            if self._kokoro_enabled and KOKORO_AVAILABLE and self._kokoro_assets_available:
                tts_chain.append(("kokoro", lambda: self._speak_kokoro(text, language)))

            # Bias first attempt toward locked engine when available.
            if self._locked_tts:
                tts_chain.sort(key=lambda item: 0 if item[0] == self._locked_tts else 1)

            for engine_name, speak_fn in tts_chain:
                try:
                    if speak_fn():
                        return True
                except Exception as exc:
                    logger.warning(f"{engine_name} TTS failed: {exc}")

            logger.error("No TTS engine succeeded")
            return False
    
    def _speak_gtts(self, text: str, language: str, blocking: bool) -> bool:
        """Speak using Google TTS (online, natural voice)"""
        try:
            # Create audio file
            audio_file = self.temp_dir / f"lada_speech_{hash(text) % 10000}.mp3"
            
            # Generate speech
            tts = gTTS(text=text, lang=language, slow=self.gtts_slow)
            tts.save(str(audio_file))
            
            # Play audio
            if blocking:
                self._play_audio(str(audio_file))
            else:
                thread = threading.Thread(target=self._play_audio, args=(str(audio_file),))
                thread.daemon = True
                thread.start()
            
            return True
            
        except Exception as e:
            logger.warning(f"gTTS error: {e}")
            return False
    
    def _speak_offline(self, text: str, blocking: bool) -> bool:
        """Speak using pyttsx3 (offline, system voice)"""
        try:
            if blocking:
                self.offline_engine.say(text)
                self.offline_engine.runAndWait()
            else:
                thread = threading.Thread(target=self._speak_offline_thread, args=(text,))
                thread.daemon = True
                thread.start()
            return True
        except Exception as e:
            logger.error(f"pyttsx3 error: {e}")
            return False
    
    def _speak_offline_thread(self, text: str):
        """Thread wrapper for non-blocking offline speech"""
        try:
            with self._tts_lock:
                self.offline_engine.say(text)
                self.offline_engine.runAndWait()
        except Exception as e:
            logger.error(f"Offline speech thread error: {e}")
    
    def _play_audio(self, filepath: str):
        """Play audio file using available player"""
        try:
            if PYGAME_AVAILABLE:
                pygame.mixer.music.load(filepath)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    pygame.time.Clock().tick(10)
            elif PLAYSOUND_AVAILABLE:
                playsound(filepath)
            else:
                # Try system player as last resort
                subprocess.Popen([
                    'wmplayer',
                    '/play',
                    '/close',
                    filepath,
                ])
        except Exception as e:
            logger.error(f"Audio playback error: {e}")
        finally:
            # Clean up temp file
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception as e:
                pass
    
    def listen(self, language: str = 'auto') -> Optional[str]:
        """
        Listen for speech and convert to text
        
        Args:
            language: 'en', 'ta', 'ta-IN', or 'auto'
            
        Returns:
            Recognized text or None
        """
        try:
            with self._open_microphone() as source:
                print("\n[Voice] Listening...")
                
                # Adjust for ambient noise
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                
                # Listen
                audio = self.recognizer.listen(
                    source,
                    timeout=self.speech_timeout,
                    phrase_time_limit=self.phrase_limit
                )
                
                print("🔄 Processing...")
                
                # Try to recognize in both languages if auto
                if language == 'auto' and self.tamil_mode:
                    text = self._recognize_mixed(audio)
                else:
                    lang_code = 'ta-IN' if language in ['ta', 'ta-IN'] else 'en-IN'
                    try:
                        text = self.recognizer.recognize_google(audio, language=lang_code)
                    except sr.RequestError as e:
                        logger.error(f"Speech recognition service error: {e}")
                        # Offline fallback with Hybrid STT
                        stt_lang = 'ta' if language in ['ta', 'ta-IN'] else 'en'
                        text = self._transcribe_hybrid_stt(audio, language=stt_lang)
                
                if text:
                    # Detect and update current language
                    self.current_language = self.detect_language(text)
                    lang_emoji = "🇮🇳" if self.current_language == 'ta' else "🇬🇧"
                    print(f"{lang_emoji} 📝 You said: {text}")
                    return text
                
                return None
                
        except sr.WaitTimeoutError:
            logger.debug("Listening timeout")
            return None
        except sr.UnknownValueError:
            print("❓ Could not understand. Please try again.")
            return None
        except sr.RequestError as e:
            logger.error(f"Speech recognition service error: {e}")
            return None
        except Exception as e:
            logger.error(f"Listen error: {e}")
            return None
    
    def _recognize_mixed(self, audio) -> Optional[str]:
        """
        Try to recognize in both Tamil and English
        Uses the result with higher confidence
        """
        results = []
        
        # Try English first
        try:
            text_en = self.recognizer.recognize_google(audio, language='en-IN')
            if text_en:
                results.append(('en', text_en))
        except sr.RequestError:
            text_en = self._transcribe_hybrid_stt(audio, language='en')
            if text_en:
                results.append(('en', text_en))
        except Exception:
            pass
        
        # Try Tamil
        try:
            text_ta = self.recognizer.recognize_google(audio, language='ta-IN')
            if text_ta:
                results.append(('ta', text_ta))
        except sr.RequestError:
            text_ta = self._transcribe_hybrid_stt(audio, language='ta')
            if text_ta:
                results.append(('ta', text_ta))
        except Exception:
            pass
        
        if not results:
            return None
        
        # Return the longer result (usually more accurate)
        # In real implementation, we'd compare confidence scores
        best = max(results, key=lambda x: len(x[1]))
        self.current_language = best[0]
        return best[1]
    
    def listen_for_wake_word(self, timeout: float = 3.0) -> bool:
        """
        Listen for wake word activation.

        Uses openwakeword (local, offline, ~50ms latency) when available.
        Falls back to Google STT + transcript matching if openwakeword is not installed.

        Returns:
            True if wake word detected
        """
        if _OWW_OK and _OWW_MODEL:
            return self._listen_oww_with_validation(timeout)

        # ── Legacy fallback: Google STT ────────────────────────────────
        try:
            with self._open_microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=3)

                try:
                    text = self.recognizer.recognize_google(audio, language='en-IN').lower()

                    for wake_word in self.wake_words:
                        if wake_word in text:
                            print(f"Wake word detected: '{wake_word}'")
                            return True

                    return False

                except sr.UnknownValueError:
                    return False
                except sr.RequestError as e:
                    logger.debug(f"Wake word SR RequestError: {e}")
                    text = (self._transcribe_hybrid_stt(audio, language='en') or '').lower()
                    for wake_word in self.wake_words:
                        if wake_word in text:
                            print(f"Wake word detected: '{wake_word}'")
                            return True
                    return False

        except sr.WaitTimeoutError:
            return False
        except Exception as e:
            logger.debug(f"Wake word error: {e}")
            return False

    def _listen_oww_with_validation(self, timeout: float = 3.0) -> bool:
        """
        Wake word detection using openwakeword + local Whisper validation.

        Stage 1 — openwakeword (continuous low-power local inference):
            Streams 80ms PCM chunks through the model until a score > threshold
            fires, or the timeout expires.  No API calls, works offline.

        Stage 2 — Whisper confirmation:
            When the model fires, records an extra 0.8 s of audio and runs
            local Whisper to check that the transcript contains a LADA wake
            phrase.  This eliminates false positives from the keyword model.
        """
        RATE = 16000
        CHUNK = 1280          # 80 ms @ 16 kHz — optimal for openwakeword
        THRESHOLD = 0.3       # Low to compensate for "alexa"≠"lada" phonemes
        FORMAT = _pyaudio.paInt16

        pa = _pyaudio.PyAudio()
        stream = None
        try:
            stream = pa.open(
                format=FORMAT, channels=1, rate=RATE,
                input=True, frames_per_buffer=CHUNK
            )
            deadline = time.time() + timeout
            while time.time() < deadline:
                raw = stream.read(CHUNK, exception_on_overflow=False)
                chunk_np = _np.frombuffer(raw, dtype=_np.int16)
                scores = _OWW_MODEL.predict(chunk_np)

                # Check if any model score exceeds threshold
                if any(s >= THRESHOLD for s in scores.values()):
                    # Stage 2: quick STT confirmation
                    confirm = self._oww_confirm_phrase(stream, RATE, CHUNK)
                    if confirm:
                        print(f"[OWW] Wake word confirmed: '{confirm}'")
                        return True
                    # False positive — keep listening
            return False

        except Exception as e:
            logger.debug(f"[OWW] Streaming error: {e}")
            # Let legacy method handle it on next call
            return False
        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            try:
                pa.terminate()
            except Exception:
                pass

    def _oww_confirm_phrase(self, stream, rate: int, chunk_size: int) -> Optional[str]:
        """
        Capture 0.8 s of follow-on audio and validate with Whisper.
        Returns the matched wake word string, or None if not confirmed.
        """
        try:
            # Capture ~0.8 s (10 chunks of 80 ms)
            frames = []
            for _ in range(10):
                frames.append(stream.read(chunk_size, exception_on_overflow=False))
            audio_bytes = b"".join(frames)

            # Run through speech_recognition for Whisper / hybrid STT
            audio_sr = sr.AudioData(audio_bytes, rate, 2)  # 16-bit = 2 bytes/sample
            transcript = (self._transcribe_hybrid_stt(audio_sr, language='en') or '').lower()
            if not transcript:
                # If hybrid STT unavailable, try Google quickly
                try:
                    transcript = self.recognizer.recognize_google(audio_sr, language='en-IN').lower()
                except Exception:
                    return None

            for wake_word in self.wake_words:
                if wake_word in transcript:
                    return wake_word
            return None
        except Exception as e:
            logger.debug(f"[OWW] Confirmation error: {e}")
            return None


    def listen_mixed(self) -> Optional[str]:
        """
        Convenience method: Listen with Tamil + English support
        Auto-detects language and responds accordingly
        """
        return self.listen(language='auto')
    
    def get_current_language(self) -> str:
        """Get the currently detected language"""
        return self.current_language
    
    def set_voice_speed(self, speed: int):
        """Set voice speed (100-300)"""
        self.voice_speed = max(100, min(300, speed))
        if self.offline_engine:
            self.offline_engine.setProperty('rate', self.voice_speed)
    
    def set_voice_volume(self, volume: float):
        """Set voice volume (0.0-1.0)"""
        self.voice_volume = max(0.0, min(1.0, volume))
        if self.offline_engine:
            self.offline_engine.setProperty('volume', self.voice_volume)
    
    def _preload_kokoro(self) -> None:
        """Pre-load Kokoro model in a background thread at startup to avoid first-speak lag."""
        if not self._kokoro_assets_available or not KOKORO_AVAILABLE or kokoro_onnx is None:
            return
        try:
            model_path, voices_path = self._kokoro_model_paths()
            self._kokoro_model = kokoro_onnx.Kokoro(str(model_path), str(voices_path))
            logger.info("✅ Kokoro TTS model pre-loaded (int8, 88MB) - zero first-speak lag")
        except Exception as e:
            self._mark_kokoro_unavailable(f"Kokoro pre-load failed, switching to fallback TTS: {e}")

    def _speak_kokoro(self, text: str, language: str = 'en') -> bool:
        """Speak using Kokoro local neural TTS (82M parameters, studio quality)"""
        if (
            not self._kokoro_assets_available
            or not KOKORO_AVAILABLE
            or kokoro_onnx is None
        ):
            return False
        
        try:
            # Load Kokoro model if not already loaded
            if self._kokoro_model is None:
                model_path, voices_path = self._kokoro_model_paths()
                
                if not model_path.exists() or not voices_path.exists():
                    self._mark_kokoro_unavailable(
                        "Kokoro model files are missing at runtime; using fallback TTS engines."
                    )
                    return False
                
                try:
                    self._kokoro_model = kokoro_onnx.Kokoro(str(model_path), str(voices_path))
                    logger.info("✅ Kokoro TTS model loaded (int8, 88MB)")
                except Exception as load_error:
                    self._mark_kokoro_unavailable(
                        f"Kokoro model could not be loaded, using fallback TTS: {load_error}"
                    )
                    return False
            
            # Kokoro currently supports English best; for Tamil, romanize it
            if language == 'ta' and self.speak_thanglish_for_tamil:
                text = self.tamil_to_thanglish(text)
            
            # Generate audio with Kokoro
            # API: kokoro.create(text, voice, speed, lang) -> (audio_array, sample_rate)
            audio_data, sample_rate = self._kokoro_model.create(
                text=text,
                voice='af_bella',  # Warm female voice (26 voices available)
                speed=1.0,
                lang='en-us'
            )
            
            # Save audio to file
            audio_path = self.temp_dir / f"lada_kokoro_{os.getpid()}.wav"
            import scipy.io.wavfile
            scipy.io.wavfile.write(str(audio_path), sample_rate, audio_data)
            
            # Play audio
            self._play_audio(str(audio_path))
            return True
            
        except Exception as e:
            logger.warning(f"Kokoro TTS error: {e}")
            return False
    
    def cleanup(self):
        """Clean up temporary files"""
        try:
            for file in self.temp_dir.glob("lada_speech_*.mp3"):
                file.unlink()
            for file in self.temp_dir.glob("lada_kokoro_*.wav"):
                file.unlink()
        except Exception as e:
            logger.debug(f"Cleanup error: {e}")

    def _load_hybrid_stt(self) -> bool:
        """Load Hybrid STT with Faster-Whisper (optimized for RTX 3050 6GB)"""
        if not HYBRID_STT_AVAILABLE:
            return False
        if self._hybrid_stt is None:
            try:
                self._hybrid_stt = HybridSpeechRecognizer(
                    prefer="faster-whisper",
                    faster_whisper_model="small",  # Good for Tamil + English
                    device="auto",  # Will use cuda if available
                    compute_type="auto"  # Will use int8_float16 on RTX 3050
                )
                return True
            except Exception as e:
                logger.warning(f"⚠️ Could not load Hybrid STT model: {e}")
                self._hybrid_stt = None
                return False
        return True

    def _transcribe_hybrid_stt(self, audio, language: Optional[str] = None) -> Optional[str]:
        """Transcribe audio using Hybrid STT (Faster-Whisper preferred)"""
        if audio is None:
            return None
        if not self._load_hybrid_stt():
            return None
        try:
            import tempfile
            import os

            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_path = f.name
                f.write(audio.get_wav_data())

            try:
                result = self._hybrid_stt.transcribe_file(temp_path, language=language)
                if result:
                    return result.text.strip() or None
                return None
            finally:
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Hybrid STT transcription failed: {e}")
            return None


# Quick test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    voice = FreeNaturalVoice(tamil_mode=True, auto_detect=True)
    
    # Test English
    voice.speak("Hello! I am LADA, your personal AI assistant.", language='en')
    
    # Test Tamil
    voice.speak("வணக்கம்! நான் லாடா. உங்களுக்கு எப்படி உதவ முடியும்?", language='ta')
    
    # Test auto-detect
    voice.speak("Hello! இது ஒரு mixed language test.", language='auto')
    
    print("\n✅ Voice test complete!")
