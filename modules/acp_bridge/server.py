"""
LADA ACP Server

Agent Communication Protocol server for IDE integration.

Features:
- WebSocket-based ACP endpoint
- Session management
- Request routing
- Tool invocation
"""

import os
import uuid
import asyncio
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Callable, Awaitable, Set
from dataclasses import dataclass, field
from enum import Enum
import json

from modules.acp_bridge.protocol import (
    ACPRequest,
    ACPResponse,
    ACPNotification,
    ACPError,
    ACPErrorCode,
    ACPMethod,
    ACPContext,
    ACPToolDefinition,
    ACPChatMessage,
    ACPStreamChunk,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class ACPMessageType(str, Enum):
    """ACP message types."""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"


class SessionStatus(str, Enum):
    """ACP session status."""
    ACTIVE = "active"
    IDLE = "idle"
    PROCESSING = "processing"
    EXPIRED = "expired"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ACPMessage:
    """
    Wrapper for ACP messages.
    """
    type: ACPMessageType
    data: Dict[str, Any]
    session_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "data": self.data,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACPMessage":
        return cls(
            type=ACPMessageType(data.get("type", "request")),
            data=data.get("data", data),  # Support raw JSON-RPC too
            session_id=data.get("session_id"),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
        )


@dataclass
class ACPSession:
    """
    An ACP session with an IDE agent.
    """
    session_id: str
    
    # Client info
    client_name: str = ""
    client_version: str = ""
    
    # Context
    context: ACPContext = field(default_factory=ACPContext)
    
    # State
    status: SessionStatus = SessionStatus.ACTIVE
    chat_history: List[ACPChatMessage] = field(default_factory=list)
    
    # Tracking
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_activity: str = field(default_factory=lambda: datetime.now().isoformat())
    request_count: int = 0
    
    # Current processing
    current_request_id: Optional[str] = None
    
    # Session TTL
    ttl_seconds: int = 3600  # 1 hour default
    
    @property
    def is_expired(self) -> bool:
        """Check if session is expired."""
        last = datetime.fromisoformat(self.last_activity)
        return datetime.now() - last > timedelta(seconds=self.ttl_seconds)
    
    def touch(self):
        """Update last activity timestamp."""
        self.last_activity = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "client_name": self.client_name,
            "client_version": self.client_version,
            "context": self.context.to_dict(),
            "status": self.status.value,
            "chat_history": [m.to_dict() for m in self.chat_history],
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "request_count": self.request_count,
        }


# ============================================================================
# ACP Handler
# ============================================================================

# Type alias for request handlers
RequestHandler = Callable[[ACPSession, ACPRequest], Awaitable[ACPResponse]]


class ACPServer:
    """
    ACP server for handling IDE agent requests.
    
    Features:
    - Session management
    - Request routing
    - Tool registration
    - Streaming support
    """
    
    def __init__(
        self,
        session_ttl: int = 3600,
        max_sessions: int = 100,
        chat_handler: Optional[Callable[[ACPSession, str], Awaitable[str]]] = None,
    ):
        """
        Initialize ACP server.
        
        Args:
            session_ttl: Session TTL in seconds
            max_sessions: Maximum concurrent sessions
            chat_handler: Handler for chat completion requests
        """
        self._session_ttl = session_ttl
        self._max_sessions = max_sessions
        self._chat_handler = chat_handler or self._default_chat_handler
        
        self._sessions: Dict[str, ACPSession] = {}
        self._tools: Dict[str, ACPToolDefinition] = {}
        self._handlers: Dict[str, RequestHandler] = {}
        
        self._lock = threading.RLock()
        
        # Register built-in handlers
        self._register_builtin_handlers()
        
        logger.info(f"[ACPServer] Initialized: ttl={session_ttl}s, max={max_sessions}")
    
    def create_session(
        self,
        client_name: str = "",
        client_version: str = "",
        context: Optional[ACPContext] = None,
        *,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ACPSession:
        """Create a new ACP session."""
        with self._lock:
            # Check limit
            if len(self._sessions) >= self._max_sessions:
                # Cleanup expired sessions
                self._cleanup_expired()
                
                if len(self._sessions) >= self._max_sessions:
                    raise RuntimeError(f"Max sessions ({self._max_sessions}) reached")
            
            # Use provided session_id or generate one
            final_session_id = session_id or f"acp_{uuid.uuid4().hex[:12]}"
            
            session = ACPSession(
                session_id=final_session_id,
                client_name=client_name,
                client_version=client_version,
                context=context or ACPContext(),
                ttl_seconds=self._session_ttl,
            )
            
            # Store metadata if provided
            if metadata:
                session.metadata = metadata
            
            self._sessions[final_session_id] = session
            
            logger.info(f"[ACPServer] Created session {final_session_id}: {client_name}")
            return session
    
    def get_session(self, session_id: str) -> Optional[ACPSession]:
        """Get session by ID."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session and session.is_expired:
                session.status = SessionStatus.EXPIRED
            return session
    
    def destroy_session(self, session_id: str) -> bool:
        """Destroy a session."""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info(f"[ACPServer] Destroyed session {session_id}")
                return True
        return False
    
    def list_sessions(self) -> List[ACPSession]:
        """List all active sessions."""
        with self._lock:
            return [s for s in self._sessions.values() if not s.is_expired]
    
    async def handle_request(
        self,
        session_id: str,
        request: ACPRequest,
    ) -> ACPResponse:
        """
        Handle an ACP request.
        
        Args:
            session_id: Session ID
            request: ACP request (ACPRequest or dict)
        
        Returns:
            ACP response (ACPResponse object)
        """
        import time
        start_time = time.time()
        
        # Convert dict to ACPRequest if needed
        if isinstance(request, dict):
            try:
                request = ACPRequest(
                    id=request.get("id"),
                    method=request.get("method", ""),
                    params=request.get("params", {}),
                    trace_id=request.get("trace_id"),
                )
            except Exception as e:
                return ACPResponse.error_response(
                    request.get("id") if isinstance(request, dict) else None,
                    ACPErrorCode.INVALID_REQUEST,
                    f"Invalid request: {e}",
                )
        
        session = self.get_session(session_id)
        if not session:
            return ACPResponse.error_response(
                request.id,
                ACPErrorCode.SESSION_NOT_FOUND,
                f"Session {session_id} not found",
            )
        
        if session.is_expired:
            return ACPResponse.error_response(
                request.id,
                ACPErrorCode.SESSION_EXPIRED,
                f"Session {session_id} has expired",
            )
        
        # Update session
        session.touch()
        session.request_count += 1
        session.current_request_id = request.id
        session.status = SessionStatus.PROCESSING
        
        try:
            # Route to handler
            handler = self._handlers.get(request.method)
            if handler:
                response = await handler(session, request)
            else:
                response = ACPResponse.error_response(
                    request.id,
                    ACPErrorCode.METHOD_NOT_FOUND,
                    f"Method {request.method} not found",
                )
            
            duration_ms = int((time.time() - start_time) * 1000)
            response.duration_ms = duration_ms
            response.trace_id = request.trace_id
            
            return response
            
        except Exception as e:
            logger.error(f"[ACPServer] Error handling {request.method}: {e}")
            return ACPResponse.error_response(
                request.id,
                ACPErrorCode.INTERNAL_ERROR,
                str(e),
            )
            
        finally:
            session.current_request_id = None
            session.status = SessionStatus.ACTIVE
    
    def handle_notification(
        self,
        session_id: str,
        notification: ACPNotification,
    ) -> None:
        """Handle an ACP notification (no response)."""
        session = self.get_session(session_id)
        if not session:
            return
        
        session.touch()
        
        # Log notification
        logger.debug(f"[ACPServer] Notification: {notification.method}")
    
    def register_handler(
        self,
        method: str,
        handler: RequestHandler,
    ) -> None:
        """Register a request handler."""
        self._handlers[method] = handler
        logger.info(f"[ACPServer] Registered handler: {method}")
    
    def register_tool(self, tool: ACPToolDefinition) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
        logger.info(f"[ACPServer] Registered tool: {tool.name}")
    
    def get_tools(self) -> List[ACPToolDefinition]:
        """Get all registered tools."""
        return list(self._tools.values())
    
    def set_chat_handler(
        self,
        handler: Callable[[ACPSession, str], Awaitable[str]],
    ) -> None:
        """Set the chat completion handler."""
        self._chat_handler = handler
    
    def _register_builtin_handlers(self):
        """Register built-in request handlers."""
        self.register_handler(ACPMethod.SESSION_CREATE.value, self._handle_session_create)
        self.register_handler(ACPMethod.SESSION_DESTROY.value, self._handle_session_destroy)
        self.register_handler(ACPMethod.SESSION_STATUS.value, self._handle_session_status)
        self.register_handler(ACPMethod.CHAT_COMPLETE.value, self._handle_chat_complete)
        self.register_handler(ACPMethod.CONTEXT_SET.value, self._handle_context_set)
        self.register_handler(ACPMethod.CONTEXT_GET.value, self._handle_context_get)
        self.register_handler(ACPMethod.CONTEXT_CLEAR.value, self._handle_context_clear)
        self.register_handler(ACPMethod.TOOL_LIST.value, self._handle_tool_list)
        self.register_handler(ACPMethod.TOOL_INVOKE.value, self._handle_tool_invoke)
    
    async def _handle_session_create(
        self,
        session: ACPSession,
        request: ACPRequest,
    ) -> ACPResponse:
        """Handle session/create request."""
        # Session already exists (we have it)
        return ACPResponse.success_response(
            request.id,
            {
                "session_id": session.session_id,
                "status": "active",
            },
        )
    
    async def _handle_session_destroy(
        self,
        session: ACPSession,
        request: ACPRequest,
    ) -> ACPResponse:
        """Handle session/destroy request."""
        self.destroy_session(session.session_id)
        return ACPResponse.success_response(
            request.id,
            {"destroyed": True},
        )
    
    async def _handle_session_status(
        self,
        session: ACPSession,
        request: ACPRequest,
    ) -> ACPResponse:
        """Handle session/status request."""
        return ACPResponse.success_response(
            request.id,
            session.to_dict(),
        )
    
    async def _handle_chat_complete(
        self,
        session: ACPSession,
        request: ACPRequest,
    ) -> ACPResponse:
        """Handle chat/complete request."""
        messages = request.params.get("messages", [])
        
        # Parse messages
        chat_messages = [ACPChatMessage.from_dict(m) for m in messages]
        
        # Get user message
        user_message = ""
        for msg in reversed(chat_messages):
            if msg.role == "user":
                user_message = msg.content
                break
        
        if not user_message:
            return ACPResponse.error_response(
                request.id,
                ACPErrorCode.INVALID_PARAMS,
                "No user message found",
            )
        
        # Update session history
        session.chat_history.extend(chat_messages)
        
        # Get response from handler
        try:
            response_text = await self._chat_handler(session, user_message)
            
            # Add to history
            assistant_msg = ACPChatMessage(role="assistant", content=response_text)
            session.chat_history.append(assistant_msg)
            
            return ACPResponse.success_response(
                request.id,
                {
                    "message": assistant_msg.to_dict(),
                    "finish_reason": "stop",
                },
            )
            
        except Exception as e:
            return ACPResponse.error_response(
                request.id,
                ACPErrorCode.INTERNAL_ERROR,
                f"Chat handler error: {e}",
            )
    
    async def _handle_context_set(
        self,
        session: ACPSession,
        request: ACPRequest,
    ) -> ACPResponse:
        """Handle context/set request."""
        context_data = request.params.get("context", {})
        session.context = ACPContext.from_dict(context_data)
        
        return ACPResponse.success_response(
            request.id,
            {"updated": True},
        )
    
    async def _handle_context_get(
        self,
        session: ACPSession,
        request: ACPRequest,
    ) -> ACPResponse:
        """Handle context/get request."""
        return ACPResponse.success_response(
            request.id,
            session.context.to_dict(),
        )
    
    async def _handle_context_clear(
        self,
        session: ACPSession,
        request: ACPRequest,
    ) -> ACPResponse:
        """Handle context/clear request."""
        session.context = ACPContext()
        session.chat_history = []
        
        return ACPResponse.success_response(
            request.id,
            {"cleared": True},
        )
    
    async def _handle_tool_list(
        self,
        session: ACPSession,
        request: ACPRequest,
    ) -> ACPResponse:
        """Handle tool/list request."""
        tools = [t.to_dict() for t in self._tools.values()]
        
        return ACPResponse.success_response(
            request.id,
            {"tools": tools},
        )
    
    async def _handle_tool_invoke(
        self,
        session: ACPSession,
        request: ACPRequest,
    ) -> ACPResponse:
        """Handle tool/invoke request."""
        tool_name = request.params.get("name")
        tool_args = request.params.get("arguments", {})
        
        if not tool_name:
            return ACPResponse.error_response(
                request.id,
                ACPErrorCode.INVALID_PARAMS,
                "Tool name required",
            )
        
        if tool_name not in self._tools:
            return ACPResponse.error_response(
                request.id,
                ACPErrorCode.TOOL_NOT_AVAILABLE,
                f"Tool {tool_name} not available",
            )
        
        # Tool invocation would be implemented here
        # For now, return a placeholder
        return ACPResponse.success_response(
            request.id,
            {
                "tool_name": tool_name,
                "result": f"Tool {tool_name} invoked (placeholder)",
            },
        )
    
    async def _default_chat_handler(
        self,
        session: ACPSession,
        message: str,
    ) -> str:
        """Default chat handler (placeholder)."""
        return f"Echo: {message}"
    
    def _cleanup_expired(self):
        """Remove expired sessions."""
        with self._lock:
            expired = [
                sid for sid, session in self._sessions.items()
                if session.is_expired
            ]
            
            for sid in expired:
                del self._sessions[sid]
            
            if expired:
                logger.info(f"[ACPServer] Cleaned up {len(expired)} expired sessions")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get server statistics."""
        with self._lock:
            active = len([s for s in self._sessions.values() if not s.is_expired])
            
            return {
                "total_sessions": len(self._sessions),
                "active_sessions": active,
                "registered_tools": len(self._tools),
                "registered_handlers": len(self._handlers),
            }
    
    # ─── API Helper Methods ─────────────────────────────────────────────
    
    def close_session(self, session_id: str) -> bool:
        """Alias for destroy_session for API compatibility."""
        return self.destroy_session(session_id)


# ============================================================================
# Singleton
# ============================================================================

_server_instance: Optional[ACPServer] = None
_server_lock = threading.Lock()


def get_acp_server() -> ACPServer:
    """Get singleton ACPServer instance."""
    global _server_instance
    if _server_instance is None:
        with _server_lock:
            if _server_instance is None:
                _server_instance = ACPServer(
                    session_ttl=int(os.getenv("LADA_ACP_SESSION_TTL", "3600")),
                    max_sessions=int(os.getenv("LADA_ACP_MAX_SESSIONS", "100")),
                )
    return _server_instance
