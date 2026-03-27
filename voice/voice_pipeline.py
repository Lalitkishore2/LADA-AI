"""LADA Voice Pipeline - Enhanced Wake Word System

Provides continuous listening mode with "LADA WAKEUP" and "LADA TURN OFF" commands.

Features:
- "LADA WAKEUP" → Start continuous listening (stays active)
- "LADA TURN OFF" → Stop listening completely
- No need to repeat wake word after activation
- Integrates with existing voice_tamil_free.py

Usage:
    from voice.voice_pipeline import VoicePipeline
    
    pipeline = VoicePipeline()
    pipeline.start()  # Begins wake word listening
    
    # User says "LADA WAKEUP" → continuous mode starts
    # User gives commands naturally
    # User says "LADA TURN OFF" → stops listening
"""

from __future__ import annotations

import os
import time
import threading
import logging
from typing import Optional, Callable, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# Import voice components
try:
    from voice_tamil_free import FreeNaturalVoice
    VOICE_AVAILABLE = True
except ImportError:
    FreeNaturalVoice = None
    VOICE_AVAILABLE = False

try:
    from voice.xtts_engine import XTTSEngine, FallbackTTSEngine
    XTTS_AVAILABLE = True
except ImportError:
    XTTSEngine = None
    FallbackTTSEngine = None
    XTTS_AVAILABLE = False


class VoiceState(Enum):
    """Voice pipeline states."""
    IDLE = "idle"              # Not listening
    LISTENING_WAKE = "wake"    # Listening for wake word
    CONTINUOUS = "continuous"  # Continuous listening mode (after WAKEUP)
    PROCESSING = "processing"  # Processing a command


@dataclass
class VoiceConfig:
    """Voice pipeline configuration."""
    # Wake phrases
    wake_phrases: List[str] = field(default_factory=lambda: [
        "lada", "hey lada", "okay lada", "lada wakeup", "lada wake up"
    ])
    
    # Turn off phrases
    turnoff_phrases: List[str] = field(default_factory=lambda: [
        "lada turn off", "lada stop", "lada sleep", "lada goodbye",
        "turn off lada", "stop listening", "go to sleep"
    ])
    
    # Timeouts
    wake_timeout: float = 5.0           # Seconds to listen for wake word
    command_timeout: float = 10.0       # Seconds to listen for command
    continuous_idle_timeout: float = 60.0  # Seconds before auto-sleep in continuous mode
    
    # TTS engine preference
    tts_engine: str = "auto"  # auto, xtts, kokoro, gtts, pyttsx3


class VoicePipeline:
    """Enhanced voice pipeline with continuous listening mode.
    
    Lifecycle:
    1. IDLE → LISTENING_WAKE (start())
    2. User says "LADA WAKEUP" → CONTINUOUS
    3. User gives commands → PROCESSING → CONTINUOUS
    4. User says "LADA TURN OFF" → IDLE
    
    Or traditional wake-per-command:
    1. IDLE → LISTENING_WAKE
    2. User says "Hey LADA" → single command → LISTENING_WAKE
    """
    
    def __init__(
        self,
        config: Optional[VoiceConfig] = None,
        on_command: Optional[Callable[[str], str]] = None,
        on_state_change: Optional[Callable[[VoiceState], None]] = None,
    ):
        """Initialize voice pipeline.
        
        Args:
            config: Voice configuration
            on_command: Callback when command is received (returns response to speak)
            on_state_change: Callback when state changes
        """
        self.config = config or VoiceConfig()
        self.on_command = on_command
        self.on_state_change = on_state_change
        
        self._state = VoiceState.IDLE
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_activity = time.time()
        
        # Voice components
        self._voice: Optional[FreeNaturalVoice] = None
        self._tts_engine = None
        
        # Load from env
        self._load_config_from_env()
        
        logger.info(f"[VoicePipeline] Initialized: state={self._state.value}")
    
    def _load_config_from_env(self):
        """Load configuration from environment variables."""
        # Additional wake phrases from env
        env_wakes = os.getenv("LADA_WAKE_PHRASES", "")
        if env_wakes:
            self.config.wake_phrases.extend(env_wakes.lower().split(","))
        
        # TTS engine preference
        env_tts = os.getenv("TTS_ENGINE", "")
        if env_tts:
            self.config.tts_engine = env_tts.lower()
        
        # Timeouts
        try:
            self.config.continuous_idle_timeout = float(
                os.getenv("LADA_CONTINUOUS_TIMEOUT", "60")
            )
        except ValueError:
            pass
    
    @property
    def state(self) -> VoiceState:
        """Current pipeline state."""
        return self._state
    
    @state.setter
    def state(self, new_state: VoiceState):
        """Set state with callback."""
        old_state = self._state
        self._state = new_state
        if old_state != new_state:
            logger.info(f"[VoicePipeline] State: {old_state.value} → {new_state.value}")
            if self.on_state_change:
                try:
                    self.on_state_change(new_state)
                except Exception as e:
                    logger.error(f"[VoicePipeline] State callback error: {e}")
    
    def _init_voice(self) -> bool:
        """Initialize voice components."""
        if not VOICE_AVAILABLE:
            logger.error("[VoicePipeline] FreeNaturalVoice not available")
            return False
        
        try:
            self._voice = FreeNaturalVoice()
            self._voice.wake_words = self.config.wake_phrases
            
            # Initialize TTS engine
            if XTTS_AVAILABLE and self.config.tts_engine in ("auto", "xtts"):
                self._tts_engine = XTTSEngine()
            
            return True
        except Exception as e:
            logger.error(f"[VoicePipeline] Voice init error: {e}")
            return False
    
    def start(self) -> bool:
        """Start the voice pipeline.
        
        Returns:
            True if started successfully
        """
        with self._lock:
            if self._running:
                logger.warning("[VoicePipeline] Already running")
                return True
            
            if not self._init_voice():
                return False
            
            self._running = True
            self.state = VoiceState.LISTENING_WAKE
            
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            
            logger.info("[VoicePipeline] Started")
            return True
    
    def stop(self):
        """Stop the voice pipeline."""
        with self._lock:
            self._running = False
            self.state = VoiceState.IDLE
        
        if self._thread:
            self._thread.join(timeout=2.0)
        
        logger.info("[VoicePipeline] Stopped")
    
    def _run_loop(self):
        """Main voice pipeline loop."""
        while self._running:
            try:
                if self.state == VoiceState.LISTENING_WAKE:
                    self._handle_wake_listening()
                
                elif self.state == VoiceState.CONTINUOUS:
                    self._handle_continuous_listening()
                
                elif self.state == VoiceState.IDLE:
                    time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"[VoicePipeline] Loop error: {e}")
                time.sleep(0.5)
    
    def _handle_wake_listening(self):
        """Handle wake word listening state."""
        if not self._voice:
            return
        
        # Listen for wake word
        detected = self._voice.listen_for_wake_word(timeout=self.config.wake_timeout)
        
        if detected:
            self._last_activity = time.time()
            
            # Listen for the actual command
            command = self._voice.listen(language='auto')
            
            if command:
                # Check for continuous mode activation
                if self._is_wakeup_command(command):
                    self._activate_continuous_mode()
                else:
                    # Process single command
                    self._process_command(command)
    
    def _handle_continuous_listening(self):
        """Handle continuous listening state (after LADA WAKEUP)."""
        if not self._voice:
            return
        
        # Check for idle timeout
        idle_time = time.time() - self._last_activity
        if idle_time > self.config.continuous_idle_timeout:
            logger.info("[VoicePipeline] Continuous mode timeout, sleeping")
            self._speak("Going to sleep. Say LADA WAKEUP to resume.")
            self.state = VoiceState.LISTENING_WAKE
            return
        
        # Listen for command (no wake word needed)
        command = self._voice.listen(language='auto')
        
        if command:
            self._last_activity = time.time()
            
            # Check for turn off command
            if self._is_turnoff_command(command):
                self._deactivate_continuous_mode()
            else:
                # Process command
                self._process_command(command)
    
    def _is_wakeup_command(self, text: str) -> bool:
        """Check if text is a wakeup command."""
        text_lower = text.lower().strip()
        wakeup_patterns = ["wakeup", "wake up", "start listening", "continuous mode"]
        
        for pattern in wakeup_patterns:
            if pattern in text_lower:
                return True
        
        # Also check if it's just the wake word with "wakeup"
        for wake in self.config.wake_phrases:
            if "wakeup" in wake or "wake up" in wake:
                if wake in text_lower:
                    return True
        
        return False
    
    def _is_turnoff_command(self, text: str) -> bool:
        """Check if text is a turn off command."""
        text_lower = text.lower().strip()
        
        for phrase in self.config.turnoff_phrases:
            if phrase in text_lower:
                return True
        
        return False
    
    def _activate_continuous_mode(self):
        """Activate continuous listening mode."""
        self.state = VoiceState.CONTINUOUS
        self._last_activity = time.time()
        self._speak("I'm listening. Just speak naturally. Say LADA TURN OFF when done.")
        logger.info("[VoicePipeline] Continuous mode activated")
    
    def _deactivate_continuous_mode(self):
        """Deactivate continuous listening mode."""
        self._speak("Okay, I'll stop listening now. Say LADA WAKEUP to resume.")
        self.state = VoiceState.LISTENING_WAKE
        logger.info("[VoicePipeline] Continuous mode deactivated")
    
    def _process_command(self, command: str):
        """Process a voice command."""
        self.state = VoiceState.PROCESSING
        
        response = None
        if self.on_command:
            try:
                response = self.on_command(command)
            except Exception as e:
                logger.error(f"[VoicePipeline] Command callback error: {e}")
                response = "Sorry, I encountered an error processing that command."
        
        if response:
            self._speak(response)
        
        # Return to appropriate state
        if self._state == VoiceState.PROCESSING:
            # If we were in continuous mode before, go back to it
            # Otherwise go back to wake listening
            # (State might have changed during processing)
            self.state = VoiceState.LISTENING_WAKE
    
    def _speak(self, text: str):
        """Speak text using best available TTS."""
        if not text:
            return
        
        # Try XTTS first
        if self._tts_engine:
            try:
                if self._tts_engine.speak(text):
                    return
            except Exception as e:
                logger.debug(f"[VoicePipeline] XTTS failed: {e}")
        
        # Fallback to FreeNaturalVoice
        if self._voice:
            try:
                self._voice.speak(text)
            except Exception as e:
                logger.error(f"[VoicePipeline] TTS failed: {e}")
    
    def force_wakeup(self):
        """Programmatically activate continuous mode."""
        self._activate_continuous_mode()
    
    def force_sleep(self):
        """Programmatically deactivate continuous mode."""
        if self.state == VoiceState.CONTINUOUS:
            self._deactivate_continuous_mode()
        else:
            self.state = VoiceState.IDLE
    
    def is_listening(self) -> bool:
        """Check if pipeline is actively listening."""
        return self.state in (VoiceState.LISTENING_WAKE, VoiceState.CONTINUOUS)
    
    def is_continuous(self) -> bool:
        """Check if in continuous listening mode."""
        return self.state == VoiceState.CONTINUOUS


# Singleton instance
_pipeline: Optional[VoicePipeline] = None


def get_voice_pipeline(**kwargs) -> VoicePipeline:
    """Get or create the voice pipeline singleton."""
    global _pipeline
    if _pipeline is None:
        _pipeline = VoicePipeline(**kwargs)
    return _pipeline


def start_voice_pipeline(on_command: Callable[[str], str]) -> VoicePipeline:
    """Start the voice pipeline with a command handler.
    
    Args:
        on_command: Function that receives command text and returns response
        
    Returns:
        Running VoicePipeline instance
    """
    pipeline = get_voice_pipeline(on_command=on_command)
    pipeline.start()
    return pipeline
