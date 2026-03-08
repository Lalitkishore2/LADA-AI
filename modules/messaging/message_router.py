"""
LADA - Message Router
Central router that manages all messaging connectors and routes
messages through LADA's command processor.
"""

import os
import logging
import asyncio
import time
from typing import Optional, Dict, List, Any

from modules.messaging.base_connector import (
    BaseConnector, IncomingMessage, OutgoingMessage
)

logger = logging.getLogger(__name__)

# Away message — if set, auto-reply with this when LADA is busy or offline
AWAY_MESSAGE = os.getenv('AWAY_MESSAGE', '')
# If >0, auto-reply after this many seconds of inactivity (0 = disabled)
AWAY_AFTER_SECONDS = int(os.getenv('AWAY_AFTER_SECONDS', '0'))


class MessageRouter:
    """
    Central message router for all messaging platforms.

    Manages connector lifecycle (start/stop) and routes incoming messages
    through LADA's AI router or command processor, returning responses
    back through the originating connector.
    """

    def __init__(self, ai_router=None, command_processor=None):
        self.ai_router = ai_router
        self.command_processor = command_processor
        self.connectors: Dict[str, BaseConnector] = {}
        self._running = False
        self._last_active: float = time.time()  # Track last time LADA was active

    def register_connector(self, connector: BaseConnector):
        """Register a messaging connector."""
        connector.set_message_handler(self._handle_message)
        self.connectors[connector.platform] = connector
        logger.info(f"[MessageRouter] Registered: {connector.platform}")

    def register_all_connectors(self):
        """Auto-discover and register all available connectors."""
        try:
            from modules.messaging.telegram_connector import TelegramConnector
            tc = TelegramConnector()
            if tc.is_configured():
                self.register_connector(tc)
        except ImportError:
            pass

        try:
            from modules.messaging.discord_connector import DiscordConnector
            dc = DiscordConnector()
            if dc.is_configured():
                self.register_connector(dc)
        except ImportError:
            pass

        try:
            from modules.messaging.whatsapp_connector import WhatsAppConnector
            wc = WhatsAppConnector()
            if wc.is_configured():
                self.register_connector(wc)
        except ImportError:
            pass

        try:
            from modules.messaging.slack_connector import SlackConnector
            sc = SlackConnector()
            if sc.is_configured():
                self.register_connector(sc)
        except ImportError:
            pass

        try:
            from modules.messaging.mattermost_connector import MattermostConnector
            mc = MattermostConnector()
            if mc.is_configured():
                self.register_connector(mc)
        except ImportError:
            pass

        try:
            from modules.messaging.teams_connector import TeamsConnector
            tc2 = TeamsConnector()
            if tc2.is_configured():
                self.register_connector(tc2)
        except ImportError:
            pass

        try:
            from modules.messaging.line_connector import LINEConnector
            lc = LINEConnector()
            if lc.is_configured():
                self.register_connector(lc)
        except ImportError:
            pass

        try:
            from modules.messaging.signal_connector import SignalConnector
            sig = SignalConnector()
            if sig.is_configured():
                self.register_connector(sig)
        except ImportError:
            pass

        try:
            from modules.messaging.matrix_connector import MatrixConnector
            mx = MatrixConnector()
            if mx.is_configured():
                self.register_connector(mx)
        except ImportError:
            pass

        logger.info(
            f"[MessageRouter] {len(self.connectors)} connector(s) registered: "
            f"{list(self.connectors.keys())}"
        )

    async def start_all(self):
        """Start all registered connectors."""
        self._running = True
        tasks = []
        for name, connector in self.connectors.items():
            if connector.is_configured():
                tasks.append(self._start_connector(name, connector))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _start_connector(self, name: str, connector: BaseConnector):
        """Start a single connector with error handling."""
        try:
            await connector.start()
            logger.info(f"[MessageRouter] Started: {name}")
        except Exception as e:
            logger.error(f"[MessageRouter] Failed to start {name}: {e}")

    async def stop_all(self):
        """Stop all running connectors."""
        self._running = False
        tasks = []
        for name, connector in self.connectors.items():
            if connector.is_running:
                tasks.append(self._stop_connector(name, connector))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _stop_connector(self, name: str, connector: BaseConnector):
        """Stop a single connector with error handling."""
        try:
            await connector.stop()
        except Exception as e:
            logger.error(f"[MessageRouter] Failed to stop {name}: {e}")

    async def _handle_message(self, message: IncomingMessage) -> Optional[str]:
        """
        Core message handler - routes incoming messages through LADA.

        Tries the command processor first (for system commands),
        then falls back to the AI router for general queries.
        Auto-replies with AWAY_MESSAGE if LADA has been inactive
        longer than AWAY_AFTER_SECONDS.
        """
        logger.info(
            f"[MessageRouter] {message.platform}:{message.username} -> "
            f"{message.text[:50]}..."
        )

        # Auto-reply if away message is configured and LADA is idle
        if AWAY_MESSAGE and AWAY_AFTER_SECONDS > 0:
            idle_for = time.time() - self._last_active
            if idle_for > AWAY_AFTER_SECONDS:
                logger.info(f"[MessageRouter] Auto-reply (idle {idle_for:.0f}s): {message.platform}")
                return AWAY_MESSAGE

        self._last_active = time.time()

        # Try command processor first (handles system commands like "volume up")
        if self.command_processor:
            try:
                result = self.command_processor.process_command(message.text)
                if result and result.get('handled'):
                    return result.get('response', 'Done.')
            except Exception as e:
                logger.error(f"[MessageRouter] Command processor error: {e}")

        # Fall back to AI router
        if self.ai_router:
            try:
                response = self.ai_router.query(message.text)
                if response:
                    return response
            except Exception as e:
                logger.error(f"[MessageRouter] AI router error: {e}")

        return "I couldn't process that request. Please try again."

    async def send_to_platform(self, platform: str, chat_id: str, text: str) -> bool:
        """Send a message to a specific platform and chat."""
        connector = self.connectors.get(platform)
        if not connector or not connector.is_running:
            return False

        return await connector.send_message(OutgoingMessage(
            text=text,
            chat_id=chat_id,
        ))

    async def broadcast(self, text: str, chat_ids: Dict[str, str]) -> Dict[str, bool]:
        """
        Broadcast a message to multiple platforms.

        Args:
            text: Message text
            chat_ids: Dict of {platform: chat_id}

        Returns:
            Dict of {platform: success}
        """
        results = {}
        for platform, chat_id in chat_ids.items():
            results[platform] = await self.send_to_platform(platform, chat_id, text)
        return results

    def get_status(self) -> List[Dict[str, Any]]:
        """Get status of all connectors."""
        return [
            {
                'platform': name,
                'configured': conn.is_configured(),
                'running': conn.is_running,
            }
            for name, conn in self.connectors.items()
        ]

    def get_connector(self, platform: str) -> Optional[BaseConnector]:
        """Get a specific connector by platform name."""
        return self.connectors.get(platform)

    def list_connectors(self) -> List[str]:
        """Return list of registered platform names."""
        return list(self.connectors.keys())


# Singleton
_router = None


def get_message_router(ai_router=None, command_processor=None) -> MessageRouter:
    """Get or create the global message router."""
    global _router
    if _router is None:
        _router = MessageRouter(
            ai_router=ai_router,
            command_processor=command_processor,
        )
        _router.register_all_connectors()
    return _router
