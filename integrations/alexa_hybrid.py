"""Alexa Hybrid Voice Switcher

Automatically switches between Echo Dot and local voice based on connectivity.

Features:
- Health check every 10 seconds
- Echo Dot online → use Alexa mode (Echo Dot mic + speaker)
- Echo Dot offline → auto-switch to local mode (PC mic + XTTS-v2)
- Seamless mode switching with zero interruption
- Mode switch logging

Environment variables:
- ECHO_DOT_IP: IP address of Echo Dot (for health checks)
- ECHO_DOT_PORT: Port for Echo Dot (default: 5001, the Alexa server port)
- ALEXA_HEALTH_INTERVAL: Health check interval in seconds (default: 10)
- LADA_VOICE_MODE: Force mode (auto, alexa, local)

Usage:
    from integrations.alexa_hybrid import AlexaHybridVoice
    
    hybrid = AlexaHybridVoice()
    hybrid.start()
    
    # Speak - automatically uses best available method
    hybrid.speak("Hello world")
"""

from __future__ import annotations

import os
import time
import logging
import threading
import socket
from typing import Optional, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class VoiceMode(Enum):
    """Voice output mode."""
    AUTO = "auto"       # Automatically select based on availability
    ALEXA = "alexa"     # Use Echo Dot (via Alexa skill)
    LOCAL = "local"     # Use local TTS (XTTS-v2 / Kokoro / pyttsx3)


@dataclass
class HybridConfig:
    """Configuration for hybrid voice switching."""
    echo_dot_ip: str = ""           # Echo Dot IP for health checks
    echo_dot_port: int = 5001       # Alexa server port
    health_interval: float = 10.0   # Seconds between health checks
    force_mode: VoiceMode = VoiceMode.AUTO
    connection_timeout: float = 2.0  # Seconds for connection test
    
    @classmethod
    def from_env(cls) -> "HybridConfig":
        """Load config from environment."""
        mode_str = os.getenv("LADA_VOICE_MODE", "auto").lower()
        mode = VoiceMode.LOCAL  # Default fallback
        for m in VoiceMode:
            if m.value == mode_str:
                mode = m
                break
        
        return cls(
            echo_dot_ip=os.getenv("ECHO_DOT_IP", ""),
            echo_dot_port=int(os.getenv("ECHO_DOT_PORT", "5001")),
            health_interval=float(os.getenv("ALEXA_HEALTH_INTERVAL", "10")),
            force_mode=mode,
            connection_timeout=float(os.getenv("ALEXA_TIMEOUT", "2.0")),
        )


class AlexaHybridVoice:
    """Hybrid voice system that switches between Alexa and local TTS.
    
    Automatically detects Echo Dot availability and switches modes seamlessly.
    """
    
    def __init__(self, config: Optional[HybridConfig] = None):
        """Initialize hybrid voice system.
        
        Args:
            config: Configuration (default: from environment)
        """
        self.config = config or HybridConfig.from_env()
        
        self._current_mode = VoiceMode.LOCAL
        self._alexa_available = False
        self._running = False
        self._health_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # Mode change callbacks
        self._on_mode_change: Optional[Callable[[VoiceMode], None]] = None
        
        # Voice components (lazy loaded)
        self._local_voice = None
        self._alexa_client = None
        
        logger.info(f"[AlexaHybrid] Initialized: force_mode={self.config.force_mode.value}")
    
    @property
    def current_mode(self) -> VoiceMode:
        """Get current active voice mode."""
        return self._current_mode
    
    @property
    def is_alexa_available(self) -> bool:
        """Check if Alexa/Echo Dot is available."""
        return self._alexa_available
    
    def set_mode_change_callback(self, callback: Callable[[VoiceMode], None]):
        """Set callback for mode changes.
        
        Args:
            callback: Function called with new mode when mode changes
        """
        self._on_mode_change = callback
    
    def _init_local_voice(self):
        """Initialize local voice components."""
        if self._local_voice is not None:
            return
        
        try:
            # Try XTTS first
            from voice.xtts_engine import FallbackTTSEngine
            self._local_voice = FallbackTTSEngine()
            logger.info("[AlexaHybrid] Local voice: FallbackTTSEngine (XTTS)")
        except ImportError:
            try:
                # Fall back to FreeNaturalVoice
                from voice_tamil_free import FreeNaturalVoice
                self._local_voice = FreeNaturalVoice()
                logger.info("[AlexaHybrid] Local voice: FreeNaturalVoice")
            except ImportError:
                logger.warning("[AlexaHybrid] No local voice available")
    
    def _check_alexa_health(self) -> bool:
        """Check if Alexa server/Echo Dot is available.
        
        Returns:
            True if Alexa is reachable
        """
        if not self.config.echo_dot_ip:
            # No Echo Dot configured, check local Alexa server
            try:
                import requests
                url = f"http://localhost:{self.config.echo_dot_port}/health"
                response = requests.get(url, timeout=self.config.connection_timeout)
                return response.ok
            except Exception:
                return False
        
        # Check Echo Dot connectivity
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.config.connection_timeout)
            result = sock.connect_ex((self.config.echo_dot_ip, self.config.echo_dot_port))
            sock.close()
            return result == 0
        except Exception as e:
            logger.debug(f"[AlexaHybrid] Health check failed: {e}")
            return False
    
    def _update_mode(self, alexa_available: bool):
        """Update current mode based on availability."""
        with self._lock:
            old_available = self._alexa_available
            self._alexa_available = alexa_available
            
            # Determine new mode
            if self.config.force_mode != VoiceMode.AUTO:
                new_mode = self.config.force_mode
            elif alexa_available:
                new_mode = VoiceMode.ALEXA
            else:
                new_mode = VoiceMode.LOCAL
            
            # Check if mode changed
            if new_mode != self._current_mode or alexa_available != old_available:
                old_mode = self._current_mode
                self._current_mode = new_mode
                
                logger.info(
                    f"[AlexaHybrid] Mode switch: {old_mode.value} → {new_mode.value} "
                    f"(alexa_available={alexa_available})"
                )
                
                if self._on_mode_change:
                    try:
                        self._on_mode_change(new_mode)
                    except Exception as e:
                        logger.error(f"[AlexaHybrid] Mode change callback error: {e}")
    
    def _health_loop(self):
        """Background health check loop."""
        while self._running:
            try:
                available = self._check_alexa_health()
                self._update_mode(available)
            except Exception as e:
                logger.error(f"[AlexaHybrid] Health loop error: {e}")
            
            time.sleep(self.config.health_interval)
    
    def start(self):
        """Start the hybrid voice system with health monitoring."""
        if self._running:
            logger.warning("[AlexaHybrid] Already running")
            return
        
        self._running = True
        self._init_local_voice()
        
        # Initial health check
        self._update_mode(self._check_alexa_health())
        
        # Start health monitoring thread
        self._health_thread = threading.Thread(target=self._health_loop, daemon=True)
        self._health_thread.start()
        
        logger.info(f"[AlexaHybrid] Started: current_mode={self._current_mode.value}")
    
    def stop(self):
        """Stop the hybrid voice system."""
        self._running = False
        if self._health_thread:
            self._health_thread.join(timeout=2.0)
        logger.info("[AlexaHybrid] Stopped")
    
    def speak(self, text: str, language: str = "en", blocking: bool = True) -> bool:
        """Speak text using current mode.
        
        Automatically uses Alexa or local voice based on availability.
        
        Args:
            text: Text to speak
            language: Language code
            blocking: Wait for speech to complete
            
        Returns:
            True if speech was successful
        """
        if not text or not text.strip():
            return False
        
        mode = self._current_mode
        
        if mode == VoiceMode.ALEXA:
            result = self._speak_alexa(text)
            if result:
                return True
            # Fallback to local on Alexa failure
            logger.warning("[AlexaHybrid] Alexa speak failed, falling back to local")
            mode = VoiceMode.LOCAL
        
        if mode == VoiceMode.LOCAL:
            return self._speak_local(text, language, blocking)
        
        return False
    
    def _speak_alexa(self, text: str) -> bool:
        """Speak via Alexa (send to Echo Dot).
        
        This sends a notification/announcement to Echo Dot.
        Note: Requires Alexa Notifications API or similar.
        """
        try:
            import requests
            
            # Send to local Alexa server which can forward to Echo Dot
            url = f"http://localhost:{self.config.echo_dot_port}/speak"
            response = requests.post(
                url,
                json={"text": text},
                timeout=10
            )
            return response.ok
            
        except Exception as e:
            logger.debug(f"[AlexaHybrid] Alexa speak error: {e}")
            return False
    
    def _speak_local(self, text: str, language: str = "en", blocking: bool = True) -> bool:
        """Speak using local TTS."""
        if self._local_voice is None:
            self._init_local_voice()
        
        if self._local_voice is None:
            logger.error("[AlexaHybrid] No local voice available")
            return False
        
        try:
            # Handle different voice engine interfaces
            if hasattr(self._local_voice, 'speak'):
                return self._local_voice.speak(text, language, blocking)
            else:
                logger.warning("[AlexaHybrid] Unknown voice interface")
                return False
        except Exception as e:
            logger.error(f"[AlexaHybrid] Local speak error: {e}")
            return False
    
    def listen(self, language: str = "auto") -> Optional[str]:
        """Listen for voice input using current mode.
        
        In Alexa mode, listening is handled by Echo Dot itself.
        In local mode, uses local microphone.
        
        Args:
            language: Language code for recognition
            
        Returns:
            Recognized text or None
        """
        # In Alexa mode, we don't need to listen locally
        # The Alexa skill receives voice input directly
        if self._current_mode == VoiceMode.ALEXA:
            logger.debug("[AlexaHybrid] In Alexa mode, listening via Echo Dot")
            return None
        
        # Local mode - use local voice
        if self._local_voice and hasattr(self._local_voice, 'listen'):
            try:
                return self._local_voice.listen(language)
            except Exception as e:
                logger.error(f"[AlexaHybrid] Local listen error: {e}")
                return None
        
        return None
    
    def force_mode(self, mode: VoiceMode):
        """Force a specific voice mode.
        
        Args:
            mode: Mode to force (ALEXA, LOCAL, or AUTO to reset)
        """
        self.config.force_mode = mode
        
        if mode == VoiceMode.AUTO:
            # Re-check availability
            self._update_mode(self._check_alexa_health())
        else:
            self._current_mode = mode
            logger.info(f"[AlexaHybrid] Forced mode: {mode.value}")
    
    def get_status(self) -> dict:
        """Get current status of hybrid voice system."""
        return {
            "running": self._running,
            "current_mode": self._current_mode.value,
            "force_mode": self.config.force_mode.value,
            "alexa_available": self._alexa_available,
            "echo_dot_ip": self.config.echo_dot_ip,
            "health_interval": self.config.health_interval,
            "local_voice_available": self._local_voice is not None,
        }


# Singleton instance
_hybrid_voice: Optional[AlexaHybridVoice] = None


def get_hybrid_voice(**kwargs) -> AlexaHybridVoice:
    """Get or create the hybrid voice singleton."""
    global _hybrid_voice
    if _hybrid_voice is None:
        _hybrid_voice = AlexaHybridVoice(**kwargs)
    return _hybrid_voice


def speak(text: str, language: str = "en", blocking: bool = True) -> bool:
    """Speak using hybrid voice system."""
    hybrid = get_hybrid_voice()
    if not hybrid._running:
        hybrid.start()
    return hybrid.speak(text, language, blocking)
