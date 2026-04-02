"""
LADA API — Shared dependencies (server state holder).

All routers access shared state through the ServerState singleton.
"""

import os
import time
import logging
import secrets
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_STATE_KEY = "request_id"
_REQUEST_ID_ALLOWED_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:")


def normalize_request_id(raw_value: Optional[str], *, prefix: str = "req") -> str:
    """Normalize incoming request IDs and generate safe fallbacks when absent."""
    candidate = str(raw_value or "").strip()
    if candidate:
        sanitized = "".join(ch if ch in _REQUEST_ID_ALLOWED_CHARS else "-" for ch in candidate)[:96]
        sanitized = sanitized.strip("-_.:")
        if sanitized:
            return sanitized

    generated = uuid.uuid4().hex
    safe_prefix = "".join(ch for ch in str(prefix or "").lower() if ch.isalnum() or ch in {"-", "_"})
    return f"{safe_prefix}-{generated}" if safe_prefix else generated


def ensure_request_id(request: Any, *, prefix: str = "req") -> str:
    """Return a request correlation ID and persist it on request.state when available."""
    state = getattr(request, "state", None)
    if state is not None:
        existing = getattr(state, REQUEST_ID_STATE_KEY, "")
        if existing:
            return str(existing)

    headers = getattr(request, "headers", None)
    incoming = ""
    if headers is not None:
        incoming = headers.get(REQUEST_ID_HEADER, "") or headers.get("x-request-id", "")

    request_id = normalize_request_id(incoming, prefix=prefix)
    if state is not None:
        setattr(state, REQUEST_ID_STATE_KEY, request_id)
    return request_id


def set_request_id_header(request: Any, response: Any, *, prefix: str = "req") -> str:
    """Ensure request correlation ID exists and expose it via response headers."""
    request_id = ensure_request_id(request, prefix=prefix)
    headers = getattr(response, "headers", None)
    if headers is not None:
        headers[REQUEST_ID_HEADER] = request_id
    return request_id


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
        self.openclaw_adapter = None
        self._openclaw_adapter_enabled = os.getenv(
            "LADA_OPENCLAW_ADAPTER_ENABLED", "false"
        ).strip().lower() in {"1", "true", "yes", "on"}

        # Standalone orchestration (feature-gated)
        self.command_bus = None
        self.orchestrator = None
        self._standalone_orchestrator_enabled = os.getenv(
            "LADA_STANDALONE_ORCHESTRATOR", "false"
        ).strip().lower() in {"1", "true", "yes", "on"}

        # WebSocket state
        self.ws_connections: Dict[str, Any] = {}  # session_id -> websocket
        self.ws_sessions: Dict[str, Dict[str, Any]] = {}  # session_id -> session data
        self.ws_orchestrator_subscribers = set()
        self.ws_orchestrator_subscription_filters: Dict[str, Dict[str, Any]] = {}
        self.ws_orchestrator_bus_subscription_token: Optional[str] = None
        self.ws_orchestrator_event_loop = None
        self.ws_orchestrator_event_callback = None

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

        if self._openclaw_adapter_enabled and self.openclaw_adapter is None:
            self._init_openclaw_adapter()

        if self._standalone_orchestrator_enabled:
            self._init_standalone_orchestrator()

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

    def _init_standalone_orchestrator(self):
        """Initialize standalone command bus + orchestrator behind a feature flag."""

        if self.command_bus is None:
            try:
                from modules.standalone.command_bus import create_command_bus

                self.command_bus = create_command_bus()
                logger.info("[APIServer] Standalone command bus initialized")
            except Exception as e:
                logger.error(f"[APIServer] Failed to initialize command bus: {e}")
                self.command_bus = None
                return

        if self.orchestrator is None and self.command_bus is not None:
            try:
                from modules.standalone.orchestrator import create_orchestrator

                self.orchestrator = create_orchestrator(
                    command_bus=self.command_bus,
                    jarvis_getter=lambda: self.jarvis,
                    ai_router_getter=lambda: self.ai_router,
                    autostart=True,
                )
                logger.info("[APIServer] Standalone orchestrator initialized")
            except Exception as e:
                logger.error(f"[APIServer] Failed to initialize orchestrator: {e}")
                self.orchestrator = None

    def _init_openclaw_adapter(self):
        """Initialize OpenClaw adapter when compatibility mode is enabled."""
        try:
            from integrations.openclaw_adapter import get_openclaw_adapter

            self.openclaw_adapter = get_openclaw_adapter()
            if self.openclaw_adapter is not None:
                logger.info("[APIServer] OpenClaw adapter initialized")
            else:
                logger.info("[APIServer] OpenClaw adapter disabled by feature flag")
        except Exception as e:
            logger.warning(f"[APIServer] OpenClaw adapter initialization failed: {e}")
            self.openclaw_adapter = None
