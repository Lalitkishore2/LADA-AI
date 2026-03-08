"""
LADA - Base Messaging Connector
Abstract base class for all platform connectors.
Includes DM pairing: unknown senders can be approved via a 6-digit code
sent to the admin (ADMIN_TELEGRAM_CHAT_ID) before their messages are routed.
"""

import os
import json
import random
import logging
import asyncio
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# DM pairing policy: "allow" (default), "deny", or "pair"
DM_PAIRING_POLICY = os.getenv('DM_PAIRING_POLICY', 'allow').lower()
# JSON file storing approved senders per platform
APPROVED_SENDERS_FILE = Path(os.getenv('APPROVED_SENDERS_FILE', 'data/approved_senders.json'))
# Admin chat ID to receive pairing codes (e.g. Telegram chat ID)
ADMIN_CHAT_ID = os.getenv('ADMIN_TELEGRAM_CHAT_ID', '')


@dataclass
class IncomingMessage:
    """Standardized incoming message from any platform."""
    platform: str
    user_id: str
    username: str
    text: str
    chat_id: str
    message_id: str = ""
    reply_to: str = ""
    attachments: list = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class OutgoingMessage:
    """Standardized outgoing message to any platform."""
    text: str
    chat_id: str
    reply_to: str = ""
    parse_mode: str = "markdown"
    attachments: list = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# Type alias for message handler callback
MessageHandler = Callable[[IncomingMessage], Awaitable[Optional[str]]]


class BaseConnector(ABC):
    """
    Abstract base class for messaging platform connectors.

    Each connector must implement:
    - start(): Begin listening for messages
    - stop(): Gracefully shut down
    - send_message(): Send a message to a chat
    - platform property: Return platform name

    DM pairing:
    - Policy "allow" (default): all senders allowed
    - Policy "deny": only approved senders allowed (pre-loaded from JSON)
    - Policy "pair": unknown senders receive a 6-digit code; admin must
      confirm before messages are routed
    """

    def __init__(self):
        self._message_handler: Optional[MessageHandler] = None
        self._running = False
        # {platform: {user_id: True}} — loaded once, updated on approval
        self._approved: Dict[str, bool] = {}
        # {user_id: code} — pending pairing codes
        self._pending_codes: Dict[str, str] = {}
        self._load_approved_senders()

    # ------------------------------------------------------------------ #
    #  Abstract interface
    # ------------------------------------------------------------------ #

    @property
    @abstractmethod
    def platform(self) -> str:
        """Return the platform name (e.g., 'telegram', 'discord')."""
        ...

    @abstractmethod
    async def start(self):
        """Start the connector and begin listening for messages."""
        ...

    @abstractmethod
    async def stop(self):
        """Stop the connector gracefully."""
        ...

    @abstractmethod
    async def send_message(self, message: OutgoingMessage) -> bool:
        """Send a message to the specified chat. Returns True on success."""
        ...

    # ------------------------------------------------------------------ #
    #  Router registration
    # ------------------------------------------------------------------ #

    def set_message_handler(self, handler: MessageHandler):
        """Set the callback for incoming messages."""
        self._message_handler = handler

    # ------------------------------------------------------------------ #
    #  DM pairing helpers
    # ------------------------------------------------------------------ #

    def _load_approved_senders(self):
        """Load approved senders from JSON file into self._approved."""
        try:
            if APPROVED_SENDERS_FILE.exists():
                data = json.loads(APPROVED_SENDERS_FILE.read_text(encoding='utf-8'))
                platform_data = data.get(self.platform, {})
                self._approved = {uid: True for uid in platform_data}
        except Exception as e:
            logger.warning(f"[{self.platform}] Could not load approved senders: {e}")

    def _save_approved_senders(self):
        """Persist approved senders for this platform to JSON file."""
        try:
            APPROVED_SENDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
            data: Dict = {}
            if APPROVED_SENDERS_FILE.exists():
                data = json.loads(APPROVED_SENDERS_FILE.read_text(encoding='utf-8'))
            data[self.platform] = list(self._approved.keys())
            APPROVED_SENDERS_FILE.write_text(
                json.dumps(data, indent=2), encoding='utf-8'
            )
        except Exception as e:
            logger.warning(f"[{self.platform}] Could not save approved senders: {e}")

    def _is_sender_approved(self, user_id: str) -> bool:
        """Return True if user is approved (or policy is 'allow')."""
        if DM_PAIRING_POLICY == 'allow':
            return True
        return self._approved.get(user_id, False)

    def _generate_pairing_code(self, user_id: str) -> str:
        """Create/return a 6-digit pairing code for this user."""
        if user_id not in self._pending_codes:
            self._pending_codes[user_id] = str(random.randint(100000, 999999))
        return self._pending_codes[user_id]

    def approve_sender(self, user_id: str):
        """Approve a user and remove their pending code."""
        self._approved[user_id] = True
        self._pending_codes.pop(user_id, None)
        self._save_approved_senders()
        logger.info(f"[{self.platform}] Approved sender: {user_id}")

    def check_pairing_code(self, user_id: str, code: str) -> bool:
        """
        Called when a user replies with a code.
        Returns True and approves if code matches.
        """
        expected = self._pending_codes.get(user_id)
        if expected and code.strip() == expected:
            self.approve_sender(user_id)
            return True
        return False

    # ------------------------------------------------------------------ #
    #  Message routing
    # ------------------------------------------------------------------ #

    async def _handle_incoming(self, message: IncomingMessage) -> Optional[str]:
        """
        Route an incoming message to the registered handler,
        applying DM pairing policy first.
        """
        if DM_PAIRING_POLICY == 'deny' and not self._is_sender_approved(message.user_id):
            logger.info(f"[{self.platform}] Denied unknown sender: {message.user_id}")
            return None

        if DM_PAIRING_POLICY == 'pair' and not self._is_sender_approved(message.user_id):
            # Check if they're submitting a pairing code
            if self.check_pairing_code(message.user_id, message.text):
                return "You've been approved! You can now chat with LADA."

            # Generate and announce new pairing code
            code = self._generate_pairing_code(message.user_id)
            logger.info(
                f"[{self.platform}] Pairing code for {message.username} ({message.user_id}): {code}"
            )
            # Notify admin via Telegram if configured (best-effort)
            if ADMIN_CHAT_ID:
                asyncio.create_task(self._notify_admin_pairing(message, code))
            return (
                f"Hi {message.username}! To start chatting with LADA, a verification "
                f"code has been sent to the administrator. Reply with the 6-digit code "
                f"to get approved."
            )

        if self._message_handler:
            try:
                return await self._message_handler(message)
            except Exception as e:
                logger.error(f"[{self.platform}] Handler error: {e}")
                return None
        return None

    async def _notify_admin_pairing(self, message: IncomingMessage, code: str):
        """Send pairing code notification to admin via Telegram (best-effort)."""
        try:
            from modules.messaging.message_router import get_message_router
            router = get_message_router()
            telegram = router.get_connector('telegram')
            if telegram and telegram.is_running:
                await telegram.send_message(OutgoingMessage(
                    text=(
                        f"DM Pairing Request\n"
                        f"Platform: {message.platform}\n"
                        f"User: {message.username} ({message.user_id})\n"
                        f"Code: {code}\n\n"
                        f"The user was told to reply with the code."
                    ),
                    chat_id=ADMIN_CHAT_ID,
                ))
        except Exception as e:
            logger.debug(f"[{self.platform}] Admin notify failed: {e}")

    # ------------------------------------------------------------------ #
    #  Properties
    # ------------------------------------------------------------------ #

    @property
    def is_running(self) -> bool:
        return self._running

    def is_configured(self) -> bool:
        """Check if the connector has the required configuration."""
        return False
