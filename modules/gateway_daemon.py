"""
LADA Gateway Daemon

Headless long-running bridge service for web/remote clients.
Runs the FastAPI + WebSocket API without opening any local UI.
"""

from __future__ import annotations

import os
import asyncio
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GatewayDaemonConfig:
    """Runtime config for the gateway daemon."""

    host: str = "0.0.0.0"
    port: int = 18790
    log_level: str = "info"

    @classmethod
    def from_env(cls) -> "GatewayDaemonConfig":
        raw_port = os.getenv("LADA_GATEWAY_PORT", "18790").strip()
        try:
            port = int(raw_port)
        except ValueError:
            port = 18790
        return cls(
            host=os.getenv("LADA_GATEWAY_HOST", "0.0.0.0").strip() or "0.0.0.0",
            port=max(1, min(port, 65535)),
            log_level=(os.getenv("LADA_GATEWAY_LOG_LEVEL", "info").strip() or "info").lower(),
        )


class GatewayDaemon:
    """Headless daemon wrapper around LADA API server."""

    def __init__(self, config: GatewayDaemonConfig | None = None):
        self.config = config or GatewayDaemonConfig.from_env()
        self._server = None

    def build_server(self):
        """Construct and return uvicorn.Server instance."""
        try:
            import uvicorn
            from modules.api_server import LADAAPIServer
        except ImportError as exc:
            raise RuntimeError(
                "Gateway daemon dependencies missing. Install fastapi + uvicorn."
            ) from exc

        api = LADAAPIServer(host=self.config.host, port=self.config.port)
        config = uvicorn.Config(
            api.app,
            host=self.config.host,
            port=self.config.port,
            log_level=self.config.log_level,
        )
        self._server = uvicorn.Server(config)
        return self._server

    async def run_async(self):
        """Run daemon in current event loop."""
        server = self._server or self.build_server()
        await server.serve()

    def run(self):
        """Run daemon synchronously."""
        logger.info(
            "[GatewayDaemon] Starting on %s:%s",
            self.config.host,
            self.config.port,
        )
        asyncio.run(self.run_async())


def run_gateway_daemon():
    """Convenience entrypoint for CLI use."""
    GatewayDaemon().run()

