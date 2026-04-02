"""LADA OpenClaw Gateway Client

WebSocket client for OpenClaw gateway integration.

Features:
- WebSocket connection to OpenClaw gateway
- Session management
- Command routing
- Event subscriptions
- Browser control via CDP bridge
- Skills execution

Environment variables:
- OPENCLAW_GATEWAY_URL: Gateway WebSocket URL (default: ws://127.0.0.1:18789)
- OPENCLAW_RECONNECT: Auto-reconnect on disconnect (default: true)
- OPENCLAW_DEBUG: Enable debug logging (default: false)

Usage:
    from integrations.openclaw_gateway import OpenClawGateway
    
    gateway = OpenClawGateway()
    await gateway.connect()
    await gateway.navigate("https://google.com")
    snapshot = await gateway.get_snapshot()
"""

from __future__ import annotations

import os
import json
import asyncio
import logging
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# Optional dependencies
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    websockets = None
    WEBSOCKETS_AVAILABLE = False


class OpenClawState(Enum):
    """Gateway connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class OpenClawConfig:
    """OpenClaw gateway configuration."""
    url: str = "ws://127.0.0.1:18789"
    auto_reconnect: bool = True
    reconnect_interval: float = 5.0
    timeout: float = 30.0
    debug: bool = False
    
    @classmethod
    def from_env(cls) -> "OpenClawConfig":
        """Load config from environment."""
        return cls(
            url=os.getenv("OPENCLAW_GATEWAY_URL", "ws://127.0.0.1:18789"),
            auto_reconnect=os.getenv("OPENCLAW_RECONNECT", "true").lower() == "true",
            debug=os.getenv("OPENCLAW_DEBUG", "false").lower() == "true",
        )


@dataclass
class BrowserSnapshot:
    """Browser page snapshot for AI analysis."""
    url: str
    title: str
    elements: List[Dict]  # Interactive elements
    text_content: str
    screenshot_base64: Optional[str] = None


@dataclass 
class OpenClawEvent:
    """Event from OpenClaw gateway."""
    type: str
    data: Dict
    timestamp: float = field(default_factory=lambda: __import__('time').time())


class OpenClawGateway:
    """WebSocket client for OpenClaw gateway.
    
    Provides browser control and skills execution via OpenClaw gateway.
    """
    
    def __init__(self, config: Optional[OpenClawConfig] = None):
        """Initialize gateway client.
        
        Args:
            config: Gateway configuration
        """
        if not WEBSOCKETS_AVAILABLE:
            logger.warning("[OpenClaw] websockets not installed. Install with: pip install websockets")
        
        self.config = config or OpenClawConfig.from_env()
        self._ws = None
        self._state = OpenClawState.DISCONNECTED
        self._session_id: Optional[str] = None
        self._message_id = 0
        self._pending_responses: Dict[int, asyncio.Future] = {}
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._receive_task: Optional[asyncio.Task] = None
        
        logger.info(f"[OpenClaw] Gateway init: {self.config.url}")
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to gateway."""
        return self._state == OpenClawState.CONNECTED and self._ws is not None
    
    async def connect(self) -> bool:
        """Connect to OpenClaw gateway.
        
        Returns:
            True if connected successfully
        """
        if not WEBSOCKETS_AVAILABLE:
            logger.error("[OpenClaw] websockets not available")
            return False
        
        if self.is_connected:
            return True
        
        self._state = OpenClawState.CONNECTING
        
        try:
            self._ws = await websockets.connect(
                self.config.url,
                ping_interval=20,
                ping_timeout=20,
            )
            
            # Start receive loop
            self._receive_task = asyncio.create_task(self._receive_loop())
            
            # Initialize session
            response = await self._send("init", {})
            if response and response.get("status") == "ok":
                self._session_id = response.get("session_id")
                self._state = OpenClawState.CONNECTED
                logger.info(f"[OpenClaw] Connected, session: {self._session_id}")
                return True
            
            raise Exception("Session init failed")
            
        except Exception as e:
            logger.error(f"[OpenClaw] Connection failed: {e}")
            self._state = OpenClawState.ERROR
            return False
    
    async def disconnect(self):
        """Disconnect from gateway."""
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self._ws:
            await self._ws.close()
            self._ws = None
        
        self._state = OpenClawState.DISCONNECTED
        self._session_id = None
        logger.info("[OpenClaw] Disconnected")
    
    async def _send(self, method: str, params: Dict) -> Optional[Dict]:
        """Send message to gateway.
        
        Args:
            method: Method name
            params: Method parameters
            
        Returns:
            Response or None
        """
        if not self._ws:
            return None
        
        self._message_id += 1
        msg_id = self._message_id
        
        message = {
            "id": msg_id,
            "method": method,
            "params": params,
        }
        
        if self._session_id:
            message["session_id"] = self._session_id
        
        # Create future for response
        future = asyncio.Future()
        self._pending_responses[msg_id] = future
        
        try:
            await self._ws.send(json.dumps(message))
            
            if self.config.debug:
                logger.debug(f"[OpenClaw] Send: {method}")
            
            # Wait for response
            response = await asyncio.wait_for(future, timeout=self.config.timeout)
            return response
            
        except asyncio.TimeoutError:
            logger.warning(f"[OpenClaw] Timeout: {method}")
            return None
        except Exception as e:
            logger.error(f"[OpenClaw] Send error: {e}")
            return None
        finally:
            self._pending_responses.pop(msg_id, None)
    
    async def _receive_loop(self):
        """Receive messages from gateway."""
        try:
            async for raw in self._ws:
                try:
                    message = json.loads(raw)
                    
                    # Check if it's a response to a pending request
                    msg_id = message.get("id")
                    if msg_id and msg_id in self._pending_responses:
                        self._pending_responses[msg_id].set_result(message.get("result"))
                        continue
                    
                    # Handle event
                    if "event" in message:
                        event = OpenClawEvent(
                            type=message["event"],
                            data=message.get("data", {})
                        )
                        await self._handle_event(event)
                        
                except json.JSONDecodeError:
                    continue
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[OpenClaw] Receive error: {e}")
            self._state = OpenClawState.ERROR
    
    async def _handle_event(self, event: OpenClawEvent):
        """Handle gateway event.
        
        Args:
            event: Event object
        """
        if self.config.debug:
            logger.debug(f"[OpenClaw] Event: {event.type}")
        
        handlers = self._event_handlers.get(event.type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"[OpenClaw] Event handler error: {e}")
    
    def on_event(self, event_type: str, handler: Callable):
        """Register event handler.
        
        Args:
            event_type: Event type to handle
            handler: Async callback function
        """
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
    
    # ─────────────────────────────────────────────────────────────────
    # Browser Control
    # ─────────────────────────────────────────────────────────────────
    
    async def navigate(self, url: str) -> bool:
        """Navigate browser to URL.
        
        Args:
            url: Target URL
            
        Returns:
            True if successful
        """
        response = await self._send("browser.navigate", {"url": url})
        return response is not None and response.get("status") == "ok"
    
    async def click(self, selector: str) -> bool:
        """Click element by selector.
        
        Args:
            selector: CSS selector or element ID
            
        Returns:
            True if clicked
        """
        response = await self._send("browser.click", {"selector": selector})
        return response is not None and response.get("status") == "ok"
    
    async def type_text(self, selector: str, text: str) -> bool:
        """Type text into element.
        
        Args:
            selector: CSS selector
            text: Text to type
            
        Returns:
            True if typed
        """
        response = await self._send("browser.type", {
            "selector": selector,
            "text": text
        })
        return response is not None and response.get("status") == "ok"
    
    async def scroll(self, direction: str = "down", amount: int = 500) -> bool:
        """Scroll page.
        
        Args:
            direction: Scroll direction (up, down, left, right)
            amount: Scroll amount in pixels
            
        Returns:
            True if scrolled
        """
        response = await self._send("browser.scroll", {
            "direction": direction,
            "amount": amount
        })
        return response is not None and response.get("status") == "ok"
    
    async def get_snapshot(self) -> Optional[BrowserSnapshot]:
        """Get page snapshot for AI analysis.
        
        Returns:
            BrowserSnapshot or None
        """
        response = await self._send("browser.snapshot", {})
        
        if response:
            return BrowserSnapshot(
                url=response.get("url", ""),
                title=response.get("title", ""),
                elements=response.get("elements", []),
                text_content=response.get("text", ""),
                screenshot_base64=response.get("screenshot"),
            )
        return None
    
    async def extract_text(self, selector: str = None) -> str:
        """Extract text from page or element.
        
        Args:
            selector: Optional CSS selector
            
        Returns:
            Extracted text
        """
        response = await self._send("browser.extract", {"selector": selector})
        if response:
            return response.get("text", "")
        return ""
    
    async def fill_form(self, fields: Dict[str, str]) -> bool:
        """Fill form fields.
        
        Args:
            fields: Dict of selector -> value
            
        Returns:
            True if filled
        """
        response = await self._send("browser.fill_form", {"fields": fields})
        return response is not None and response.get("status") == "ok"
    
    async def screenshot(self) -> Optional[bytes]:
        """Capture screenshot.
        
        Returns:
            PNG image bytes
        """
        import base64
        response = await self._send("browser.screenshot", {})
        
        if response and response.get("data"):
            return base64.b64decode(response["data"])
        return None
    
    async def execute_js(self, script: str) -> Any:
        """Execute JavaScript.
        
        Args:
            script: JavaScript code
            
        Returns:
            Script result
        """
        response = await self._send("browser.execute", {"script": script})
        if response:
            return response.get("result")
        return None
    
    # ─────────────────────────────────────────────────────────────────
    # Skills Execution
    # ─────────────────────────────────────────────────────────────────
    
    async def list_skills(self) -> List[Dict]:
        """List available skills.
        
        Returns:
            List of skill info dicts
        """
        response = await self._send("skills.list", {})
        if response:
            return response.get("skills", [])
        return []
    
    async def execute_skill(self, skill_name: str, params: Dict = None) -> Optional[Dict]:
        """Execute a skill.
        
        Args:
            skill_name: Skill name
            params: Skill parameters
            
        Returns:
            Skill result
        """
        response = await self._send("skills.execute", {
            "skill": skill_name,
            "params": params or {}
        })
        return response
    
    async def install_skill(self, skill_url: str) -> bool:
        """Install skill from URL.
        
        Args:
            skill_url: URL to skill (GitHub, ClawHub, etc.)
            
        Returns:
            True if installed
        """
        response = await self._send("skills.install", {"url": skill_url})
        return response is not None and response.get("status") == "ok"
    
    # ─────────────────────────────────────────────────────────────────
    # Session Management
    # ─────────────────────────────────────────────────────────────────
    
    async def new_session(self) -> Optional[str]:
        """Create new browser session.
        
        Returns:
            Session ID
        """
        response = await self._send("session.new", {})
        if response:
            return response.get("session_id")
        return None
    
    async def close_session(self) -> bool:
        """Close current session.
        
        Returns:
            True if closed
        """
        response = await self._send("session.close", {})
        return response is not None

    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()


# Convenience functions
_gateway: Optional[OpenClawGateway] = None


def get_openclaw_gateway(**kwargs) -> OpenClawGateway:
    """Get or create OpenClaw gateway singleton."""
    global _gateway
    if _gateway is None:
        _gateway = OpenClawGateway(**kwargs)
    return _gateway


async def openclaw_navigate(url: str) -> bool:
    """Navigate via OpenClaw."""
    gateway = get_openclaw_gateway()
    if not gateway.is_connected:
        await gateway.connect()
    return await gateway.navigate(url)


async def openclaw_snapshot() -> Optional[BrowserSnapshot]:
    """Get snapshot via OpenClaw."""
    gateway = get_openclaw_gateway()
    if not gateway.is_connected:
        await gateway.connect()
    return await gateway.get_snapshot()
