"""
LADA - Slack Connector
Routes messages between Slack and LADA's command processor.
"""

import os
import logging
import asyncio
from typing import Optional

from modules.messaging.base_connector import (
    BaseConnector, IncomingMessage, OutgoingMessage
)

logger = logging.getLogger(__name__)

# Conditional import
try:
    from slack_sdk.web.async_client import AsyncWebClient
    from slack_sdk.socket_mode.aiohttp import SocketModeClient
    from slack_sdk.socket_mode.request import SocketModeRequest
    from slack_sdk.socket_mode.response import SocketModeResponse
    SLACK_OK = True
except ImportError:
    SLACK_OK = False


class SlackConnector(BaseConnector):
    """Slack connector using Socket Mode (no public URL needed)."""

    @property
    def platform(self) -> str:
        return "slack"

    def __init__(self):
        super().__init__()
        self.bot_token = os.getenv('SLACK_BOT_TOKEN', '')
        self.app_token = os.getenv('SLACK_APP_TOKEN', '')
        self.allowed_channels = os.getenv('SLACK_ALLOWED_CHANNELS', '').split(',')
        self.allowed_channels = [c.strip() for c in self.allowed_channels if c.strip()]
        self._web_client: Optional[object] = None
        self._socket_client: Optional[object] = None
        self._bot_user_id: Optional[str] = None

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.app_token) and SLACK_OK

    async def start(self):
        if not self.is_configured():
            logger.warning("[Slack] Not configured (missing tokens or library)")
            return

        self._web_client = AsyncWebClient(token=self.bot_token)

        # Get bot user ID
        try:
            auth_response = await self._web_client.auth_test()
            self._bot_user_id = auth_response.get('user_id')
        except Exception as e:
            logger.error(f"[Slack] Auth test failed: {e}")
            return

        self._socket_client = SocketModeClient(
            app_token=self.app_token,
            web_client=AsyncWebClient(token=self.bot_token),
        )

        self._socket_client.socket_mode_request_listeners.append(self._on_event)

        self._running = True
        logger.info(f"[Slack] Starting (bot user: {self._bot_user_id})")
        await self._socket_client.connect()

    async def stop(self):
        self._running = False
        if self._socket_client:
            try:
                await self._socket_client.disconnect()
            except Exception as e:
                logger.error(f"[Slack] Shutdown error: {e}")
        logger.info("[Slack] Stopped")

    async def send_message(self, message: OutgoingMessage) -> bool:
        if not self._web_client:
            return False
        try:
            await self._web_client.chat_postMessage(
                channel=message.chat_id,
                text=message.text,
            )
            return True
        except Exception as e:
            logger.error(f"[Slack] Send failed: {e}")
            return False

    async def _on_event(self, client: object, req: object):
        """Handle incoming Socket Mode events."""
        if req.type == "events_api":
            # Acknowledge the event
            response = SocketModeResponse(envelope_id=req.envelope_id)
            await client.send_socket_mode_response(response)

            event = req.payload.get('event', {})
            event_type = event.get('type')

            if event_type == 'message' and 'subtype' not in event:
                await self._handle_message_event(event)

            elif event_type == 'app_mention':
                await self._handle_message_event(event)

    async def _handle_message_event(self, event: dict):
        """Process a Slack message event."""
        user_id = event.get('user', '')
        text = event.get('text', '')
        channel = event.get('channel', '')
        ts = event.get('ts', '')

        # Ignore bot's own messages
        if user_id == self._bot_user_id:
            return

        # Check channel restriction
        if self.allowed_channels and channel not in self.allowed_channels:
            return

        # Remove bot mention from text
        if self._bot_user_id:
            text = text.replace(f'<@{self._bot_user_id}>', '').strip()

        if not text:
            return

        incoming = IncomingMessage(
            platform="slack",
            user_id=user_id,
            username=user_id,
            text=text,
            chat_id=channel,
            message_id=ts,
        )

        response = await self._handle_incoming(incoming)
        if response:
            await self.send_message(OutgoingMessage(
                text=response,
                chat_id=channel,
            ))
