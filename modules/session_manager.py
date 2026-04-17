"""
LADA Session Manager - Per-conversation context isolation

Each conversation (GUI chat, voice session, messaging channel) gets
its own isolated session with:
- Conversation history
- Context window tracking
- Token budget
- Session-specific state (attached files, preferences)

Built around per-channel session isolation.
"""

import os
import json
import logging
import threading
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class SessionType(Enum):
    """Types of conversation sessions"""
    GUI_CHAT = "gui_chat"
    VOICE = "voice"
    CLI = "cli"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    WHATSAPP = "whatsapp"
    API = "api"


@dataclass
class SessionMessage:
    """Single message in a session"""
    role: str  # 'user', 'assistant', 'system'
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    token_count: int = 0


@dataclass
class Session:
    """
    Isolated conversation session.
    Each session has its own history, context, and state.
    Sessions are namespaced by agent_id for multi-agent isolation.
    """
    session_id: str
    session_type: SessionType
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    messages: List[SessionMessage] = field(default_factory=list)
    total_tokens: int = 0
    max_context_tokens: int = 8192  # Updated per model
    metadata: Dict[str, Any] = field(default_factory=dict)
    active: bool = True
    agent_id: str = "default"  # Agent namespace for isolation

    def add_message(self, role: str, content: str, token_count: int = 0,
                    metadata: Optional[Dict] = None) -> SessionMessage:
        """Add a message to this session"""
        msg = SessionMessage(
            role=role,
            content=content,
            token_count=token_count,
            metadata=metadata or {},
        )
        self.messages.append(msg)
        self.total_tokens += token_count
        return msg

    def get_context(self, max_tokens: Optional[int] = None) -> List[Dict[str, str]]:
        """
        Get conversation context as message list.
        Trims oldest messages if over token budget.
        """
        limit = max_tokens or self.max_context_tokens
        messages = []
        running_tokens = 0

        # Walk backwards from newest, collecting messages that fit
        for msg in reversed(self.messages):
            if running_tokens + msg.token_count > limit:
                break
            messages.insert(0, {
                'role': msg.role,
                'content': msg.content,
            })
            running_tokens += msg.token_count

        return messages

    def get_last_n(self, n: int = 10) -> List[Dict[str, str]]:
        """Get last N messages"""
        return [
            {'role': m.role, 'content': m.content}
            for m in self.messages[-n:]
        ]

    def clear(self) -> None:
        """Clear all messages"""
        self.messages.clear()
        self.total_tokens = 0

    def message_count(self) -> int:
        """Get number of messages"""
        return len(self.messages)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize session to dict"""
        return {
            'session_id': self.session_id,
            'session_type': self.session_type.value,
            'created_at': self.created_at,
            'message_count': len(self.messages),
            'total_tokens': self.total_tokens,
            'active': self.active,
            'agent_id': self.agent_id,
            'metadata': self.metadata,
            'messages': [
                {
                    'role': m.role,
                    'content': m.content,
                    'timestamp': m.timestamp,
                    'token_count': m.token_count,
                }
                for m in self.messages
            ],
        }


class SessionManager:
    """
    Manages multiple isolated conversation sessions.

    Features:
    - Create/retrieve/close sessions
    - Auto-assign session IDs
    - Persist sessions to disk (JSONL per session)
    - Session discovery and listing
    - Inter-session message forwarding (for multi-agent)
    """

    def __init__(self, data_dir: str = None):
        self.data_dir = Path(data_dir or os.getenv('DATA_DIR', './data')) / 'sessions'
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()
        self._counter = 0

        logger.info(f"[SessionManager] Initialized (dir: {self.data_dir})")

    def create_session(self, session_type: SessionType = SessionType.GUI_CHAT,
                       session_id: str = None,
                       max_context_tokens: int = 8192,
                       metadata: Optional[Dict] = None,
                       agent_id: str = "default") -> Session:
        """Create a new conversation session, namespaced by agent_id"""
        with self._lock:
            if not session_id:
                self._counter += 1
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                # Include agent_id in session_id for namespacing
                session_id = f"{agent_id}_{session_type.value}_{ts}_{self._counter}"

            session = Session(
                session_id=session_id,
                session_type=session_type,
                max_context_tokens=max_context_tokens,
                metadata=metadata or {},
                agent_id=agent_id,
            )
            self.sessions[session_id] = session

        logger.info(f"[SessionManager] Created session: {session_id} (agent={agent_id}, type={session_type.value})")
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID"""
        return self.sessions.get(session_id)

    def get_or_create(self, session_id: str,
                      session_type: SessionType = SessionType.GUI_CHAT,
                      max_context_tokens: int = 8192,
                      agent_id: str = "default") -> Session:
        """Get existing session or create new one (namespaced by agent_id)"""
        session = self.sessions.get(session_id)
        if session:
            return session
        return self.create_session(
            session_type=session_type,
            session_id=session_id,
            max_context_tokens=max_context_tokens,
            agent_id=agent_id,
        )

    def close_session(self, session_id: str) -> bool:
        """Close a session (marks inactive, persists to disk)"""
        session = self.sessions.get(session_id)
        if not session:
            return False

        session.active = False
        self.save_session(session_id)
        logger.info(f"[SessionManager] Closed session: {session_id}")
        return True

    def list_sessions(self, session_type: Optional[SessionType] = None,
                      active_only: bool = True) -> List[Session]:
        """List all sessions, optionally filtered"""
        results = []
        for s in self.sessions.values():
            if active_only and not s.active:
                continue
            if session_type and s.session_type != session_type:
                continue
            results.append(s)
        return results

    def list_sessions_for_agent(self, agent_id: str, active_only: bool = True) -> List[Session]:
        """List sessions belonging to a specific agent"""
        results = []
        for s in self.sessions.values():
            if s.agent_id != agent_id:
                continue
            if active_only and not s.active:
                continue
            results.append(s)
        return results

    def save_session(self, session_id: str) -> bool:
        """Save a session to disk"""
        session = self.sessions.get(session_id)
        if not session:
            return False

        filepath = self.data_dir / f"{session_id}.json"
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"[SessionManager] Failed to save session {session_id}: {e}")
            return False

    def save_all(self) -> int:
        """Save all active sessions. Returns count saved."""
        saved = 0
        for sid in list(self.sessions.keys()):
            if self.save_session(sid):
                saved += 1
        return saved

    def load_session(self, session_id: str) -> Optional[Session]:
        """Load a session from disk"""
        filepath = self.data_dir / f"{session_id}.json"
        if not filepath.exists():
            return None

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            session = Session(
                session_id=data['session_id'],
                session_type=SessionType(data['session_type']),
                created_at=data.get('created_at', ''),
                total_tokens=data.get('total_tokens', 0),
                active=data.get('active', True),
                metadata=data.get('metadata', {}),
                agent_id=data.get('agent_id', 'default'),
            )

            for m in data.get('messages', []):
                session.messages.append(SessionMessage(
                    role=m['role'],
                    content=m['content'],
                    timestamp=m.get('timestamp', ''),
                    token_count=m.get('token_count', 0),
                ))

            self.sessions[session_id] = session
            return session

        except Exception as e:
            logger.error(f"[SessionManager] Failed to load session {session_id}: {e}")
            return None

    def send_to_session(self, from_session: str, to_session: str, content: str) -> bool:
        """
        Forward a message from one session to another.
        For multi-agent inter-session communication.
        """
        target = self.sessions.get(to_session)
        if not target or not target.active:
            return False

        target.add_message(
            role='system',
            content=f"[From session {from_session}]: {content}",
            metadata={'forwarded_from': from_session},
        )
        return True

    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics"""
        active = sum(1 for s in self.sessions.values() if s.active)
        total_messages = sum(s.message_count() for s in self.sessions.values())
        total_tokens = sum(s.total_tokens for s in self.sessions.values())

        by_type = {}
        for s in self.sessions.values():
            t = s.session_type.value
            by_type[t] = by_type.get(t, 0) + 1

        return {
            'total_sessions': len(self.sessions),
            'active_sessions': active,
            'total_messages': total_messages,
            'total_tokens': total_tokens,
            'sessions_by_type': by_type,
        }


# Module-level singleton
_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get or create the global session manager"""
    global _manager
    if _manager is None:
        _manager = SessionManager()
    return _manager
