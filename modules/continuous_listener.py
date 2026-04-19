"""
LADA v10.0 - Continuous Voice Listener (GPU-Accelerated)
Always listening and executing commands - no wake word needed
Runs in background even when app is minimized

Features:
- Google Speech API (online, better accuracy)
- Faster-Whisper offline fallback (GPU-accelerated local STT)
- Auto-retry on connectivity issues
- Tamil + English auto-detection
- Optimized for RTX 3050 6GB (int8_float16 compute type)
"""

import threading
import time
import logging
import socket
import os
from typing import Callable, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import speech recognition
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False
    logger.warning("speech_recognition not available - pip install SpeechRecognition")

# Import hybrid STT for offline fallback (Faster-Whisper preferred)
try:
    from modules.hybrid_stt import HybridSpeechRecognizer
    HYBRID_STT_AVAILABLE = True
except ImportError:
    HybridSpeechRecognizer = None
    HYBRID_STT_AVAILABLE = False


def check_internet(timeout=2):
    """Quick internet connectivity check"""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=timeout)
        return True
    except OSError:
        return False


class ContinuousListener:
    """
    Always-on voice command listener
    Listens continuously and executes commands without wake word
    Falls back to offline Whisper when no internet
    """
    
    def __init__(self, on_command: Callable[[str], None] = None, 
                 on_listening: Callable[[], None] = None,
                 on_processing: Callable[[], None] = None):
        """
        Initialize continuous listener
        
        Args:
            on_command: Callback with the recognized command
            on_listening: Callback when starting to listen
            on_processing: Callback when processing speech
        """
        self.on_command = on_command
        self.on_listening = on_listening
        self.on_processing = on_processing
        
        self.running = False
        self.paused = False
        self.thread: Optional[threading.Thread] = None
        self.recognizer = sr.Recognizer() if SR_AVAILABLE else None
        self.microphone = None
        self.mic_device_index = self._resolve_microphone_device_index()
        
        # Hybrid STT for offline (Faster-Whisper preferred)
        self.hybrid_stt = None
        self.offline_mode = False
        self.consecutive_errors = 0
        self.max_errors_before_offline = 3
        (
            self.google_primary_language,
            self.google_secondary_language,
            self.google_auto_detect,
        ) = self._resolve_google_language_config()
        
        # Adjust recognition settings
        if self.recognizer:
            self.recognizer.energy_threshold = 300
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 0.6  # Faster response
            self.recognizer.phrase_threshold = 0.2

    def _resolve_microphone_device_index(self) -> Optional[int]:
        """Resolve preferred microphone index from env var."""
        raw = os.getenv("LADA_MIC_DEVICE_INDEX", "").strip()
        if not raw:
            return None
        try:
            idx = int(raw)
            return idx if idx >= 0 else None
        except ValueError:
            logger.warning("LADA_MIC_DEVICE_INDEX is invalid, ignoring value")
            return None

    def _resolve_google_language_config(self) -> tuple[str, str, bool]:
        """Resolve Google STT language preferences from env."""
        primary = os.getenv("LADA_STT_GOOGLE_LANGUAGE", "en-IN").strip() or "en-IN"
        secondary = os.getenv("LADA_STT_GOOGLE_SECONDARY_LANGUAGE", "ta-IN").strip() or "ta-IN"
        auto_detect = os.getenv("LADA_STT_GOOGLE_AUTO_DETECT", "1").strip().lower() in {"1", "true", "yes", "on"}
        return primary, secondary, auto_detect

    def _recognize_google(self, audio) -> Optional[str]:
        """Recognize speech with optional mixed-language probing."""
        if not self.recognizer:
            return None

        primary = self.google_primary_language
        secondary = self.google_secondary_language

        if (
            not self.google_auto_detect
            or not secondary
            or secondary.lower() == primary.lower()
        ):
            return self.recognizer.recognize_google(audio, language=primary)

        candidates = []
        for lang in (primary, secondary):
            try:
                text = self.recognizer.recognize_google(audio, language=lang)
            except sr.UnknownValueError:
                continue
            if text and text.strip():
                candidates.append(text.strip())

        if not candidates:
            return None
        return max(candidates, key=len)
    
    def _load_hybrid_stt(self):
        """Load Hybrid STT model for offline recognition (Faster-Whisper on RTX 3050 6GB)"""
        if not HYBRID_STT_AVAILABLE:
            return False
        if self.hybrid_stt is None:
            try:
                logger.info("[STT] Loading local speech model (Faster-Whisper)...")
                print("[Loading] Initializing local speech recognition (GPU accelerated)...")
                # Optimal config for RTX 3050 6GB: small model, cuda, int8_float16
                self.hybrid_stt = HybridSpeechRecognizer(
                    prefer="faster-whisper",
                    faster_whisper_model="small",  # Good for Tamil + English
                    device="auto",  # Will use cuda if available
                    compute_type="auto"  # Will use int8_float16 on cuda
                )
                device_info = "GPU" if self.hybrid_stt.device == "cuda" else "CPU"
                logger.info(f"[STT] Hybrid STT loaded ({device_info})")
                print(f"[Ready] Local speech recognition initialized ({device_info})")
                return True
            except Exception as e:
                logger.error(f"Could not load Hybrid STT: {e}")
                self.hybrid_stt = None
                return False
        return True
    
    def start(self):
        """Start continuous listening in background"""
        if not SR_AVAILABLE:
            logger.error("Cannot start - speech_recognition not installed")
            return False
        
        if self.running:
            return True

        # If stop() was called while a listen cycle was still blocking on mic input,
        # reuse the same thread on quick re-enable instead of spawning a duplicate.
        if self.thread and self.thread.is_alive():
            self.running = True
            self.paused = False
            logger.info("[Listener] Reusing existing listener thread")
            return True
        
        self.running = True
        self.paused = False
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        logger.info("[Listener] Continuous listener started - always listening")
        print("\n[Listener] Listening...")
        return True
    
    def stop(self):
        """Stop listening"""
        self.paused = True
        self.running = False
        if self.thread:
            current = threading.current_thread()
            if self.thread is not current:
                self.thread.join(timeout=2)
            if not self.thread.is_alive():
                self.thread = None
        logger.info("[Listener] Continuous listener stopped")
    
    def pause(self):
        """Pause detection (while speaking/processing)"""
        self.paused = True
    
    def resume(self):
        """Resume detection"""
        if not self.running:
            logger.debug("[Listener] Resume ignored (listener not running)")
            return False
        self.paused = False
        self.consecutive_errors = 0  # Reset error count
        print("\n[Listener] Listening...")
        return True
    
    def _listen_loop(self):
        """Main listening loop"""
        try:
            if self.mic_device_index is None:
                self.microphone = sr.Microphone()
            else:
                try:
                    self.microphone = sr.Microphone(device_index=self.mic_device_index)
                except Exception as exc:
                    logger.warning(f"Configured microphone index {self.mic_device_index} unavailable: {exc}")
                    self.microphone = sr.Microphone()
            
            # Calibrate for ambient noise
            with self.microphone as source:
                logger.info("[Listener] Calibrating for ambient noise...")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                logger.info(f"[Listener] Energy threshold: {self.recognizer.energy_threshold}")
            
            while self.running:
                if self.paused:
                    time.sleep(0.1)
                    continue
                
                try:
                    self._listen_once()
                except Exception as e:
                    logger.debug(f"Listen cycle error: {e}")
                    time.sleep(0.3)
                    
        except Exception as e:
            logger.error(f"Continuous listener error: {e}")
            self.running = False
    
    def _listen_once(self):
        """Single listen attempt with online/offline fallback"""
        try:
            with self.microphone as source:
                # Signal that we're listening
                if self.on_listening:
                    self.on_listening()
                
                # Listen for audio with longer timeout for natural speech
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=15)

            if not self.running or self.paused:
                return
            
            # Signal processing (only once, not spamming)
            if self.on_processing:
                self.on_processing()
            
            text = None
            
            # Try Google first (better accuracy) if online
            if not self.offline_mode:
                try:
                    text = self._recognize_google(audio)
                    self.consecutive_errors = 0  # Reset on success
                    
                except sr.RequestError as e:
                    self.consecutive_errors += 1
                    logger.warning(f"Google Speech API error ({self.consecutive_errors}/{self.max_errors_before_offline}): {e}")
                    
                    if self.consecutive_errors >= self.max_errors_before_offline:
                        print("[Warning] Connection issues detected, switching to offline mode...")
                        self.offline_mode = True
                    else:
                        print(f"[Warning] Retrying... ({self.consecutive_errors}/{self.max_errors_before_offline})")
                        time.sleep(0.5)
                        return
            
            # Offline fallback with Hybrid STT (Faster-Whisper)
            if self.offline_mode and HYBRID_STT_AVAILABLE and text is None:
                if self._load_hybrid_stt():
                    try:
                        # Save audio to temp file for transcription
                        import tempfile
                        import os
                        
                        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                            temp_path = f.name
                            wav_data = audio.get_wav_data()
                            f.write(wav_data)
                        
                        # Transcribe with Hybrid STT (auto-detects Tamil/English)
                        result = self.hybrid_stt.transcribe_file(temp_path, language=None)  # Auto-detect
                        if result and result.text:
                            text = result.text.strip()
                        else:
                            logger.debug("[Hybrid STT] No transcription result")
                        
                        # Clean up
                        os.unlink(temp_path)
                        
                        # Check if back online periodically
                        if check_internet():
                            print("[Online] Back online - switching to Google Speech")
                            self.offline_mode = False
                            self.consecutive_errors = 0
                            
                    except Exception as e:
                        logger.error(f"Hybrid STT error: {e}")
            
            # Process recognized text
            if text and text.strip():
                if not self.running or self.paused:
                    return
                mode = "[Offline]" if self.offline_mode else "[Online]"
                logger.info(f"[Listener] Heard: '{text}'")
                print(f"{mode} You said: {text}")
                
                # Trigger command callback
                if self.on_command:
                    self.on_command(text)
                        
        except sr.UnknownValueError:
            pass  # Didn't understand - continue listening
        except sr.WaitTimeoutError:
            pass  # No speech detected - continue listening


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    def on_command(cmd):
        print(f"\n[Command] Received: {cmd}")
        print("[Listener] Listening...")
    
    listener = ContinuousListener(on_command=on_command)
    
    print("=" * 50)
    print("LADA Continuous Listener - Test Mode")
    print("=" * 50)
    print("Speak any command - no wake word needed!")
    print("Press Ctrl+C to stop")
    print("=" * 50)
    
    listener.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        listener.stop()
        print("\nStopped.")
