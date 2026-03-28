"""
LADA API — Shared dependencies (server state holder).

All routers access shared state through the ServerState singleton.
"""

import os
import time
import logging
import secrets
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ServerState:
    """
    Holds shared server state that routers need.
    Created once by LADAAPIServer and referenced by all routers.
    """

    def __init__(self):
        self.start_time = datetime.now()

        # Session auth - NO DEFAULT PASSWORD for security
        self._auth_password = os.getenv("LADA_WEB_PASSWORD")
        if not self._auth_password:
            # Generate secure random password on first startup
            self._auth_password = secrets.token_urlsafe(24)
            logger.warning(
                f"[ServerState] No LADA_WEB_PASSWORD set. Generated random password: {self._auth_password}"
            )
            logger.warning("[ServerState] Set LADA_WEB_PASSWORD environment variable to use custom password")
        
        self._session_tokens: Dict[str, float] = {}  # token -> expiry timestamp
        self._session_ttl = int(os.getenv("LADA_SESSION_TTL", "86400"))

        # Lazy-loaded components
        self.ai_router = None
        self.chat_manager = None
        self.jarvis = None
        self.voice_processor = None
        self.agents: Dict[str, Any] = {}

        # WebSocket state
        self.ws_connections: Dict[str, Any] = {}  # session_id -> websocket
        self.ws_sessions: Dict[str, Dict[str, Any]] = {}  # session_id -> session data

    # ── Session Auth ─────────────────────────────────────────

    def create_session_token(self) -> str:
        """Create a new session token with TTL."""
        token = secrets.token_hex(32)
        self._session_tokens[token] = time.time() + self._session_ttl
        now = time.time()
        self._session_tokens = {t: exp for t, exp in self._session_tokens.items() if exp > now}
        return token

    def validate_session_token(self, token: str) -> bool:
        """Check if a session token is valid and not expired."""
        if not token:
            return False
        expiry = self._session_tokens.get(token)
        if expiry is None:
            return False
        if time.time() > expiry:
            del self._session_tokens[token]
            return False
        return True

    def invalidate_token(self, token: str):
        self._session_tokens.pop(token, None)

    # ── Component Loading ────────────────────────────────────

    def load_components(self):
        """Lazy load LADA components."""
        if self.ai_router is None:
            try:
                from lada_ai_router import HybridAIRouter
                self.ai_router = HybridAIRouter()
            except Exception as e:
                logger.error(f"[APIServer] Failed to load AIRouter: {e}")

        if self.chat_manager is None:
            try:
                from modules.chat_manager import ChatManager
                self.chat_manager = ChatManager()
            except Exception as e:
                logger.error(f"[APIServer] Failed to load ChatManager: {e}")

        if self.jarvis is None:
            try:
                from lada_jarvis_core import JarvisCommandProcessor
                self.jarvis = JarvisCommandProcessor()
                logger.info("[APIServer] Loaded JarvisCommandProcessor")
            except Exception as e:
                logger.error(f"[APIServer] Failed to load Jarvis: {e}")

        if self.voice_processor is None:
            try:
                from modules.voice_nlu import VoiceCommandProcessor
                self.voice_processor = VoiceCommandProcessor()
                logger.info("[APIServer] Loaded VoiceCommandProcessor")
            except Exception as e:
                logger.error(f"[APIServer] Failed to load VoiceCommandProcessor: {e}")

        if not self.agents:
            self._load_agents()

    def _load_agents(self):
        """Load available agents."""
        agent_map = {
            'flight': ('modules.agents.flight_agent', 'FlightAgent'),
            'hotel': ('modules.agents.hotel_agent', 'HotelAgent'),
            'restaurant': ('modules.agents.restaurant_agent', 'RestaurantAgent'),
            'email': ('modules.agents.email_agent', 'EmailAgent'),
            'calendar': ('modules.agents.calendar_agent', 'CalendarAgent'),
            'product': ('modules.agents.product_agent', 'ProductAgent'),
        }

        for agent_name, (module_path, class_name) in agent_map.items():
            try:
                module = __import__(module_path, fromlist=[class_name])
                agent_class = getattr(module, class_name)
                self.agents[agent_name] = agent_class()
                logger.info(f"[APIServer] Loaded agent: {agent_name}")
            except Exception as e:
                logger.warning(f"[APIServer] Failed to load {agent_name}: {e}")
