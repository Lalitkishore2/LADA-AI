"""
LADA - Telegram Connector
Routes messages between Telegram and LADA's command processor.
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
    from telegram import Update, Bot
    from telegram.ext import (
        Application, CommandHandler, MessageHandler as TGMessageHandler,
        ContextTypes, filters,
    )
    TELEGRAM_OK = True
except ImportError:
    TELEGRAM_OK = False


class TelegramConnector(BaseConnector):
    """Telegram bot connector using python-telegram-bot library."""

    @property
    def platform(self) -> str:
        return "telegram"

    def __init__(self):
        super().__init__()
        self.token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.allowed_users = os.getenv('TELEGRAM_ALLOWED_USERS', '').split(',')
        self.allowed_users = [u.strip() for u in self.allowed_users if u.strip()]
        self._app: Optional[object] = None

    def is_configured(self) -> bool:
        return bool(self.token) and TELEGRAM_OK

    async def start(self):
        if not self.is_configured():
            logger.warning("[Telegram] Not configured (missing token or library)")
            return

        self._app = Application.builder().token(self.token).build()

        # Register handlers
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(
            TGMessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message)
        )

        self._running = True
        logger.info("[Telegram] Starting polling...")

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

    async def stop(self):
        self._running = False
        if self._app:
            try:
                await self._app.updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            except Exception as e:
                logger.error(f"[Telegram] Shutdown error: {e}")
        logger.info("[Telegram] Stopped")

    async def send_message(self, message: OutgoingMessage) -> bool:
        if not self._app:
            return False
        try:
            bot: Bot = self._app.bot
            await bot.send_message(
                chat_id=int(message.chat_id),
                text=message.text,
                parse_mode='Markdown' if message.parse_mode == 'markdown' else None,
            )
            return True
        except Exception as e:
            logger.error(f"[Telegram] Send failed: {e}")
            return False

    def _is_allowed(self, user_id: str, username: str) -> bool:
        """Check if user is in the allowed list (empty list = allow all)."""
        if not self.allowed_users:
            return True
        return user_id in self.allowed_users or username in self.allowed_users

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "LADA AI Assistant connected.\n"
            "Send me any message and I'll process it."
        )

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "LADA Telegram Bot\n\n"
            "Send any text message to interact with LADA.\n"
            "Commands:\n"
            "/start - Initialize bot\n"
            "/help - Show this message"
        )

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return

        user = update.effective_user
        user_id = str(user.id)
        username = user.username or ""

        if not self._is_allowed(user_id, username):
            await update.message.reply_text("Access denied.")
            return

        incoming = IncomingMessage(
            platform="telegram",
            user_id=user_id,
            username=username,
            text=update.message.text,
            chat_id=str(update.effective_chat.id),
            message_id=str(update.message.message_id),
        )

        response = await self._handle_incoming(incoming)
        if response:
            # Telegram has a 4096 char limit per message
            for i in range(0, len(response), 4000):
                chunk = response[i:i + 4000]
                await update.message.reply_text(chunk)
