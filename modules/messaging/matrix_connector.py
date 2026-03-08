"""
Matrix Connector - Sync polling bot for Matrix homeservers.
Requires: pip install matrix-nio
ENV: MATRIX_HOMESERVER, MATRIX_ACCESS_TOKEN, MATRIX_BOT_USER_ID
"""
import os
import asyncio
import logging
from typing import Optional
from datetime import datetime

try:
    from nio import AsyncClient, MatrixRoom, RoomMessageText, LoginResponse
    MATRIX_OK = True
except ImportError:
    AsyncClient = None
    MatrixRoom = None
    RoomMessageText = None
    LoginResponse = None
    MATRIX_OK = False

from modules.messaging.base_connector import BaseConnector, IncomingMessage, OutgoingMessage

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 10000


class MatrixConnector(BaseConnector):
    """Matrix bot connector via matrix-nio sync polling."""

    @property
    def platform(self) -> str:
        return "matrix"

    def __init__(self):
        super().__init__()
        self.homeserver = os.getenv('MATRIX_HOMESERVER', '')
        self.access_token = os.getenv('MATRIX_ACCESS_TOKEN', '')
        self.bot_user_id = os.getenv('MATRIX_BOT_USER_ID', '')
        self._client: Optional[object] = None
        self._task: Optional[asyncio.Task] = None

    def is_configured(self) -> bool:
        return bool(self.homeserver and self.access_token) and MATRIX_OK

    async def start(self):
        if not self.is_configured():
            logger.warning("[Matrix] Not configured — set MATRIX_HOMESERVER + MATRIX_ACCESS_TOKEN")
            return

        try:
            self._client = AsyncClient(self.homeserver)
            self._client.access_token = self.access_token
            if self.bot_user_id:
                self._client.user_id = self.bot_user_id

            self._client.add_event_callback(self._on_message, RoomMessageText)
            self._running = True

            # Run initial sync to skip old messages
            await self._client.sync(timeout=3000, full_state=True)
            logger.info(f"[Matrix] Connected to {self.homeserver}")

            self._task = asyncio.create_task(self._sync_loop())

        except Exception as e:
            logger.error(f"[Matrix] Start failed: {e}")
            self._running = False

    async def _sync_loop(self):
        """Continuous sync polling loop."""
        while self._running:
            try:
                await self._client.sync(timeout=30000)
            except Exception as e:
                logger.debug(f"[Matrix] Sync error: {e}")
                await asyncio.sleep(5.0)

    async def _on_message(self, room: 'MatrixRoom', event: 'RoomMessageText'):
        """Handle incoming Matrix room message."""
        # Skip our own messages
        if self.bot_user_id and event.sender == self.bot_user_id:
            return

        text = (event.body or '').strip()
        if not text:
            return

        incoming = IncomingMessage(
            platform=self.platform,
            user_id=event.sender,
            username=event.sender.split(':')[0].lstrip('@'),
            text=text,
            chat_id=room.room_id,
            message_id=event.event_id,
            timestamp=datetime.fromtimestamp(event.server_timestamp / 1000).isoformat(),
        )

        response = await self._handle_incoming(incoming)
        if response:
            chunks = [response[i:i+MAX_MESSAGE_LENGTH]
                      for i in range(0, len(response), MAX_MESSAGE_LENGTH)]
            for chunk in chunks:
                await self._client.room_send(
                    room_id=room.room_id,
                    message_type='m.room.message',
                    content={
                        'msgtype': 'm.text',
                        'body': chunk,
                    },
                )

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
        logger.info("[Matrix] Stopped")

    async def send_message(self, message: OutgoingMessage) -> bool:
        if not self._client:
            return False
        try:
            chunks = [message.text[i:i+MAX_MESSAGE_LENGTH]
                      for i in range(0, len(message.text), MAX_MESSAGE_LENGTH)]
            for chunk in chunks:
                await self._client.room_send(
                    room_id=message.chat_id,
                    message_type='m.room.message',
                    content={'msgtype': 'm.text', 'body': chunk},
                )
            return True
        except Exception as e:
            logger.error(f"[Matrix] Send failed: {e}")
            return False
