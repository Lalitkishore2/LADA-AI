"""
LADA v7.0 - Wake Word Detection Module
Always listening for "LADA" to activate voice control
"""

import threading
import queue
import time
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Try to import speech recognition
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False
    logger.warning("speech_recognition not available - pip install SpeechRecognition")

# Optional offline fallback
try:
    import whisper  # type: ignore

    WHISPER_AVAILABLE = True
except Exception:
    whisper = None  # type: ignore
    WHISPER_AVAILABLE = False


class WakeWordDetector:
    """
    Background wake word detector
    Listens for 'L' (Elle) and triggers callback when detected
    """
    
    # All phonetic variations of "L" / "Elle" for reliable detection
    WAKE_WORDS = [
        'l', 'el', 'ell', 'elle', 'ale', 'al', 'all',
        'hell', 'well', 'bell', 'tell', 'dell', 'sell',
        'hey el', 'hey ell', 'hey elle', 'hey l',
        'hail', 'hale', 'ale', 'ail',
        'lada', 'lata', 'ladder'  # Keep old ones for backwards compatibility
    ]
    
    def __init__(self, on_wake: Callable[[], None] = None, on_command: Callable[[str], None] = None):
        """
        Initialize wake word detector
        
        Args:
            on_wake: Callback when wake word detected (no command yet)
            on_command: Callback with the command after wake word
        """
        self.on_wake = on_wake
        self.on_command = on_command
        self.running = False
        self.paused = False
        self.thread: Optional[threading.Thread] = None
        self.recognizer = sr.Recognizer() if SR_AVAILABLE else None
        self.microphone = None

        self._whisper_model = None
        
        # Adjust for ambient noise on start
        if self.recognizer:
            self.recognizer.energy_threshold = 300
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = 0.8
    
    def start(self):
        """Start listening in background"""
        if not SR_AVAILABLE:
            logger.error("Cannot start wake word - speech_recognition not installed")
            return False
        
        if self.running:
            return True
        
        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        logger.info("🎤 Wake word detector started - listening for 'L' (Elle)")
        return True
    
    def stop(self):
        """Stop listening"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        logger.info("🎤 Wake word detector stopped")
    
    def pause(self):
        """Pause detection (while speaking/processing)"""
        self.paused = True
    
    def resume(self):
        """Resume detection"""
        self.paused = False
    
    def _listen_loop(self):
        """Main listening loop"""
        try:
            self.microphone = sr.Microphone()
            
            # Calibrate for ambient noise
            with self.microphone as source:
                logger.info("🎤 Calibrating for ambient noise...")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                logger.info(f"🎤 Energy threshold: {self.recognizer.energy_threshold}")
            
            while self.running:
                if self.paused:
                    time.sleep(0.1)
                    continue
                
                try:
                    self._listen_once()
                except Exception as e:
                    logger.debug(f"Listen cycle error: {e}")
                    time.sleep(0.5)
                    
        except Exception as e:
            logger.error(f"Wake word detector error: {e}")
            self.running = False
    
    def _listen_once(self):
        """Single listen attempt"""
        try:
            with self.microphone as source:
                # Listen for audio
                audio = self.recognizer.listen(source, timeout=3, phrase_time_limit=5)
            
            # Recognize speech
            try:
                text = self.recognizer.recognize_google(audio).lower()
                logger.debug(f"Heard: {text}")
                
                # Check for wake word
                wake_detected = False
                command = text
                
                for wake_word in self.WAKE_WORDS:
                    if wake_word in text:
                        wake_detected = True
                        # Extract command after wake word
                        parts = text.split(wake_word, 1)
                        if len(parts) > 1:
                            command = parts[1].strip()
                        else:
                            command = ""
                        break
                
                if wake_detected:
                    logger.info(f"🎤 Wake word detected! Command: '{command}'")
                    
                    # Trigger wake callback
                    if self.on_wake:
                        self.on_wake()
                    
                    # If we got a command, trigger command callback
                    if command and self.on_command:
                        self.on_command(command)
                    elif self.on_command:
                        # No command after wake word, wait for follow-up
                        self._listen_for_command()
                        
            except sr.UnknownValueError:
                pass  # Didn't understand
            except sr.RequestError as e:
                logger.warning(f"Google Speech API error: {e}")

                # Offline fallback (best-effort): try Whisper if installed
                text = self._transcribe_whisper(audio)
                if text:
                    text = text.lower()
                    logger.debug(f"[Whisper] Heard: {text}")

                    wake_detected = False
                    command = text

                    for wake_word in self.WAKE_WORDS:
                        if wake_word in text:
                            wake_detected = True
                            parts = text.split(wake_word, 1)
                            if len(parts) > 1:
                                command = parts[1].strip()
                            else:
                                command = ""
                            break

                    if wake_detected:
                        logger.info(f"🎤 Wake word detected! Command: '{command}'")

                        if self.on_wake:
                            self.on_wake()

                        if command and self.on_command:
                            self.on_command(command)
                        elif self.on_command:
                            self._listen_for_command()
                
        except sr.WaitTimeoutError:
            pass  # No speech detected
    
    def _listen_for_command(self):
        """Listen for command after wake word"""
        logger.info("🎤 Listening for command...")
        
        try:
            with self.microphone as source:
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
            
            try:
                text = self.recognizer.recognize_google(audio).lower()
            except sr.RequestError as e:
                logger.warning(f"Google Speech API error (command): {e}")
                text = (self._transcribe_whisper(audio) or "").lower()
            logger.info(f"🎤 Command: '{text}'")
            
            if self.on_command:
                self.on_command(text)
                
        except Exception as e:
            logger.debug(f"Command listen error: {e}")

    def _load_whisper(self) -> bool:
        if not WHISPER_AVAILABLE:
            return False
        if self._whisper_model is None:
            try:
                self._whisper_model = whisper.load_model("tiny")  # type: ignore[union-attr]
            except Exception as e:
                logger.warning(f"[WakeWord] Whisper init failed: {e}")
                self._whisper_model = None
                return False
        return True

    def _transcribe_whisper(self, audio) -> Optional[str]:
        if not self._load_whisper():
            return None
        try:
            import tempfile
            import os

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_path = f.name
                f.write(audio.get_wav_data())

            try:
                result = self._whisper_model.transcribe(temp_path)  # type: ignore[union-attr]
                text = (result.get("text") or "").strip()
                return text or None
            finally:
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"[WakeWord] Whisper transcription failed: {e}")
            return None


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    def on_wake():
        print("🔔 LADA activated!")
    
    def on_command(cmd):
        print(f"📝 Command: {cmd}")
    
    detector = WakeWordDetector(on_wake=on_wake, on_command=on_command)
    
    print("Starting wake word detector...")
    print("Say 'LADA' followed by a command")
    print("Press Ctrl+C to stop")
    
    detector.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        detector.stop()
        print("\nStopped.")
