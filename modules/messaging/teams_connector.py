"""
Microsoft Teams Connector - Bot Framework webhook handler.
Requires: pip install botbuilder-core botbuilder-schema
ENV: TEAMS_APP_ID, TEAMS_APP_PASSWORD
The bot must be registered in Azure Bot Service and the webhook
pointed to POST /messaging/teams on the LADA API server.
"""
import os
import logging
import asyncio
from typing import Optional
from datetime import datetime

try:
    from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext
    from botbuilder.schema import Activity
    TEAMS_OK = True
except ImportError:
    BotFrameworkAdapter = None
    BotFrameworkAdapterSettings = None
    TurnContext = None
    Activity = None
    TEAMS_OK = False

from modules.messaging.base_connector import BaseConnector, IncomingMessage, OutgoingMessage

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4000


class TeamsConnector(BaseConnector):
    """Microsoft Teams bot connector via Bot Framework adapter."""

    @property
    def platform(self) -> str:
        return "teams"

    def __init__(self):
        super().__init__()
        self.app_id = os.getenv('TEAMS_APP_ID', '')
        self.app_password = os.getenv('TEAMS_APP_PASSWORD', '')
        self._adapter: Optional[object] = None
        self._pending_activities: asyncio.Queue = asyncio.Queue()

    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_password) and TEAMS_OK

    def get_adapter(self):
        """Return the Bot Framework adapter (lazy init)."""
        if self._adapter is None and TEAMS_OK:
            settings = BotFrameworkAdapterSettings(self.app_id, self.app_password)
            self._adapter = BotFrameworkAdapter(settings)
        return self._adapter

    async def process_activity(self, activity: 'Activity', auth_header: str) -> None:
        """
        Called by api_server.py POST /messaging/teams endpoint.
        Processes an incoming Bot Framework Activity.
        """
        if not TEAMS_OK or not self._adapter:
            return

        async def _bot_logic(turn_context: 'TurnContext'):
            text = turn_context.activity.text or ''
            text = text.strip()
            if not text:
                return

            user = turn_context.activity.from_property
            user_id = user.id if user else 'unknown'
            username = user.name if user else 'unknown'
            channel = turn_context.activity.channel_data or {}
            chat_id = turn_context.activity.conversation.id

            incoming = IncomingMessage(
                platform=self.platform,
                user_id=user_id,
                username=username,
                text=text,
                chat_id=chat_id,
                message_id=turn_context.activity.id or '',
                timestamp=datetime.now().isoformat(),
            )

            response = await self._handle_incoming(incoming)
            if response:
                chunks = [response[i:i+MAX_MESSAGE_LENGTH]
                          for i in range(0, len(response), MAX_MESSAGE_LENGTH)]
                for chunk in chunks:
                    await turn_context.send_activity(chunk)

        await self._adapter.process_activity(activity, auth_header, _bot_logic)

    async def start(self):
        if not self.is_configured():
            logger.warning("[Teams] Not configured — set TEAMS_APP_ID + TEAMS_APP_PASSWORD")
            return
        self.get_adapter()
        self._running = True
        logger.info("[Teams] Connector ready (webhook mode — waiting for POST /messaging/teams)")

    async def stop(self):
        self._running = False
        logger.info("[Teams] Stopped")

    async def send_message(self, message: OutgoingMessage) -> bool:
        """
        Proactive send is complex with Bot Framework; log for now.
        Replies are sent inline via process_activity().
        """
        logger.info(f"[Teams] Proactive send to {message.chat_id}: {message.text[:80]}")
        return False
