"""
LADA v7.0 - Advanced Voice Module
Wake word detection, continuous listening, and voice commands
"""

import os
import sys
import time
import struct
import logging
import threading
import queue
from typing import Optional, Callable, Dict, Any
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# Check for audio dependencies
PYAUDIO_OK = False
SPEECH_RECOGNITION_OK = False
PVPORCUPINE_OK = False
WHISPER_OK = False

try:
    import pyaudio
    PYAUDIO_OK = True
except ImportError:
    logger.warning("[Voice] PyAudio not available")

try:
    import speech_recognition as sr
    SPEECH_RECOGNITION_OK = True
except ImportError:
    logger.warning("[Voice] speech_recognition not available")

try:
    import pvporcupine
    PVPORCUPINE_OK = True
except ImportError:
    logger.warning("[Voice] pvporcupine (wake word) not available")

try:
    import whisper
    WHISPER_OK = True
except ImportError:
    logger.warning("[Voice] OpenAI Whisper not available")


class WakeWordDetector:
    """
    Wake word detection using Porcupine or keyword spotting.
    
    Listens for wake words like "Hey LADA", "LADA", etc.
    """
    
    DEFAULT_WAKE_WORDS = ['lada', 'hey lada', 'computer', 'jarvis']
    
    def __init__(
        self,
        wake_words: list = None,
        porcupine_key: str = None,
        callback: Callable = None
    ):
        """
        Initialize wake word detector.
        
        Args:
            wake_words: List of wake words to listen for
            porcupine_key: Picovoice API key (for Porcupine)
            callback: Function to call when wake word detected
        """
        self.wake_words = wake_words or self.DEFAULT_WAKE_WORDS
        self.porcupine_key = porcupine_key
        self.callback = callback
        self.is_listening = False
        self._thread = None
        self._stop_event = threading.Event()
        
        # Porcupine instance (if available)
        self.porcupine = None
        self.pa = None
        self.audio_stream = None
    
    def start(self):
        """Start listening for wake word."""
        if self.is_listening:
            return

        self._stop_event.clear()
        if PVPORCUPINE_OK and self.porcupine_key:
            self._thread = threading.Thread(target=self._listen_porcupine, daemon=True)
        elif SPEECH_RECOGNITION_OK:
            self._thread = threading.Thread(target=self._listen_speech_recognition, daemon=True)
        else:
            logger.error("[WakeWord] No audio library available")
            self.is_listening = False
            return

        self.is_listening = True
        self._thread.start()
        logger.info(f"[WakeWord] Started listening for: {self.wake_words}")
    
    def stop(self):
        """Stop listening for wake word."""
        self._stop_event.set()
        self.is_listening = False
        
        if self.porcupine:
            self.porcupine.delete()
            self.porcupine = None
        
        if self.audio_stream:
            self.audio_stream.close()
        
        if self.pa:
            self.pa.terminate()
        
        logger.info("[WakeWord] Stopped listening")
    
    def _listen_porcupine(self):
        """Listen using Porcupine wake word engine."""
        try:
            # Initialize Porcupine
            self.porcupine = pvporcupine.create(
                access_key=self.porcupine_key,
                keywords=["computer"]  # Built-in keyword
            )
            
            self.pa = pyaudio.PyAudio()
            self.audio_stream = self.pa.open(
                rate=self.porcupine.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=self.porcupine.frame_length
            )
            
            while not self._stop_event.is_set():
                pcm = self.audio_stream.read(self.porcupine.frame_length)
                pcm = struct.unpack_from("h" * self.porcupine.frame_length, pcm)
                
                keyword_index = self.porcupine.process(pcm)
                if keyword_index >= 0:
                    logger.info(f"[WakeWord] Detected: {self.wake_words[keyword_index]}")
                    if self.callback:
                        self.callback()
                        
        except Exception as e:
            logger.error(f"[WakeWord] Porcupine error: {e}")
    
    def _listen_speech_recognition(self):
        """Listen using speech_recognition library with keyword spotting."""
        recognizer = sr.Recognizer()
        
        try:
            with sr.Microphone() as source:
                logger.info("[WakeWord] Adjusting for ambient noise...")
                recognizer.adjust_for_ambient_noise(source, duration=1)
                
                while not self._stop_event.is_set():
                    try:
                        # Listen for short phrases
                        audio = recognizer.listen(source, timeout=2, phrase_time_limit=3)
                        
                        # Try to recognize
                        try:
                            text = recognizer.recognize_google(audio).lower()
                            
                            # Check for wake words
                            for wake_word in self.wake_words:
                                if wake_word in text:
                                    logger.info(f"[WakeWord] Detected: {wake_word} in '{text}'")
                                    if self.callback:
                                        self.callback()
                                    break
                                    
                        except sr.UnknownValueError:
                            pass  # Couldn't understand
                        except sr.RequestError as e:
                            logger.warning(f"[WakeWord] API error: {e}")
                            
                    except sr.WaitTimeoutError:
                        pass  # No speech detected
                        
        except Exception as e:
            logger.error(f"[WakeWord] Error: {e}")


class ContinuousListener:
    """
    Continuous voice input listener.
    
    After wake word detection, listens for commands and transcribes them.
    """
    
    def __init__(self, use_whisper: bool = False):
        """
        Initialize continuous listener.
        
        Args:
            use_whisper: Use OpenAI Whisper for transcription
        """
        self.use_whisper = use_whisper and WHISPER_OK
        self.whisper_model = None
        self.recognizer = sr.Recognizer() if SPEECH_RECOGNITION_OK else None
        self.is_listening = False
        self.command_queue = queue.Queue()
        self._thread = None
        self._stop_event = threading.Event()
        
        # Load Whisper model if needed
        if self.use_whisper:
            try:
                self.whisper_model = whisper.load_model("base")
                logger.info("[Voice] Whisper model loaded")
            except Exception as e:
                logger.error(f"[Voice] Failed to load Whisper: {e}")
                self.use_whisper = False
    
    def start(self, duration: float = 10.0, callback: Callable = None):
        """
        Start listening for commands.
        
        Args:
            duration: How long to listen (seconds)
            callback: Function to call with transcribed text
        """
        if not SPEECH_RECOGNITION_OK:
            logger.error("[Voice] speech_recognition not available")
            return
        
        self._stop_event.clear()
        self.is_listening = True
        
        self._thread = threading.Thread(
            target=self._listen_loop,
            args=(duration, callback),
            daemon=True
        )
        self._thread.start()
    
    def stop(self):
        """Stop listening."""
        self._stop_event.set()
        self.is_listening = False
    
    def _listen_loop(self, duration: float, callback: Callable):
        """Main listening loop."""
        with sr.Microphone() as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
            
            start_time = time.time()
            
            while not self._stop_event.is_set():
                if time.time() - start_time > duration:
                    break
                
                try:
                    logger.info("[Voice] Listening...")
                    audio = self.recognizer.listen(
                        source,
                        timeout=5,
                        phrase_time_limit=15
                    )
                    
                    # Transcribe
                    text = self._transcribe(audio)
                    
                    if text:
                        logger.info(f"[Voice] Transcribed: {text}")
                        self.command_queue.put(text)
                        
                        if callback:
                            callback(text)
                        
                except sr.WaitTimeoutError:
                    pass
                except Exception as e:
                    logger.error(f"[Voice] Listen error: {e}")
        
        self.is_listening = False
    
    def _transcribe(self, audio) -> Optional[str]:
        """Transcribe audio to text."""
        if self.use_whisper:
            return self._transcribe_whisper(audio)
        else:
            return self._transcribe_google(audio)
    
    def _transcribe_google(self, audio) -> Optional[str]:
        """Transcribe using Google Speech Recognition."""
        try:
            text = self.recognizer.recognize_google(audio)
            return text
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            logger.error(f"[Voice] Google API error: {e}")
            return None
    
    def _transcribe_whisper(self, audio) -> Optional[str]:
        """Transcribe using OpenAI Whisper."""
        if not self.whisper_model:
            return self._transcribe_google(audio)
        
        try:
            # Save audio to temp file
            temp_path = Path("cache/temp_audio.wav")
            temp_path.parent.mkdir(exist_ok=True)
            
            with open(temp_path, "wb") as f:
                f.write(audio.get_wav_data())
            
            # Transcribe with Whisper
            result = self.whisper_model.transcribe(str(temp_path))
            
            # Clean up
            temp_path.unlink()
            
            return result.get("text", "").strip()
            
        except Exception as e:
            logger.error(f"[Voice] Whisper error: {e}")
            return self._transcribe_google(audio)
    
    def get_command(self, timeout: float = 0.1) -> Optional[str]:
        """Get next command from queue."""
        try:
            return self.command_queue.get(timeout=timeout)
        except queue.Empty:
            return None


class VoiceAssistant:
    """
    Complete voice assistant with wake word and continuous listening.
    
    Features:
    - Wake word detection
    - Continuous listening after wake
    - Text-to-speech responses
    - Voice activity detection
    """
    
    def __init__(
        self,
        wake_words: list = None,
        porcupine_key: str = None,
        use_whisper: bool = False,
        on_command: Callable = None
    ):
        """
        Initialize voice assistant.
        
        Args:
            wake_words: Wake words to listen for
            porcupine_key: Picovoice API key
            use_whisper: Use Whisper for transcription
            on_command: Callback for voice commands
        """
        self.on_command = on_command
        self.is_active = False
        self.last_activity = None
        
        # Initialize components
        self.wake_detector = WakeWordDetector(
            wake_words=wake_words,
            porcupine_key=porcupine_key,
            callback=self._on_wake
        )
        
        self.listener = ContinuousListener(use_whisper=use_whisper)
        
        # TTS engine
        self.tts_engine = None
        try:
            import pyttsx3
            self.tts_engine = pyttsx3.init()
            self.tts_engine.setProperty('rate', 150)
        except:
            logger.warning("[Voice] pyttsx3 not available")
    
    def start(self):
        """Start the voice assistant."""
        logger.info("[VoiceAssistant] Starting...")
        self.is_active = True
        self.wake_detector.start()
        
        # Play startup sound
        self.speak("LADA voice assistant ready")
    
    def stop(self):
        """Stop the voice assistant."""
        self.is_active = False
        self.wake_detector.stop()
        self.listener.stop()
        logger.info("[VoiceAssistant] Stopped")
    
    def _on_wake(self):
        """Called when wake word is detected."""
        logger.info("[VoiceAssistant] Wake word detected!")
        self.last_activity = datetime.now()
        
        # Play acknowledgment
        self.speak("Yes?")
        
        # Start listening for command
        self.listener.start(
            duration=10,
            callback=self._on_command
        )
    
    def _on_command(self, text: str):
        """Called when a command is transcribed."""
        if not text:
            return
        
        logger.info(f"[VoiceAssistant] Command: {text}")
        self.last_activity = datetime.now()
        
        if self.on_command:
            self.on_command(text)
    
    def speak(self, text: str):
        """Speak text using TTS."""
        if not text:
            return
        
        logger.info(f"[VoiceAssistant] Speaking: {text[:50]}...")
        
        if self.tts_engine:
            try:
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
            except Exception as e:
                logger.error(f"[VoiceAssistant] TTS error: {e}")
        else:
            # Try playsound for pre-recorded responses
            logger.info(f"[VoiceAssistant] (No TTS) Would say: {text}")
    
    def listen_once(self, timeout: float = 5.0) -> Optional[str]:
        """
        Listen for a single command (without wake word).
        
        Args:
            timeout: How long to listen
            
        Returns:
            Transcribed text or None
        """
        if not SPEECH_RECOGNITION_OK:
            return None
        
        recognizer = sr.Recognizer()
        
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                logger.info("[Voice] Listening (once)...")
                
                audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=10)
                
                # Transcribe
                if self.listener.use_whisper:
                    text = self.listener._transcribe_whisper(audio)
                else:
                    text = self.listener._transcribe_google(audio)
                
                return text
                
        except sr.WaitTimeoutError:
            return None
        except Exception as e:
            logger.error(f"[Voice] Listen error: {e}")
            return None


class VoiceCommands:
    """
    Voice command parser and handler.
    
    Parses voice input and routes to appropriate actions.
    """
    
    # Command patterns
    COMMANDS = {
        'search': r'(?:search|find|look up|google)\s+(.+)',
        'open': r'(?:open|launch|start)\s+(.+)',
        'play': r'(?:play|listen to)\s+(.+)',
        'set_timer': r'(?:set|create)\s+(?:a\s+)?timer\s+(?:for\s+)?(\d+)\s+(minutes?|seconds?|hours?)',
        'set_reminder': r'(?:remind|set reminder)\s+(?:me\s+)?(?:to\s+)?(.+)',
        'weather': r'(?:what.s the |how.s the )?weather\s*(?:in\s+)?(.+)?',
        'time': r'what(?:.s| is) the time',
        'date': r'what(?:.s| is) (?:the )?(?:date|today)',
        'stop': r'(?:stop|cancel|nevermind|never mind)',
        'thank': r'(?:thank you|thanks)',
    }
    
    def __init__(self):
        """Initialize command parser."""
        import re
        self.patterns = {
            cmd: re.compile(pattern, re.IGNORECASE)
            for cmd, pattern in self.COMMANDS.items()
        }
    
    def parse(self, text: str) -> Dict[str, Any]:
        """
        Parse a voice command.
        
        Args:
            text: Transcribed voice input
            
        Returns:
            Parsed command dict with 'command' and 'args'
        """
        text = text.strip()
        
        for cmd_name, pattern in self.patterns.items():
            match = pattern.search(text)
            if match:
                return {
                    'command': cmd_name,
                    'args': match.groups(),
                    'raw': text
                }
        
        # Default: treat as general query
        return {
            'command': 'query',
            'args': (text,),
            'raw': text
        }


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

def create_voice_assistant(
    on_command: Callable = None,
    use_whisper: bool = False
) -> VoiceAssistant:
    """Create and return a configured voice assistant."""
    return VoiceAssistant(
        wake_words=['lada', 'hey lada', 'computer'],
        use_whisper=use_whisper,
        on_command=on_command
    )


def listen_for_command(timeout: float = 10.0) -> Optional[str]:
    """Listen for a single voice command (convenience function)."""
    listener = ContinuousListener()
    
    if not SPEECH_RECOGNITION_OK:
        return None
    
    recognizer = sr.Recognizer()
    
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            print("🎤 Listening...")
            
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=15)
            text = recognizer.recognize_google(audio)
            
            return text
            
    except sr.WaitTimeoutError:
        return None
    except sr.UnknownValueError:
        return None
    except Exception as e:
        logger.error(f"[Voice] Error: {e}")
        return None


# ============================================================
# EXAMPLE USAGE
# ============================================================
if __name__ == "__main__":
    print("🚀 Testing Advanced Voice Module...")
    print(f"  PyAudio: {'✓' if PYAUDIO_OK else '✗'}")
    print(f"  SpeechRecognition: {'✓' if SPEECH_RECOGNITION_OK else '✗'}")
    print(f"  Porcupine: {'✓' if PVPORCUPINE_OK else '✗'}")
    print(f"  Whisper: {'✓' if WHISPER_OK else '✗'}")
    
    # Test command parser
    print("\n📝 Testing command parser...")
    parser = VoiceCommands()
    
    test_commands = [
        "search for the best restaurants",
        "open Chrome",
        "set a timer for 5 minutes",
        "what's the weather in Delhi",
        "what time is it",
        "remind me to call mom",
    ]
    
    for cmd in test_commands:
        result = parser.parse(cmd)
        print(f"  '{cmd}' → {result['command']}: {result['args']}")
    
    # Test voice listening (only if available)
    if SPEECH_RECOGNITION_OK:
        print("\n🎤 Testing voice input (5 seconds)...")
        print("  Say something...")
        
        text = listen_for_command(timeout=5)
        
        if text:
            print(f"  You said: {text}")
            result = parser.parse(text)
            print(f"  Parsed as: {result['command']}")
        else:
            print("  No speech detected")
    
    print("\n✅ Voice module test complete!")
