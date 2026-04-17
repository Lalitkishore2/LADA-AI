"""
LADA ACP Bridge Module

Agent Communication Protocol bridge for IDE integration.

Features:
- ACP session management
- IDE agent connection
- Request/response routing
- Context synchronization
"""

from modules.acp_bridge.server import (
    ACPSession,
    ACPMessage,
    ACPMessageType,
    ACPServer,
    get_acp_server,
)

from modules.acp_bridge.protocol import (
    ACPRequest,
    ACPResponse,
    ACPNotification,
    ACPError,
    ACPErrorCode,
)

__all__ = [
    # Server
    'ACPSession',
    'ACPMessage',
    'ACPMessageType',
    'ACPServer',
    'get_acp_server',
    # Protocol
    'ACPRequest',
    'ACPResponse',
    'ACPNotification',
    'ACPError',
    'ACPErrorCode',
]
