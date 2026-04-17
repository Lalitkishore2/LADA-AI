"""
LADA ACP Protocol Definitions

Agent Communication Protocol message types and structures.
Based on emerging agent-to-agent protocols for IDE integration.

Features:
- JSON-RPC style request/response
- Notification support
- Error codes
- Context passing
"""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field
from enum import Enum


# ============================================================================
# Enums
# ============================================================================

class ACPErrorCode(int, Enum):
    """Standard ACP error codes."""
    # Standard JSON-RPC codes
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    
    # ACP-specific codes
    SESSION_NOT_FOUND = -33001
    SESSION_EXPIRED = -33002
    UNAUTHORIZED = -33003
    CONTEXT_TOO_LARGE = -33004
    TOOL_NOT_AVAILABLE = -33005
    AGENT_BUSY = -33006
    TIMEOUT = -33007
    CANCELLED = -33008


class ACPMethod(str, Enum):
    """Standard ACP methods."""
    # Session management
    SESSION_CREATE = "session/create"
    SESSION_DESTROY = "session/destroy"
    SESSION_STATUS = "session/status"
    
    # Chat/completion
    CHAT_COMPLETE = "chat/complete"
    CHAT_STREAM = "chat/stream"
    CHAT_CANCEL = "chat/cancel"
    
    # Context
    CONTEXT_SET = "context/set"
    CONTEXT_GET = "context/get"
    CONTEXT_CLEAR = "context/clear"
    
    # Tools
    TOOL_LIST = "tool/list"
    TOOL_INVOKE = "tool/invoke"
    TOOL_RESULT = "tool/result"
    
    # Files
    FILE_READ = "file/read"
    FILE_WRITE = "file/write"
    FILE_LIST = "file/list"
    
    # Notifications
    NOTIFY_PROGRESS = "notify/progress"
    NOTIFY_LOG = "notify/log"
    NOTIFY_COMPLETE = "notify/complete"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ACPRequest:
    """
    ACP request message (JSON-RPC style).
    """
    method: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    params: Dict[str, Any] = field(default_factory=dict)
    
    # ACP extensions
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "jsonrpc": "2.0",
            "method": self.method,
            "id": self.id,
            "params": self.params,
        }
        
        if self.session_id:
            result["session_id"] = self.session_id
        if self.trace_id:
            result["trace_id"] = self.trace_id
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACPRequest":
        return cls(
            method=data["method"],
            id=data.get("id", str(uuid.uuid4())),
            params=data.get("params", {}),
            session_id=data.get("session_id"),
            trace_id=data.get("trace_id"),
        )


@dataclass
class ACPResponse:
    """
    ACP response message.
    """
    id: str
    result: Optional[Any] = None
    error: Optional["ACPError"] = None
    
    # ACP extensions
    trace_id: Optional[str] = None
    duration_ms: Optional[int] = None
    
    @property
    def success(self) -> bool:
        return self.error is None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "jsonrpc": "2.0",
            "id": self.id,
        }
        
        if self.error:
            result["error"] = self.error.to_dict()
        else:
            result["result"] = self.result
        
        if self.trace_id:
            result["trace_id"] = self.trace_id
        if self.duration_ms is not None:
            result["duration_ms"] = self.duration_ms
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACPResponse":
        error = None
        if "error" in data:
            error = ACPError.from_dict(data["error"])
        
        return cls(
            id=data["id"],
            result=data.get("result"),
            error=error,
            trace_id=data.get("trace_id"),
            duration_ms=data.get("duration_ms"),
        )
    
    @classmethod
    def success_response(
        cls,
        request_id: str,
        result: Any,
        trace_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> "ACPResponse":
        return cls(
            id=request_id,
            result=result,
            trace_id=trace_id,
            duration_ms=duration_ms,
        )
    
    @classmethod
    def error_response(
        cls,
        request_id: str,
        code: ACPErrorCode,
        message: str,
        data: Any = None,
    ) -> "ACPResponse":
        return cls(
            id=request_id,
            error=ACPError(code=code, message=message, data=data),
        )


@dataclass
class ACPNotification:
    """
    ACP notification (no response expected).
    """
    method: str
    params: Dict[str, Any] = field(default_factory=dict)
    
    # ACP extensions
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "jsonrpc": "2.0",
            "method": self.method,
            "params": self.params,
        }
        
        if self.session_id:
            result["session_id"] = self.session_id
        if self.trace_id:
            result["trace_id"] = self.trace_id
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACPNotification":
        return cls(
            method=data["method"],
            params=data.get("params", {}),
            session_id=data.get("session_id"),
            trace_id=data.get("trace_id"),
        )


@dataclass
class ACPError:
    """
    ACP error structure.
    """
    code: ACPErrorCode
    message: str
    data: Any = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "code": self.code.value if isinstance(self.code, ACPErrorCode) else self.code,
            "message": self.message,
        }
        if self.data is not None:
            result["data"] = self.data
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACPError":
        code = data["code"]
        try:
            code = ACPErrorCode(code)
        except ValueError:
            pass
        
        return cls(
            code=code,
            message=data["message"],
            data=data.get("data"),
        )


# ============================================================================
# Context Types
# ============================================================================

@dataclass
class ACPContext:
    """
    ACP context for agent sessions.
    """
    # Working directory
    workspace_root: str = ""
    current_file: Optional[str] = None
    
    # Selected content
    selection: Optional[str] = None
    selection_range: Optional[Dict[str, int]] = None
    
    # Environment
    language: str = "python"
    framework: str = ""
    
    # Custom context
    variables: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "workspace_root": self.workspace_root,
            "current_file": self.current_file,
            "selection": self.selection,
            "selection_range": self.selection_range,
            "language": self.language,
            "framework": self.framework,
            "variables": self.variables,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACPContext":
        return cls(
            workspace_root=data.get("workspace_root", ""),
            current_file=data.get("current_file"),
            selection=data.get("selection"),
            selection_range=data.get("selection_range"),
            language=data.get("language", "python"),
            framework=data.get("framework", ""),
            variables=data.get("variables", {}),
        )


@dataclass
class ACPToolDefinition:
    """
    Tool definition for ACP tool list.
    """
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)  # JSON Schema
    
    # Optional
    requires_approval: bool = False
    timeout_seconds: int = 60
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "requires_approval": self.requires_approval,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class ACPChatMessage:
    """
    Chat message in ACP format.
    """
    role: str  # "user", "assistant", "system", "tool"
    content: str
    
    # Optional
    name: Optional[str] = None  # For tool messages
    tool_calls: Optional[List[Dict[str, Any]]] = None  # For assistant tool calls
    tool_call_id: Optional[str] = None  # For tool result messages
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "role": self.role,
            "content": self.content,
        }
        if self.name:
            result["name"] = self.name
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ACPChatMessage":
        return cls(
            role=data["role"],
            content=data.get("content", ""),
            name=data.get("name"),
            tool_calls=data.get("tool_calls"),
            tool_call_id=data.get("tool_call_id"),
        )


# ============================================================================
# Stream Types
# ============================================================================

@dataclass
class ACPStreamChunk:
    """
    Streaming response chunk.
    """
    chunk_id: int
    content: str = ""
    tool_call_chunk: Optional[Dict[str, Any]] = None
    finish_reason: Optional[str] = None  # "stop", "tool_calls", "length"
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "chunk_id": self.chunk_id,
        }
        if self.content:
            result["content"] = self.content
        if self.tool_call_chunk:
            result["tool_call_chunk"] = self.tool_call_chunk
        if self.finish_reason:
            result["finish_reason"] = self.finish_reason
        return result
