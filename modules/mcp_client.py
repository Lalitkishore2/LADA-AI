"""
LADA v11.0 - MCP (Model Context Protocol) Client
Industry-standard protocol for connecting AI to external tools and services.

Supports MCP stdio and SSE transports, dynamic tool discovery,
and integration with the LADA command processor.
"""

import os
import json
import asyncio
import subprocess
import logging
import time
import threading
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Conditional imports
try:
    import aiohttp
    AIOHTTP_OK = True
except ImportError:
    AIOHTTP_OK = False


@dataclass
class MCPTool:
    """Represents an MCP tool from a server."""
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    server_name: str = ""


@dataclass
class MCPServer:
    """Configuration for an MCP server."""
    name: str
    command: str  # e.g. "npx" or "python"
    args: List[str] = field(default_factory=list)  # e.g. ["-y", "@modelcontextprotocol/server-filesystem"]
    env: Dict[str, str] = field(default_factory=dict)
    transport: str = "stdio"  # "stdio" or "sse"
    url: Optional[str] = None  # For SSE transport
    enabled: bool = True


class MCPStdioTransport:
    """
    Communicate with an MCP server over stdio (JSON-RPC).
    Launches the server as a subprocess and exchanges messages via stdin/stdout.
    """

    def __init__(self, server: MCPServer):
        self.server = server
        self._process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._lock = threading.Lock()
        self._running = False
        self._reader_thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """Start the MCP server subprocess."""
        try:
            env = dict(os.environ)
            env.update(self.server.env)

            self._process = subprocess.Popen(
                [self.server.command] + self.server.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                bufsize=0,
            )
            self._running = True
            self._reader_thread = threading.Thread(
                target=self._read_loop, daemon=True
            )
            self._reader_thread.start()
            logger.info(f"[MCP] Started server: {self.server.name}")
            return True
        except Exception as e:
            logger.error(f"[MCP] Failed to start {self.server.name}: {e}")
            return False

    def stop(self):
        """Stop the server subprocess."""
        self._running = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
            self._process = None

    def _read_loop(self):
        """Background thread reading JSON-RPC responses from stdout."""
        while self._running and self._process and self._process.stdout:
            try:
                # Read Content-Length header
                header = b""
                while self._running:
                    byte = self._process.stdout.read(1)
                    if not byte:
                        self._running = False
                        return
                    header += byte
                    if header.endswith(b"\r\n\r\n"):
                        break

                # Parse Content-Length
                header_str = header.decode('utf-8')
                content_length = 0
                for line in header_str.split('\r\n'):
                    if line.lower().startswith('content-length:'):
                        content_length = int(line.split(':')[1].strip())
                        break

                if content_length <= 0:
                    continue

                # Read body
                body = self._process.stdout.read(content_length)
                if not body:
                    continue

                msg = json.loads(body.decode('utf-8'))
                self._handle_message(msg)

            except json.JSONDecodeError as e:
                logger.debug(f"[MCP] JSON parse error: {e}")
            except Exception as e:
                if self._running:
                    logger.error(f"[MCP] Read error: {e}")
                break

    def _handle_message(self, msg: Dict[str, Any]):
        """Handle incoming JSON-RPC message."""
        msg_id = msg.get("id")
        if msg_id is not None and msg_id in self._pending:
            future = self._pending.pop(msg_id)
            if "error" in msg:
                future.set_exception(Exception(json.dumps(msg["error"])))
            else:
                future.set_result(msg.get("result", {}))

    def send_request(self, method: str, params: Optional[Dict] = None,
                     timeout: float = 30.0) -> Any:
        """
        Send a JSON-RPC request and wait for response (synchronous).
        """
        if not self._process or not self._running:
            raise ConnectionError(f"MCP server {self.server.name} not running")

        with self._lock:
            self._request_id += 1
            req_id = self._request_id

        msg = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params:
            msg["params"] = params

        # Create future for response
        future = asyncio.Future()
        # Use a simple event-based approach for sync waiting
        result_container = {"result": None, "error": None, "done": False}
        event = threading.Event()

        self._pending[req_id] = type('FutureLike', (), {
            'set_result': lambda v: (result_container.update({"result": v, "done": True}), event.set()),
            'set_exception': lambda e: (result_container.update({"error": e, "done": True}), event.set()),
        })()

        # Send request
        body = json.dumps(msg).encode('utf-8')
        header = f"Content-Length: {len(body)}\r\n\r\n".encode('utf-8')

        try:
            self._process.stdin.write(header + body)
            self._process.stdin.flush()
        except Exception as e:
            self._pending.pop(req_id, None)
            raise ConnectionError(f"Failed to send to {self.server.name}: {e}")

        # Wait for response
        event.wait(timeout=timeout)

        if not result_container["done"]:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"MCP request '{method}' timed out after {timeout}s")

        if result_container["error"]:
            raise result_container["error"]

        return result_container["result"]


class MCPSSETransport:
    """Communicate with an MCP server over Server-Sent Events."""

    def __init__(self, server: MCPServer):
        self.server = server
        self._session = None

    def start(self) -> bool:
        if not AIOHTTP_OK or not self.server.url:
            return False
        logger.info(f"[MCP] SSE transport ready for: {self.server.url}")
        return True

    def stop(self):
        pass

    def send_request(self, method: str, params: Optional[Dict] = None,
                     timeout: float = 30.0) -> Any:
        """Send request via HTTP POST to SSE endpoint."""
        if not AIOHTTP_OK or not self.server.url:
            raise ConnectionError("SSE transport not available")

        import requests
        msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
        }
        if params:
            msg["params"] = params

        try:
            resp = requests.post(
                self.server.url,
                json=msg,
                timeout=timeout,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            result = resp.json()
            if "error" in result:
                raise Exception(json.dumps(result["error"]))
            return result.get("result", {})
        except Exception as e:
            raise ConnectionError(f"SSE request failed: {e}")


class MCPClient:
    """
    MCP Client - manages multiple MCP servers and their tools.

    Features:
    - Dynamic tool discovery from MCP servers
    - Support for stdio and SSE transports
    - Tool registry with unified calling interface
    - Server lifecycle management (start/stop)
    - Configuration from JSON file
    - Graceful fallback when servers unavailable
    """

    CONFIG_FILE = "config/mcp_servers.json"

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self.CONFIG_FILE
        self._servers: Dict[str, MCPServer] = {}
        self._transports: Dict[str, Any] = {}  # MCPStdioTransport or MCPSSETransport
        self._tools: Dict[str, MCPTool] = {}  # tool_name -> MCPTool
        self._tool_to_server: Dict[str, str] = {}  # tool_name -> server_name
        self._initialized = False

        self._load_config()

    def _load_config(self):
        """Load MCP server configurations from JSON."""
        if not os.path.exists(self.config_path):
            self._create_default_config()
            return

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            for name, srv_cfg in config.get("mcpServers", {}).items():
                server = MCPServer(
                    name=name,
                    command=srv_cfg.get("command", ""),
                    args=srv_cfg.get("args", []),
                    env=srv_cfg.get("env", {}),
                    transport=srv_cfg.get("transport", "stdio"),
                    url=srv_cfg.get("url"),
                    enabled=srv_cfg.get("enabled", True),
                )
                self._servers[name] = server

            logger.info(f"[MCP] Loaded {len(self._servers)} server configs")

        except Exception as e:
            logger.error(f"[MCP] Config load error: {e}")

    def _create_default_config(self):
        """Create default MCP config with common servers."""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        default_config = {
            "mcpServers": {
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", os.path.expanduser("~")],
                    "transport": "stdio",
                    "enabled": False,
                    "_comment": "Enable to allow LADA file operations via MCP"
                },
                "web-search": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-brave-search"],
                    "env": {"BRAVE_API_KEY": ""},
                    "transport": "stdio",
                    "enabled": False,
                    "_comment": "Enable with Brave API key for web search"
                },
                "github": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                    "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": ""},
                    "transport": "stdio",
                    "enabled": False,
                    "_comment": "Enable with GitHub token for repo operations"
                },
                "memory": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-memory"],
                    "transport": "stdio",
                    "enabled": False,
                    "_comment": "Knowledge graph memory server"
                },
                "sqlite": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-sqlite", "data/lada.db"],
                    "transport": "stdio",
                    "enabled": False,
                    "_comment": "SQLite database operations"
                },
            }
        }

        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2)
            logger.info(f"[MCP] Created default config at {self.config_path}")
        except Exception as e:
            logger.error(f"[MCP] Failed to create config: {e}")

    def initialize(self) -> Dict[str, Any]:
        """
        Start all enabled MCP servers and discover their tools.

        Returns status dict with server and tool counts.
        """
        started = 0
        failed = 0
        total_tools = 0

        for name, server in self._servers.items():
            if not server.enabled:
                continue

            # Create transport
            if server.transport == "sse" and server.url:
                transport = MCPSSETransport(server)
            else:
                transport = MCPStdioTransport(server)

            if transport.start():
                self._transports[name] = transport

                # Initialize protocol
                try:
                    transport.send_request("initialize", {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "LADA", "version": "11.0"}
                    })
                    transport.send_request("notifications/initialized")
                except Exception as e:
                    logger.warning(f"[MCP] Init handshake failed for {name}: {e}")

                # Discover tools
                try:
                    result = transport.send_request("tools/list")
                    tools = result.get("tools", [])
                    for tool_def in tools:
                        tool = MCPTool(
                            name=tool_def["name"],
                            description=tool_def.get("description", ""),
                            input_schema=tool_def.get("inputSchema", {}),
                            server_name=name,
                        )
                        self._tools[tool.name] = tool
                        self._tool_to_server[tool.name] = name
                        total_tools += 1

                    logger.info(f"[MCP] {name}: {len(tools)} tools discovered")
                    started += 1
                except Exception as e:
                    logger.warning(f"[MCP] Tool discovery failed for {name}: {e}")
                    failed += 1
            else:
                failed += 1

        self._initialized = True
        status = {
            "servers_started": started,
            "servers_failed": failed,
            "total_tools": total_tools,
            "tool_names": list(self._tools.keys()),
        }
        logger.info(f"[MCP] Initialized: {started} servers, {total_tools} tools")
        return status

    def call_tool(self, tool_name: str, arguments: Dict[str, Any] = None,
                  timeout: float = 30.0) -> Dict[str, Any]:
        """
        Call an MCP tool by name.

        Returns result dict with content and status.
        """
        if tool_name not in self._tools:
            return {"error": f"Tool '{tool_name}' not found", "available_tools": list(self._tools.keys())}

        server_name = self._tool_to_server[tool_name]
        transport = self._transports.get(server_name)

        if transport is None:
            return {"error": f"Server '{server_name}' not running"}

        try:
            result = transport.send_request("tools/call", {
                "name": tool_name,
                "arguments": arguments or {},
            }, timeout=timeout)

            content = result.get("content", [])
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))

            return {
                "status": "success",
                "tool": tool_name,
                "result": "\n".join(text_parts) if text_parts else json.dumps(content),
                "raw": content,
            }

        except Exception as e:
            return {"error": str(e), "tool": tool_name}

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all available MCP tools."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "server": tool.server_name,
                "input_schema": tool.input_schema,
            }
            for tool in self._tools.values()
        ]

    def get_tools_for_llm(self) -> List[Dict[str, Any]]:
        """
        Get tool definitions in format suitable for LLM function calling.
        Optimized for token efficiency.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description[:200],  # Token optimization
                    "parameters": tool.input_schema,
                }
            }
            for tool in self._tools.values()
        ]

    def add_server(self, name: str, command: str, args: List[str] = None,
                   env: Dict[str, str] = None, transport: str = "stdio",
                   url: Optional[str] = None) -> bool:
        """Dynamically add a new MCP server."""
        server = MCPServer(
            name=name, command=command,
            args=args or [], env=env or {},
            transport=transport, url=url, enabled=True,
        )
        self._servers[name] = server

        # Save to config
        try:
            config = {}
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = json.load(f)

            if "mcpServers" not in config:
                config["mcpServers"] = {}

            config["mcpServers"][name] = {
                "command": command,
                "args": args or [],
                "env": env or {},
                "transport": transport,
                "url": url,
                "enabled": True,
            }

            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)

            return True
        except Exception as e:
            logger.error(f"[MCP] Failed to save server config: {e}")
            return False

    def shutdown(self):
        """Gracefully stop all MCP servers."""
        for name, transport in self._transports.items():
            try:
                transport.stop()
                logger.info(f"[MCP] Stopped server: {name}")
            except Exception as e:
                logger.error(f"[MCP] Error stopping {name}: {e}")
        self._transports.clear()
        self._tools.clear()
        self._tool_to_server.clear()

    def get_stats(self) -> Dict[str, Any]:
        return {
            "initialized": self._initialized,
            "servers_configured": len(self._servers),
            "servers_running": len(self._transports),
            "tools_available": len(self._tools),
            "servers": {
                name: {
                    "enabled": srv.enabled,
                    "running": name in self._transports,
                    "transport": srv.transport,
                }
                for name, srv in self._servers.items()
            }
        }


# Singleton
_mcp_client: Optional[MCPClient] = None

def get_mcp_client(config_path: Optional[str] = None) -> MCPClient:
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient(config_path=config_path)
    return _mcp_client
