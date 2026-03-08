"""
Mattermost Connector - WebSocket-based bot for Mattermost.
Requires: pip install mattermostdriver
ENV: MATTERMOST_URL, MATTERMOST_TOKEN, MATTERMOST_BOT_NAME
"""
import os
import asyncio
import logging
from typing import Optional
from datetime import datetime

try:
    from mattermostdriver import Driver
    MATTERMOST_OK = True
except ImportError:
    Driver = None
    MATTERMOST_OK = False

from modules.messaging.base_connector import BaseConnector, IncomingMessage, OutgoingMessage

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4000


class MattermostConnector(BaseConnector):
    """Mattermost bot connector via WebSocket."""

    @property
    def platform(self) -> str:
        return "mattermost"

    def __init__(self):
        super().__init__()
        self.url = os.getenv('MATTERMOST_URL', '')
        self.token = os.getenv('MATTERMOST_TOKEN', '')
        self.bot_name = os.getenv('MATTERMOST_BOT_NAME', 'lada')
        self._driver: Optional[object] = None
        self._bot_user_id: str = ''

    def is_configured(self) -> bool:
        return bool(self.url and self.token) and MATTERMOST_OK

    async def start(self):
        if not self.is_configured():
            logger.warning("[Mattermost] Not configured — set MATTERMOST_URL + MATTERMOST_TOKEN")
            return

        try:
            from urllib.parse import urlparse
            parsed = urlparse(self.url)
            self._driver = Driver({
                'url': parsed.hostname or self.url,
                'token': self.token,
                'scheme': parsed.scheme or 'https',
                'port': parsed.port or (443 if (parsed.scheme or 'https') == 'https' else 80),
                'verify': True,
            })
            self._driver.login()
            me = self._driver.users.get_user('me')
            self._bot_user_id = me.get('id', '')
            self._running = True

            logger.info(f"[Mattermost] Connected as {me.get('username')} ({self._bot_user_id})")

            # WebSocket event loop
            await asyncio.get_event_loop().run_in_executor(
                None, self._ws_listen
            )

        except Exception as e:
            logger.error(f"[Mattermost] Start failed: {e}")
            self._running = False

    def _ws_listen(self):
        """Blocking WebSocket listener (run in executor)."""
        def handle_event(data):
            try:
                event = data.get('event', '')
                if event != 'posted':
                    return
                post = data.get('data', {}).get('post', '{}')
                import json
                post = json.loads(post) if isinstance(post, str) else post
                user_id = post.get('user_id', '')
                if user_id == self._bot_user_id:
                    return  # Don't respond to self
                message_text = post.get('message', '').strip()
                if not message_text:
                    return
                channel_id = post.get('channel_id', '')
                post_id = post.get('id', '')
                # Look up username
                try:
                    user_info = self._driver.users.get_user(user_id)
                    username = user_info.get('username', user_id)
                except Exception:
                    username = user_id

                incoming = IncomingMessage(
                    platform=self.platform,
                    user_id=user_id,
                    username=username,
                    text=message_text,
                    chat_id=channel_id,
                    message_id=post_id,
                    timestamp=datetime.now().isoformat(),
                )

                loop = asyncio.new_event_loop()
                response = loop.run_until_complete(self._handle_incoming(incoming))
                loop.close()

                if response:
                    chunks = [response[i:i+MAX_MESSAGE_LENGTH]
                              for i in range(0, len(response), MAX_MESSAGE_LENGTH)]
                    for chunk in chunks:
                        self._driver.posts.create_post(options={
                            'channel_id': channel_id,
                            'message': chunk,
                            'root_id': post_id,
                        })
            except Exception as e:
                logger.error(f"[Mattermost] Event handler error: {e}")

        try:
            self._driver.init_websocket(handle_event)
        except Exception as e:
            logger.error(f"[Mattermost] WebSocket error: {e}")
            self._running = False

    async def stop(self):
        self._running = False
        if self._driver:
            try:
                self._driver.logout()
            except Exception:
                pass
        logger.info("[Mattermost] Stopped")

    async def send_message(self, message: OutgoingMessage) -> bool:
        if not self._driver:
            return False
        try:
            chunks = [message.text[i:i+MAX_MESSAGE_LENGTH]
                      for i in range(0, len(message.text), MAX_MESSAGE_LENGTH)]
            for chunk in chunks:
                self._driver.posts.create_post(options={
                    'channel_id': message.chat_id,
                    'message': chunk,
                })
            return True
        except Exception as e:
            logger.error(f"[Mattermost] Send failed: {e}")
            return False
