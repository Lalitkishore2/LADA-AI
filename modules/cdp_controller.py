"""LADA CDP (Chrome DevTools Protocol) Controller

Direct WebSocket connection to Chrome DevTools Protocol for advanced browser control.

Features:
- Direct WebSocket connection to ws://localhost:9222
- Page snapshots (accessibility tree)
- Network interception
- Performance monitoring
- Cookie/session management
- DOM inspection and manipulation
- JavaScript evaluation with return values

Environment variables:
- CDP_HOST: Chrome DevTools host (default: localhost)
- CDP_PORT: Chrome DevTools port (default: 9222)
- CDP_DEBUG: Enable debug logging (default: false)

Usage:
    # Start Chrome with remote debugging:
    # chrome.exe --remote-debugging-port=9222
    
    from modules.cdp_controller import CDPController
    
    cdp = CDPController()
    cdp.connect()
    cdp.navigate("https://example.com")
    snapshot = cdp.get_accessibility_tree()
"""

from __future__ import annotations

import os
import json
import logging
import threading
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Optional dependencies
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    requests = None
    REQUESTS_AVAILABLE = False

try:
    import websocket
    WEBSOCKET_AVAILABLE = True
except ImportError:
    websocket = None
    WEBSOCKET_AVAILABLE = False


@dataclass
class CDPConfig:
    """CDP connection configuration."""
    host: str = "localhost"
    port: int = 9222
    debug: bool = False
    timeout: float = 30.0
    
    @classmethod
    def from_env(cls) -> "CDPConfig":
        """Load config from environment."""
        return cls(
            host=os.getenv("CDP_HOST", "localhost"),
            port=int(os.getenv("CDP_PORT", "9222")),
            debug=os.getenv("CDP_DEBUG", "false").lower() == "true",
        )


@dataclass
class CDPTarget:
    """Represents a Chrome debuggable target (tab/page)."""
    id: str
    type: str
    title: str
    url: str
    ws_url: str
    
    @classmethod
    def from_json(cls, data: Dict) -> "CDPTarget":
        return cls(
            id=data.get("id", ""),
            type=data.get("type", ""),
            title=data.get("title", ""),
            url=data.get("url", ""),
            ws_url=data.get("webSocketDebuggerUrl", ""),
        )


class CDPController:
    """Chrome DevTools Protocol controller for advanced browser automation.
    
    Provides low-level access to Chrome via CDP WebSocket connection.
    """
    
    def __init__(self, config: Optional[CDPConfig] = None):
        """Initialize CDP controller.
        
        Args:
            config: CDP configuration
        """
        if not WEBSOCKET_AVAILABLE:
            raise ImportError("websocket-client required: pip install websocket-client")
        
        self.config = config or CDPConfig.from_env()
        self._ws: Optional[websocket.WebSocket] = None
        self._target: Optional[CDPTarget] = None
        self._message_id = 0
        self._callbacks: Dict[int, Callable] = {}
        self._responses: Dict[int, Any] = {}
        self._lock = threading.Lock()
        self._connected = False
        
        logger.info(f"[CDP] Init: {self.config.host}:{self.config.port}")
    
    @property
    def base_url(self) -> str:
        """Get CDP HTTP base URL."""
        return f"http://{self.config.host}:{self.config.port}"
    
    def get_targets(self) -> List[CDPTarget]:
        """Get list of debuggable targets (tabs).
        
        Returns:
            List of CDPTarget objects
        """
        if not REQUESTS_AVAILABLE:
            return []
        
        try:
            response = requests.get(
                f"{self.base_url}/json/list",
                timeout=5
            )
            if response.ok:
                targets = [CDPTarget.from_json(t) for t in response.json()]
                logger.debug(f"[CDP] Found {len(targets)} targets")
                return targets
        except Exception as e:
            logger.error(f"[CDP] Failed to get targets: {e}")
        
        return []
    
    def connect(self, target_id: str = None) -> bool:
        """Connect to a Chrome target via WebSocket.
        
        Args:
            target_id: Specific target ID (default: first page target)
            
        Returns:
            True if connected successfully
        """
        try:
            # Get available targets
            targets = self.get_targets()
            if not targets:
                logger.error("[CDP] No targets available. Is Chrome running with --remote-debugging-port?")
                return False
            
            # Find target
            if target_id:
                self._target = next((t for t in targets if t.id == target_id), None)
            else:
                # Get first page target
                self._target = next(
                    (t for t in targets if t.type == "page"),
                    targets[0]
                )
            
            if not self._target or not self._target.ws_url:
                logger.error("[CDP] No valid target found")
                return False
            
            # Connect WebSocket
            self._ws = websocket.create_connection(
                self._target.ws_url,
                timeout=self.config.timeout
            )
            self._connected = True
            
            logger.info(f"[CDP] Connected to: {self._target.title}")
            
            # Enable required domains
            self._enable_domains()
            
            return True
            
        except Exception as e:
            logger.error(f"[CDP] Connection failed: {e}")
            return False
    
    def _enable_domains(self):
        """Enable CDP domains for full functionality."""
        domains = ["Page", "DOM", "Network", "Runtime", "Accessibility"]
        
        for domain in domains:
            self.send(f"{domain}.enable")
    
    def disconnect(self):
        """Disconnect from Chrome."""
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None
        
        self._connected = False
        self._target = None
        logger.info("[CDP] Disconnected")
    
    def _next_id(self) -> int:
        """Get next message ID."""
        with self._lock:
            self._message_id += 1
            return self._message_id
    
    def send(self, method: str, params: Dict = None, wait: bool = True) -> Optional[Dict]:
        """Send CDP command.
        
        Args:
            method: CDP method (e.g., "Page.navigate")
            params: Method parameters
            wait: Wait for response
            
        Returns:
            Response result or None
        """
        if not self._connected or not self._ws:
            logger.warning("[CDP] Not connected")
            return None
        
        msg_id = self._next_id()
        message = {
            "id": msg_id,
            "method": method,
            "params": params or {}
        }
        
        try:
            self._ws.send(json.dumps(message))
            
            if self.config.debug:
                logger.debug(f"[CDP] Send: {method}")
            
            if wait:
                return self._wait_response(msg_id)
            
            return {"id": msg_id}
            
        except Exception as e:
            logger.error(f"[CDP] Send error: {e}")
            return None
    
    def _wait_response(self, msg_id: int, timeout: float = None) -> Optional[Dict]:
        """Wait for response to message.
        
        Args:
            msg_id: Message ID to wait for
            timeout: Max wait time
            
        Returns:
            Response result or None
        """
        timeout = timeout or self.config.timeout
        deadline = __import__('time').time() + timeout
        
        while __import__('time').time() < deadline:
            try:
                raw = self._ws.recv()
                response = json.loads(raw)
                
                if response.get("id") == msg_id:
                    if "error" in response:
                        logger.error(f"[CDP] Error: {response['error']}")
                        return None
                    return response.get("result", {})
                
                # Store event for later processing
                if "method" in response:
                    self._handle_event(response)
                
            except Exception as e:
                logger.debug(f"[CDP] Recv error: {e}")
                break
        
        logger.warning(f"[CDP] Timeout waiting for response {msg_id}")
        return None
    
    def _handle_event(self, event: Dict):
        """Handle CDP event."""
        method = event.get("method", "")
        params = event.get("params", {})
        
        if self.config.debug:
            logger.debug(f"[CDP] Event: {method}")
    
    # ─────────────────────────────────────────────────────────────────
    # High-level API
    # ─────────────────────────────────────────────────────────────────
    
    def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to URL.
        
        Args:
            url: Target URL
            
        Returns:
            Result dict
        """
        result = self.send("Page.navigate", {"url": url})
        
        if result:
            # Wait for load
            self.send("Page.loadEventFired", wait=False)
            return {
                "success": True,
                "url": url,
                "frameId": result.get("frameId")
            }
        
        return {"success": False, "url": url}
    
    def evaluate(self, expression: str) -> Any:
        """Evaluate JavaScript expression.
        
        Args:
            expression: JavaScript code
            
        Returns:
            Expression result
        """
        result = self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True
        })
        
        if result:
            return result.get("result", {}).get("value")
        return None
    
    def get_document(self) -> Optional[Dict]:
        """Get DOM document node.
        
        Returns:
            Document node info
        """
        return self.send("DOM.getDocument")
    
    def query_selector(self, selector: str, node_id: int = None) -> Optional[int]:
        """Find element by CSS selector.
        
        Args:
            selector: CSS selector
            node_id: Parent node ID (default: document)
            
        Returns:
            Node ID or None
        """
        if node_id is None:
            doc = self.get_document()
            if doc:
                node_id = doc.get("root", {}).get("nodeId")
        
        if not node_id:
            return None
        
        result = self.send("DOM.querySelector", {
            "nodeId": node_id,
            "selector": selector
        })
        
        if result:
            return result.get("nodeId")
        return None
    
    def click_element(self, selector: str) -> bool:
        """Click element by selector.
        
        Args:
            selector: CSS selector
            
        Returns:
            True if clicked
        """
        # Use JavaScript click for reliability
        script = f"""
            document.querySelector('{selector}').click();
            true;
        """
        return self.evaluate(script) == True
    
    def type_text(self, selector: str, text: str) -> bool:
        """Type text into element.
        
        Args:
            selector: CSS selector
            text: Text to type
            
        Returns:
            True if typed
        """
        script = f"""
            const el = document.querySelector('{selector}');
            el.focus();
            el.value = '{text}';
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            true;
        """
        return self.evaluate(script) == True
    
    def get_accessibility_tree(self) -> Optional[Dict]:
        """Get full accessibility tree (for AI analysis).
        
        Returns:
            Accessibility tree structure
        """
        result = self.send("Accessibility.getFullAXTree")
        
        if result:
            return result.get("nodes", [])
        return None
    
    def get_accessibility_snapshot(self) -> List[Dict]:
        """Get simplified accessibility snapshot for AI.
        
        Returns:
            List of interactive elements with roles and names
        """
        tree = self.get_accessibility_tree()
        if not tree:
            return []
        
        # Extract interactive elements
        elements = []
        for node in tree:
            role = node.get("role", {}).get("value", "")
            name = node.get("name", {}).get("value", "")
            
            # Filter for interactive elements
            interactive_roles = [
                "button", "link", "textbox", "checkbox", "radio",
                "combobox", "listbox", "menu", "menuitem", "tab",
                "searchbox", "switch"
            ]
            
            if role in interactive_roles:
                elements.append({
                    "role": role,
                    "name": name,
                    "nodeId": node.get("nodeId"),
                    "backendNodeId": node.get("backendDOMNodeId"),
                })
        
        return elements
    
    def screenshot(self, format: str = "png", quality: int = 80) -> Optional[bytes]:
        """Capture screenshot.
        
        Args:
            format: Image format (png, jpeg, webp)
            quality: JPEG/WebP quality (0-100)
            
        Returns:
            Image data bytes
        """
        result = self.send("Page.captureScreenshot", {
            "format": format,
            "quality": quality if format != "png" else None
        })
        
        if result:
            import base64
            return base64.b64decode(result.get("data", ""))
        return None
    
    def get_cookies(self) -> List[Dict]:
        """Get all cookies.
        
        Returns:
            List of cookie objects
        """
        result = self.send("Network.getAllCookies")
        if result:
            return result.get("cookies", [])
        return []
    
    def set_cookie(self, name: str, value: str, domain: str, **kwargs) -> bool:
        """Set a cookie.
        
        Args:
            name: Cookie name
            value: Cookie value
            domain: Cookie domain
            **kwargs: Additional cookie properties
            
        Returns:
            True if set successfully
        """
        params = {
            "name": name,
            "value": value,
            "domain": domain,
            **kwargs
        }
        result = self.send("Network.setCookie", params)
        return result is not None
    
    def clear_cookies(self) -> bool:
        """Clear all cookies.
        
        Returns:
            True if cleared
        """
        result = self.send("Network.clearBrowserCookies")
        return result is not None
    
    def intercept_requests(self, patterns: List[str]) -> bool:
        """Enable request interception for patterns.
        
        Args:
            patterns: URL patterns to intercept (e.g., ["*://api.*"])
            
        Returns:
            True if enabled
        """
        result = self.send("Fetch.enable", {
            "patterns": [{"urlPattern": p} for p in patterns]
        })
        return result is not None
    
    def get_performance_metrics(self) -> Dict[str, float]:
        """Get page performance metrics.
        
        Returns:
            Dict of metric name to value
        """
        result = self.send("Performance.getMetrics")
        
        if result:
            metrics = result.get("metrics", [])
            return {m["name"]: m["value"] for m in metrics}
        return {}
    
    def get_html(self) -> str:
        """Get full page HTML.
        
        Returns:
            HTML source
        """
        return self.evaluate("document.documentElement.outerHTML") or ""
    
    def get_text(self) -> str:
        """Get page text content.
        
        Returns:
            Text content
        """
        return self.evaluate("document.body.innerText") or ""
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()


# Convenience functions
_cdp: Optional[CDPController] = None


def get_cdp_controller(**kwargs) -> CDPController:
    """Get or create CDP controller singleton."""
    global _cdp
    if _cdp is None:
        _cdp = CDPController(**kwargs)
    return _cdp


def connect_cdp() -> bool:
    """Connect to Chrome via CDP."""
    return get_cdp_controller().connect()


def navigate_cdp(url: str) -> Dict[str, Any]:
    """Navigate using CDP."""
    cdp = get_cdp_controller()
    if not cdp._connected:
        cdp.connect()
    return cdp.navigate(url)
