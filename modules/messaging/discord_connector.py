"""
LADA - Discord Connector
Routes messages between Discord and LADA's command processor.
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
    import discord
    from discord.ext import commands
    DISCORD_OK = True
except ImportError:
    DISCORD_OK = False


class DiscordConnector(BaseConnector):
    """Discord bot connector using discord.py library."""

    @property
    def platform(self) -> str:
        return "discord"

    def __init__(self):
        super().__init__()
        self.token = os.getenv('DISCORD_BOT_TOKEN', '')
        self.allowed_channels = os.getenv('DISCORD_ALLOWED_CHANNELS', '').split(',')
        self.allowed_channels = [c.strip() for c in self.allowed_channels if c.strip()]
        self.bot_prefix = os.getenv('DISCORD_BOT_PREFIX', '!')
        self._bot: Optional[object] = None
        self._task: Optional[asyncio.Task] = None

    def is_configured(self) -> bool:
        return bool(self.token) and DISCORD_OK

    async def start(self):
        if not self.is_configured():
            logger.warning("[Discord] Not configured (missing token or library)")
            return

        intents = discord.Intents.default()
        intents.message_content = True

        self._bot = commands.Bot(command_prefix=self.bot_prefix, intents=intents)

        @self._bot.event
        async def on_ready():
            logger.info(f"[Discord] Connected as {self._bot.user}")

        @self._bot.event
        async def on_message(message):
            if message.author == self._bot.user:
                return

            # Check channel restriction
            if self.allowed_channels and str(message.channel.id) not in self.allowed_channels:
                return

            # Respond to mentions or DMs
            is_dm = isinstance(message.channel, discord.DMChannel)
            is_mentioned = self._bot.user in message.mentions if message.mentions else False

            if not is_dm and not is_mentioned:
                # Check for bot prefix
                if not message.content.startswith(self.bot_prefix):
                    return
                text = message.content[len(self.bot_prefix):].strip()
            else:
                text = message.content.replace(f'<@{self._bot.user.id}>', '').strip()

            if not text:
                return

            incoming = IncomingMessage(
                platform="discord",
                user_id=str(message.author.id),
                username=str(message.author),
                text=text,
                chat_id=str(message.channel.id),
                message_id=str(message.id),
            )

            response = await self._handle_incoming(incoming)
            if response:
                # Discord has a 2000 char limit per message
                for i in range(0, len(response), 1900):
                    chunk = response[i:i + 1900]
                    await message.reply(chunk)

        self._running = True
        logger.info("[Discord] Starting bot...")
        self._task = asyncio.create_task(self._bot.start(self.token))

    async def stop(self):
        self._running = False
        if self._bot:
            try:
                await self._bot.close()
            except Exception as e:
                logger.error(f"[Discord] Shutdown error: {e}")
        if self._task:
            self._task.cancel()
        logger.info("[Discord] Stopped")

    async def send_message(self, message: OutgoingMessage) -> bool:
        if not self._bot:
            return False
        try:
            channel = self._bot.get_channel(int(message.chat_id))
            if channel:
                await channel.send(message.text)
                return True
        except Exception as e:
            logger.error(f"[Discord] Send failed: {e}")
        return False
