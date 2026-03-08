"""
LADA - WhatsApp Connector
Routes messages between WhatsApp (via Twilio) and LADA's command processor.
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
    from twilio.rest import Client as TwilioClient
    TWILIO_OK = True
except ImportError:
    TWILIO_OK = False

try:
    from fastapi import Request
    FASTAPI_OK = True
except ImportError:
    FASTAPI_OK = False


class WhatsAppConnector(BaseConnector):
    """
    WhatsApp connector using Twilio API.

    This connector works via webhooks: Twilio calls our endpoint when a message
    arrives, and we use the Twilio API to send responses.
    Requires a running FastAPI server with the webhook route registered.
    """

    @property
    def platform(self) -> str:
        return "whatsapp"

    def __init__(self):
        super().__init__()
        self.account_sid = os.getenv('TWILIO_ACCOUNT_SID', '')
        self.auth_token = os.getenv('TWILIO_AUTH_TOKEN', '')
        self.whatsapp_number = os.getenv('TWILIO_WHATSAPP_NUMBER', '')
        self._client: Optional[object] = None

    def is_configured(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.whatsapp_number) and TWILIO_OK

    async def start(self):
        if not self.is_configured():
            logger.warning("[WhatsApp] Not configured (missing Twilio credentials)")
            return

        self._client = TwilioClient(self.account_sid, self.auth_token)
        self._running = True
        logger.info("[WhatsApp] Ready (webhook mode - register /api/whatsapp/webhook)")

    async def stop(self):
        self._running = False
        self._client = None
        logger.info("[WhatsApp] Stopped")

    async def send_message(self, message: OutgoingMessage) -> bool:
        if not self._client:
            return False
        try:
            self._client.messages.create(
                body=message.text,
                from_=f"whatsapp:{self.whatsapp_number}",
                to=f"whatsapp:{message.chat_id}",
            )
            return True
        except Exception as e:
            logger.error(f"[WhatsApp] Send failed: {e}")
            return False

    async def handle_webhook(self, form_data: dict) -> Optional[str]:
        """
        Process incoming Twilio webhook data.
        Call this from a FastAPI route handler.
        """
        body = form_data.get('Body', '')
        from_number = form_data.get('From', '').replace('whatsapp:', '')
        message_sid = form_data.get('MessageSid', '')

        if not body:
            return None

        incoming = IncomingMessage(
            platform="whatsapp",
            user_id=from_number,
            username=from_number,
            text=body,
            chat_id=from_number,
            message_id=message_sid,
        )

        response = await self._handle_incoming(incoming)

        # Send response back
        if response and self._client:
            await self.send_message(OutgoingMessage(
                text=response,
                chat_id=from_number,
            ))

        return response
