"""Feature-flagged LADA browser adapter.

This module intentionally keeps browser gateway integration in adapter mode only:
- No eager imports of archived gateway modules on normal startup
- No hard dependency on websockets unless adapter mode is enabled and used
- Explicit command-driven lifecycle (connect / navigate / snapshot / disconnect)

Environment variables:
- LADA_BROWSER_ADAPTER_ENABLED: enable adapter mode (default: 0)
- LADA_BROWSER_GATEWAY_URL: gateway URL (default: ws://127.0.0.1:18789)
- LADA_BROWSER_TIMEOUT_SEC: adapter call timeout (default: 20)
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _flag_enabled(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


class LadaBrowserAdapter:
    """Lazy adapter around archived browser gateway module."""

    def __init__(
        self,
        gateway_url: Optional[str] = None,
        timeout_sec: Optional[float] = None,
        enabled: bool = True,
    ):
        self.enabled = bool(enabled)
        self.gateway_url = gateway_url or os.getenv(
            "LADA_BROWSER_GATEWAY_URL",
            "ws://127.0.0.1:18789",
        )
        if timeout_sec is None:
            timeout_sec = float(os.getenv("LADA_BROWSER_TIMEOUT_SEC", "20"))
        self.timeout_sec = max(5.0, float(timeout_sec))

        self._gateway_module = None
        self._gateway = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        self._state = "disabled" if not self.enabled else "idle"
        self._last_error = ""

    def _archived_gateway_path(self) -> Path:
        repo_root = Path(__file__).resolve().parents[1]
        return repo_root / "archived" / "integrations" / "openclaw_gateway.py"

    def _load_gateway_module(self):
        if self._gateway_module is not None:
            return self._gateway_module

        path = self._archived_gateway_path()
        if not path.exists():
            raise FileNotFoundError(f"Archived browser gateway not found at: {path}")

        spec = importlib.util.spec_from_file_location("lada_archived_browser_gateway", path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Failed to build import spec for archived browser gateway")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self._gateway_module = module
        return module

    def _ensure_loop(self):
        with self._lock:
            if self._loop is not None and self._loop.is_running():
                return

            ready = threading.Event()

            def _run_loop():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                ready.set()
                loop.run_forever()
                pending = asyncio.all_tasks(loop=loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.close()

            self._loop_thread = threading.Thread(
                target=_run_loop,
                daemon=True,
                name="LADA-BrowserAdapterLoop",
            )
            self._loop_thread.start()
            ready.wait(timeout=2)

    def _stop_loop(self):
        with self._lock:
            loop = self._loop
            thread = self._loop_thread
            self._loop = None
            self._loop_thread = None

        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None and thread.is_alive():
            thread.join(timeout=0.5)

    def _run(self, coro):
        self._ensure_loop()
        if self._loop is None:
            raise RuntimeError("Browser adapter event loop is not available")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=self.timeout_sec)

    async def _get_gateway(self):
        if self._gateway is not None:
            return self._gateway

        module = self._load_gateway_module()
        config_cls = getattr(module, "OpenClawConfig")
        gateway_cls = getattr(module, "OpenClawGateway")

        config = config_cls.from_env()
        config.url = self.gateway_url
        self._gateway = gateway_cls(config=config)
        return self._gateway

    async def _connect_async(self) -> bool:
        gateway = await self._get_gateway()
        if gateway.is_connected:
            self._state = "connected"
            return True

        self._state = "connecting"
        ok = await gateway.connect()
        self._state = "connected" if ok else "error"
        if not ok:
            self._last_error = "connection failed"
        return bool(ok)

    async def _disconnect_async(self):
        if self._gateway is not None:
            try:
                if self._gateway.is_connected:
                    await self._gateway.disconnect()
            finally:
                self._state = "idle"

    async def _navigate_async(self, url: str) -> bool:
        gateway = await self._get_gateway()
        if not gateway.is_connected:
            ok = await self._connect_async()
            if not ok:
                return False
        return bool(await gateway.navigate(url))

    async def _click_async(self, selector: str) -> bool:
        gateway = await self._get_gateway()
        if not gateway.is_connected:
            ok = await self._connect_async()
            if not ok:
                return False
        return bool(await gateway.click(selector))

    async def _type_async(self, selector: str, text: str) -> bool:
        gateway = await self._get_gateway()
        if not gateway.is_connected:
            ok = await self._connect_async()
            if not ok:
                return False
        return bool(await gateway.type_text(selector, text))

    async def _scroll_async(self, direction: str = "down", amount: int = 500) -> bool:
        gateway = await self._get_gateway()
        if not gateway.is_connected:
            ok = await self._connect_async()
            if not ok:
                return False
        return bool(await gateway.scroll(direction=direction, amount=amount))

    async def _extract_text_async(self, selector: Optional[str] = None) -> str:
        gateway = await self._get_gateway()
        if not gateway.is_connected:
            ok = await self._connect_async()
            if not ok:
                return ""
        return str(await gateway.extract_text(selector=selector))

    async def _snapshot_async(self) -> Optional[dict]:
        gateway = await self._get_gateway()
        if not gateway.is_connected:
            ok = await self._connect_async()
            if not ok:
                return None

        snapshot = await gateway.get_snapshot()
        if snapshot is None:
            return None

        return {
            "url": snapshot.url,
            "title": snapshot.title,
            "interactive_elements": len(snapshot.elements or []),
            "text_chars": len(snapshot.text_content or ""),
            "has_screenshot": bool(snapshot.screenshot_base64),
        }

    def status(self) -> dict:
        connected = bool(self._gateway is not None and getattr(self._gateway, "is_connected", False))
        return {
            "enabled": self.enabled,
            "state": self._state,
            "connected": connected,
            "url": self.gateway_url,
            "last_error": self._last_error,
        }

    def connect(self) -> bool:
        if not self.enabled:
            self._state = "disabled"
            return False
        try:
            return bool(self._run(self._connect_async()))
        except Exception as e:
            self._state = "error"
            self._last_error = str(e)
            logger.warning("[LadaBrowserAdapter] connect failed: %s", e)
            return False

    def disconnect(self):
        if not self.enabled:
            self._state = "disabled"
            return
        try:
            self._run(self._disconnect_async())
        except Exception as e:
            logger.warning("[LadaBrowserAdapter] disconnect warning: %s", e)
        finally:
            self._stop_loop()

    def navigate(self, url: str) -> bool:
        if not self.enabled:
            self._state = "disabled"
            return False
        try:
            return bool(self._run(self._navigate_async(url)))
        except Exception as e:
            self._state = "error"
            self._last_error = str(e)
            logger.warning("[LadaBrowserAdapter] navigate failed: %s", e)
            return False

    def click(self, selector: str) -> bool:
        if not self.enabled:
            self._state = "disabled"
            return False
        try:
            return bool(self._run(self._click_async(selector)))
        except Exception as e:
            self._state = "error"
            self._last_error = str(e)
            logger.warning("[LadaBrowserAdapter] click failed: %s", e)
            return False

    def type_text(self, selector: str, text: str) -> bool:
        if not self.enabled:
            self._state = "disabled"
            return False
        try:
            return bool(self._run(self._type_async(selector, text)))
        except Exception as e:
            self._state = "error"
            self._last_error = str(e)
            logger.warning("[LadaBrowserAdapter] type failed: %s", e)
            return False

    def scroll(self, direction: str = "down", amount: int = 500) -> bool:
        if not self.enabled:
            self._state = "disabled"
            return False
        try:
            return bool(self._run(self._scroll_async(direction=direction, amount=amount)))
        except Exception as e:
            self._state = "error"
            self._last_error = str(e)
            logger.warning("[LadaBrowserAdapter] scroll failed: %s", e)
            return False

    def extract_text(self, selector: Optional[str] = None) -> str:
        if not self.enabled:
            self._state = "disabled"
            return ""
        try:
            return str(self._run(self._extract_text_async(selector=selector)) or "")
        except Exception as e:
            self._state = "error"
            self._last_error = str(e)
            logger.warning("[LadaBrowserAdapter] extract text failed: %s", e)
            return ""

    def snapshot_summary(self) -> Optional[dict]:
        if not self.enabled:
            self._state = "disabled"
            return None
        try:
            return self._run(self._snapshot_async())
        except Exception as e:
            self._state = "error"
            self._last_error = str(e)
            logger.warning("[LadaBrowserAdapter] snapshot failed: %s", e)
            return None


_adapter_singleton: Optional[LadaBrowserAdapter] = None


def lada_browser_adapter_enabled() -> bool:
    return _flag_enabled("LADA_BROWSER_ADAPTER_ENABLED", "0")


def get_lada_browser_adapter(force: bool = False) -> Optional[LadaBrowserAdapter]:
    """Get singleton LADA browser adapter only when feature-flag is enabled.

    Args:
        force: bypass feature flag check when caller already validated enablement.
    """
    global _adapter_singleton

    if not force and not lada_browser_adapter_enabled():
        return None

    if _adapter_singleton is None:
        _adapter_singleton = LadaBrowserAdapter(enabled=True)
    return _adapter_singleton


