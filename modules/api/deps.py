"""
LADA API — Shared dependencies (server state holder).

All routers access shared state through the ServerState singleton.
"""

import os
import time
import logging
import secrets
import uuid
import json
import base64
import hmac
import hashlib
import inspect
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_STATE_KEY = "request_id"
_REQUEST_ID_ALLOWED_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:")
_JWT_B64_PAD = "="


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


def _jwt_b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _jwt_b64url_decode(text: str) -> bytes:
    if not isinstance(text, str) or not text:
        raise ValueError("invalid base64url payload")
    padding = _JWT_B64_PAD * ((4 - len(text) % 4) % 4)
    try:
        return base64.urlsafe_b64decode((text + padding).encode("ascii"))
    except Exception as exc:
        raise ValueError("invalid base64url payload") from exc


def _parse_positive_int_env(name: str, default: int) -> int:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


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
        self._session_ttl = _parse_positive_int_env("LADA_SESSION_TTL", 86400)
        self._session_jwt_enabled = os.getenv("LADA_SESSION_JWT_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
        self._jwt_issuer = os.getenv("LADA_JWT_ISSUER", "lada-api")
        self._jwt_secret = os.getenv("LADA_JWT_SECRET")
        if not self._jwt_secret:
            self._jwt_secret = secrets.token_urlsafe(48)
            logger.warning("[ServerState] No LADA_JWT_SECRET set. Generated ephemeral JWT signing key.")

        # Lazy-loaded components
        self.ai_router = None
        self.chat_manager = None
        self.jarvis = None
        self.voice_processor = None
        self.agents: Dict[str, Any] = {}
        self.lada_browser_adapter = None
        self._lada_browser_adapter_enabled = os.getenv(
            "LADA_BROWSER_ADAPTER_ENABLED", "false"
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

    def _is_jwt_token(self, token: str) -> bool:
        return isinstance(token, str) and token.count(".") == 2

    def _encode_session_jwt(self, claims: Dict[str, Any]) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        header_part = _jwt_b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        payload_part = _jwt_b64url_encode(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        signing_input = f"{header_part}.{payload_part}".encode("ascii")
        signature = hmac.new(self._jwt_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        signature_part = _jwt_b64url_encode(signature)
        return f"{header_part}.{payload_part}.{signature_part}"

    def _decode_and_verify_session_jwt(self, token: str) -> Dict[str, Any]:
        if not self._is_jwt_token(token):
            raise ValueError("not a JWT token")
        header_part, payload_part, signature_part = token.split(".", 2)
        signing_input = f"{header_part}.{payload_part}".encode("ascii")
        expected_sig = hmac.new(self._jwt_secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        actual_sig = _jwt_b64url_decode(signature_part)
        if not hmac.compare_digest(actual_sig, expected_sig):
            raise ValueError("invalid JWT signature")
        payload_raw = _jwt_b64url_decode(payload_part)
        try:
            payload = json.loads(payload_raw.decode("utf-8"))
        except Exception as exc:
            raise ValueError("invalid JWT payload") from exc
        if not isinstance(payload, dict):
            raise ValueError("invalid JWT payload")
        return payload

    def create_session_token(self) -> str:
        """Create a new session token with TTL."""
        now = time.time()
        expiry = now + self._session_ttl
        token_key = secrets.token_hex(16)
        self._session_tokens[token_key] = expiry
        token = token_key
        if self._session_jwt_enabled:
            token = self._encode_session_jwt(
                {
                    "sub": "session",
                    "jti": token_key,
                    "iss": self._jwt_issuer,
                    "iat": int(now),
                    "exp": int(expiry),
                }
            )
        now = time.time()
        self._session_tokens = {t: exp for t, exp in self._session_tokens.items() if exp > now}
        return token

    def validate_session_token(self, token: str) -> bool:
        """Check if a session token is valid and not expired."""
        if not token:
            return False
        if self._is_jwt_token(token):
            try:
                payload = self._decode_and_verify_session_jwt(token)
            except ValueError:
                return False
            jti = str(payload.get("jti", "")).strip()
            token_expiry = self._session_tokens.get(jti)
            if not jti or token_expiry is None:
                return False
            if payload.get("iss") != self._jwt_issuer:
                return False
            exp_claim = payload.get("exp")
            if not isinstance(exp_claim, int):
                return False
            now = time.time()
            if now > exp_claim or now > token_expiry:
                self._session_tokens.pop(jti, None)
                return False
            return True
        expiry = self._session_tokens.get(token)
        if expiry is None:
            return False
        if time.time() > expiry:
            del self._session_tokens[token]
            return False
        return True

    def invalidate_token(self, token: str):
        if self._is_jwt_token(token):
            try:
                payload = self._decode_and_verify_session_jwt(token)
                jti = str(payload.get("jti", "")).strip()
                if jti:
                    self._session_tokens.pop(jti, None)
            except ValueError:
                pass
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

        if self._lada_browser_adapter_enabled and self.lada_browser_adapter is None:
            self._init_lada_browser_adapter()

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
                # Some agents require ai_router in constructor while others use zero-arg init.
                init_sig = inspect.signature(agent_class.__init__)
                init_params = list(init_sig.parameters.values())[1:]  # skip self
                ai_router_param = next((param for param in init_params if param.name == "ai_router"), None)
                accepts_var_kwargs = any(
                    param.kind == inspect.Parameter.VAR_KEYWORD for param in init_params
                )
                if ai_router_param is not None:
                    if ai_router_param.kind == inspect.Parameter.POSITIONAL_ONLY:
                        self.agents[agent_name] = agent_class(self.ai_router)
                    else:
                        self.agents[agent_name] = agent_class(ai_router=self.ai_router)
                elif accepts_var_kwargs:
                    self.agents[agent_name] = agent_class(ai_router=self.ai_router)
                else:
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

    def _init_lada_browser_adapter(self):
        """Initialize LADA browser adapter when compatibility mode is enabled."""
        try:
            from integrations.lada_browser_adapter import get_lada_browser_adapter

            self.lada_browser_adapter = get_lada_browser_adapter()
            if self.lada_browser_adapter is not None:
                logger.info("[APIServer] LADA browser adapter initialized")
            else:
                logger.info("[APIServer] LADA browser adapter disabled by feature flag")
        except Exception as e:
            logger.warning(f"[APIServer] LADA browser adapter initialization failed: {e}")
            self.lada_browser_adapter = None
