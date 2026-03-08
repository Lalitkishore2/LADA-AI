"""
LINE Connector - Webhook-based bot for LINE Messaging API.
Requires: pip install line-bot-sdk
ENV: LINE_CHANNEL_TOKEN, LINE_CHANNEL_SECRET
The LINE webhook must point to POST /messaging/line on the LADA API server.
"""
import os
import logging
from typing import Optional
from datetime import datetime

try:
    from linebot import LineBotApi, WebhookHandler
    from linebot.models import MessageEvent, TextMessage, TextSendMessage
    from linebot.exceptions import InvalidSignatureError
    LINE_OK = True
except ImportError:
    LineBotApi = None
    WebhookHandler = None
    MessageEvent = None
    TextMessage = None
    TextSendMessage = None
    InvalidSignatureError = Exception
    LINE_OK = False

from modules.messaging.base_connector import BaseConnector, IncomingMessage, OutgoingMessage

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 5000


class LINEConnector(BaseConnector):
    """LINE Messaging API bot connector (webhook mode)."""

    @property
    def platform(self) -> str:
        return "line"

    def __init__(self):
        super().__init__()
        self.channel_token = os.getenv('LINE_CHANNEL_TOKEN', '')
        self.channel_secret = os.getenv('LINE_CHANNEL_SECRET', '')
        self._api: Optional[object] = None
        self._handler: Optional[object] = None

    def is_configured(self) -> bool:
        return bool(self.channel_token and self.channel_secret) and LINE_OK

    def _setup(self):
        if self._api is None and LINE_OK:
            self._api = LineBotApi(self.channel_token)
            self._handler = WebhookHandler(self.channel_secret)

            @self._handler.add(MessageEvent, message=TextMessage)
            def _on_message(event):
                import asyncio
                user_id = event.source.user_id
                try:
                    profile = self._api.get_profile(user_id)
                    username = profile.display_name
                except Exception:
                    username = user_id
                chat_id = event.source.user_id
                if hasattr(event.source, 'group_id'):
                    chat_id = event.source.group_id
                elif hasattr(event.source, 'room_id'):
                    chat_id = event.source.room_id

                incoming = IncomingMessage(
                    platform=self.platform,
                    user_id=user_id,
                    username=username,
                    text=event.message.text,
                    chat_id=chat_id,
                    message_id=event.message.id,
                    timestamp=datetime.now().isoformat(),
                )

                loop = asyncio.new_event_loop()
                response = loop.run_until_complete(self._handle_incoming(incoming))
                loop.close()

                if response:
                    chunks = [response[i:i+MAX_MESSAGE_LENGTH]
                              for i in range(0, len(response), MAX_MESSAGE_LENGTH)]
                    for chunk in chunks:
                        self._api.reply_message(
                            event.reply_token if len(chunks) == 1 else None,
                            TextSendMessage(text=chunk)
                        ) if event.reply_token else self._api.push_message(
                            chat_id, TextSendMessage(text=chunk)
                        )

    async def handle_webhook(self, body: str, signature: str) -> bool:
        """
        Called by api_server.py POST /messaging/line.
        Returns True if signature valid and event processed.
        """
        if not self.is_configured() or not self._handler:
            return False
        try:
            self._handler.handle(body, signature)
            return True
        except InvalidSignatureError:
            logger.warning("[LINE] Invalid webhook signature")
            return False
        except Exception as e:
            logger.error(f"[LINE] Webhook error: {e}")
            return False

    async def start(self):
        if not self.is_configured():
            logger.warning("[LINE] Not configured — set LINE_CHANNEL_TOKEN + LINE_CHANNEL_SECRET")
            return
        self._setup()
        self._running = True
        logger.info("[LINE] Connector ready (webhook mode — waiting for POST /messaging/line)")

    async def stop(self):
        self._running = False
        logger.info("[LINE] Stopped")

    async def send_message(self, message: OutgoingMessage) -> bool:
        if not self._api:
            return False
        try:
            chunks = [message.text[i:i+MAX_MESSAGE_LENGTH]
                      for i in range(0, len(message.text), MAX_MESSAGE_LENGTH)]
            for chunk in chunks:
                self._api.push_message(message.chat_id, TextSendMessage(text=chunk))
            return True
        except Exception as e:
            logger.error(f"[LINE] Send failed: {e}")
            return False
