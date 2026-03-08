"""
Signal Connector - JSON-RPC bridge to signal-cli.
Requires: signal-cli running as daemon on SIGNAL_CLI_URL (default http://localhost:8080)
Docs: https://github.com/AsamK/signal-cli/blob/master/man/signal-cli-jsonrpc.md
ENV: SIGNAL_PHONE, SIGNAL_CLI_URL
"""
import os
import json
import asyncio
import logging
import aiohttp
from typing import Optional
from datetime import datetime

from modules.messaging.base_connector import BaseConnector, IncomingMessage, OutgoingMessage

logger = logging.getLogger(__name__)


class SignalConnector(BaseConnector):
    """Signal bot connector via signal-cli JSON-RPC sidecar."""

    @property
    def platform(self) -> str:
        return "signal"

    def __init__(self):
        super().__init__()
        self.phone = os.getenv('SIGNAL_PHONE', '')
        self.cli_url = os.getenv('SIGNAL_CLI_URL', 'http://localhost:8080')
        self._task: Optional[asyncio.Task] = None

    def is_configured(self) -> bool:
        return bool(self.phone)

    async def start(self):
        if not self.is_configured():
            logger.warning("[Signal] Not configured — set SIGNAL_PHONE")
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(f"[Signal] Polling {self.cli_url} for {self.phone}")

    async def _poll_loop(self):
        """Poll signal-cli JSON-RPC for new messages."""
        while self._running:
            try:
                messages = await self._receive_messages()
                for msg in messages:
                    await self._dispatch(msg)
            except Exception as e:
                logger.debug(f"[Signal] Poll error: {e}")
            await asyncio.sleep(1.0)

    async def _receive_messages(self):
        """Call signal-cli receive via JSON-RPC."""
        payload = {
            "jsonrpc": "2.0",
            "method": "receive",
            "params": {"account": self.phone, "timeout": 1},
            "id": 1,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.cli_url}/api/v1/rpc",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return data.get('result', []) or []

    async def _dispatch(self, raw: dict):
        """Parse a signal-cli message event and route to handler."""
        envelope = raw.get('envelope', {})
        data_msg = envelope.get('dataMessage', {})
        if not data_msg:
            return
        text = data_msg.get('message', '').strip()
        if not text:
            return
        sender = envelope.get('source', '')
        username = envelope.get('sourceName') or sender
        group_info = data_msg.get('groupInfo', {})
        chat_id = group_info.get('groupId') or sender
        ts = envelope.get('timestamp', '')

        incoming = IncomingMessage(
            platform=self.platform,
            user_id=sender,
            username=username,
            text=text,
            chat_id=chat_id,
            timestamp=str(ts) if ts else datetime.now().isoformat(),
        )

        response = await self._handle_incoming(incoming)
        if response:
            await self._send_rpc(chat_id, response)

    async def _send_rpc(self, recipient: str, text: str):
        """Send a message via signal-cli JSON-RPC."""
        # Determine if group or individual
        params = {"account": self.phone, "message": text}
        if len(recipient) > 20:  # heuristic: group IDs are long base64
            params["groupId"] = recipient
        else:
            params["recipient"] = [recipient]

        payload = {
            "jsonrpc": "2.0",
            "method": "send",
            "params": params,
            "id": 2,
        }
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"{self.cli_url}/api/v1/rpc",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                )
        except Exception as e:
            logger.error(f"[Signal] Send failed: {e}")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("[Signal] Stopped")

    async def send_message(self, message: OutgoingMessage) -> bool:
        try:
            await self._send_rpc(message.chat_id, message.text)
            return True
        except Exception as e:
            logger.error(f"[Signal] Send failed: {e}")
            return False
