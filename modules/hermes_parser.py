"""LADA Hermes Function Calling Parser

Parse Hermes-style XML function calls from LLM responses.

Hermes format:
```
<tool_call>{"name": "function_name", "arguments": {"arg1": "value1"}}</tool_call>
```

Response format:
```
<tool_response>{"name": "function_name", "result": {...}}</tool_response>
```

Features:
- Parse <tool_call> blocks from responses
- Generate <tool_response> blocks
- Chain multiple tool calls
- Compatible with NousResearch Hermes-trained models
- Auto-detect format (OpenAI JSON vs Hermes XML)

Environment variables:
- LADA_FUNCTION_FORMAT: Force format (auto | openai | hermes)

Usage:
    from modules.hermes_parser import HermesParser
    
    parser = HermesParser()
    tool_calls = parser.parse_tool_calls(llm_response)
    
    for call in tool_calls:
        result = execute_tool(call.name, call.arguments)
        parser.add_tool_response(call.name, result)
    
    formatted = parser.format_tool_responses()
"""

from __future__ import annotations

import os
import re
import json
import logging
from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class FunctionFormat(Enum):
    """Function calling format types."""
    AUTO = "auto"
    OPENAI = "openai"
    HERMES = "hermes"


@dataclass
class ToolCall:
    """Represents a parsed tool/function call."""
    name: str
    arguments: Dict[str, Any]
    id: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "id": self.id,
        }
    
    def to_openai_format(self) -> Dict:
        """Convert to OpenAI function call format."""
        return {
            "id": self.id or f"call_{hash(self.name) % 10000}",
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(self.arguments)
            }
        }
    
    def to_hermes_format(self) -> str:
        """Convert to Hermes XML format."""
        return f'<tool_call>{json.dumps({"name": self.name, "arguments": self.arguments})}</tool_call>'


@dataclass
class ToolResponse:
    """Represents a tool execution result."""
    name: str
    result: Any
    success: bool = True
    error: Optional[str] = None
    
    def to_hermes_format(self) -> str:
        """Convert to Hermes XML format."""
        data = {
            "name": self.name,
            "result": self.result if self.success else None,
            "error": self.error,
        }
        return f'<tool_response>{json.dumps(data)}</tool_response>'
    
    def to_openai_format(self, tool_call_id: str) -> Dict:
        """Convert to OpenAI tool message format."""
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps(self.result) if self.success else f"Error: {self.error}"
        }


class HermesParser:
    """Parser for Hermes-style XML function calls."""
    
    # Regex patterns
    TOOL_CALL_PATTERN = re.compile(
        r'<tool_call>\s*({.*?})\s*</tool_call>',
        re.DOTALL
    )
    
    TOOL_RESPONSE_PATTERN = re.compile(
        r'<tool_response>\s*({.*?})\s*</tool_response>',
        re.DOTALL
    )
    
    # Alternative patterns for models that use different tags
    FUNCTION_CALL_PATTERN = re.compile(
        r'<function_call>\s*({.*?})\s*</function_call>',
        re.DOTALL
    )
    
    def __init__(self, format: FunctionFormat = None):
        """Initialize parser.
        
        Args:
            format: Force function format (default: auto-detect from env)
        """
        env_format = os.getenv("LADA_FUNCTION_FORMAT", "auto")
        self.format = format or FunctionFormat(env_format)
        
        self._tool_responses: List[ToolResponse] = []
        
        logger.debug(f"[Hermes] Parser init, format: {self.format.value}")
    
    def detect_format(self, text: str) -> FunctionFormat:
        """Auto-detect function call format in text.
        
        Args:
            text: LLM response text
            
        Returns:
            Detected format
        """
        # Check for Hermes XML tags
        if '<tool_call>' in text or '<function_call>' in text:
            return FunctionFormat.HERMES
        
        # Check for OpenAI JSON function_call structure
        if '"function_call"' in text or '"tool_calls"' in text:
            return FunctionFormat.OPENAI
        
        # Default
        return FunctionFormat.OPENAI
    
    def parse_tool_calls(self, text: str) -> List[ToolCall]:
        """Parse tool calls from LLM response.
        
        Args:
            text: LLM response text
            
        Returns:
            List of parsed ToolCall objects
        """
        if self.format == FunctionFormat.AUTO:
            detected = self.detect_format(text)
        else:
            detected = self.format
        
        if detected == FunctionFormat.HERMES:
            return self._parse_hermes_calls(text)
        else:
            return self._parse_openai_calls(text)
    
    def _parse_hermes_calls(self, text: str) -> List[ToolCall]:
        """Parse Hermes XML tool calls.
        
        Args:
            text: Response text
            
        Returns:
            List of ToolCall
        """
        calls = []
        
        # Try primary pattern
        matches = self.TOOL_CALL_PATTERN.findall(text)
        
        # Try alternative pattern if no matches
        if not matches:
            matches = self.FUNCTION_CALL_PATTERN.findall(text)
        
        for match in matches:
            try:
                data = json.loads(match)
                call = ToolCall(
                    name=data.get("name", ""),
                    arguments=data.get("arguments", data.get("parameters", {})),
                    id=data.get("id"),
                )
                calls.append(call)
                logger.debug(f"[Hermes] Parsed call: {call.name}")
                
            except json.JSONDecodeError as e:
                logger.warning(f"[Hermes] JSON parse error: {e}")
        
        return calls
    
    def _parse_openai_calls(self, text: str) -> List[ToolCall]:
        """Parse OpenAI-style JSON function calls.
        
        Args:
            text: Response text (expected to be JSON)
            
        Returns:
            List of ToolCall
        """
        calls = []
        
        try:
            # Try to parse as JSON
            data = json.loads(text) if isinstance(text, str) else text
            
            # Handle tool_calls array
            if "tool_calls" in data:
                for tc in data["tool_calls"]:
                    func = tc.get("function", {})
                    args = func.get("arguments", "{}")
                    if isinstance(args, str):
                        args = json.loads(args)
                    
                    call = ToolCall(
                        name=func.get("name", ""),
                        arguments=args,
                        id=tc.get("id"),
                    )
                    calls.append(call)
            
            # Handle single function_call
            elif "function_call" in data:
                fc = data["function_call"]
                args = fc.get("arguments", "{}")
                if isinstance(args, str):
                    args = json.loads(args)
                
                call = ToolCall(
                    name=fc.get("name", ""),
                    arguments=args,
                )
                calls.append(call)
                
        except (json.JSONDecodeError, TypeError):
            pass
        
        return calls
    
    def add_tool_response(self, name: str, result: Any, success: bool = True, error: str = None):
        """Add tool execution result.
        
        Args:
            name: Tool name
            result: Execution result
            success: Whether execution succeeded
            error: Error message if failed
        """
        response = ToolResponse(
            name=name,
            result=result,
            success=success,
            error=error,
        )
        self._tool_responses.append(response)
    
    def clear_responses(self):
        """Clear stored tool responses."""
        self._tool_responses.clear()
    
    def format_tool_responses(self, format: FunctionFormat = None) -> str:
        """Format tool responses for LLM context.
        
        Args:
            format: Output format (default: use parser format)
            
        Returns:
            Formatted responses string
        """
        fmt = format or self.format
        if fmt == FunctionFormat.AUTO:
            fmt = FunctionFormat.HERMES
        
        if fmt == FunctionFormat.HERMES:
            return "\n".join(r.to_hermes_format() for r in self._tool_responses)
        else:
            # For OpenAI, return as JSON array
            return json.dumps([
                {"name": r.name, "result": r.result, "success": r.success}
                for r in self._tool_responses
            ])
    
    def get_responses_for_openai(self, tool_calls: List[ToolCall]) -> List[Dict]:
        """Get tool responses in OpenAI message format.
        
        Args:
            tool_calls: Original tool calls (for IDs)
            
        Returns:
            List of tool message dicts
        """
        messages = []
        
        for call, response in zip(tool_calls, self._tool_responses):
            tool_call_id = call.id or f"call_{hash(call.name) % 10000}"
            messages.append(response.to_openai_format(tool_call_id))
        
        return messages
    
    @staticmethod
    def format_tool_call(name: str, arguments: Dict, format: FunctionFormat = FunctionFormat.HERMES) -> str:
        """Format a tool call for injection into prompt.
        
        Args:
            name: Tool name
            arguments: Tool arguments
            format: Output format
            
        Returns:
            Formatted tool call string
        """
        call = ToolCall(name=name, arguments=arguments)
        
        if format == FunctionFormat.HERMES:
            return call.to_hermes_format()
        else:
            return json.dumps(call.to_openai_format())
    
    @staticmethod
    def strip_tool_calls(text: str) -> str:
        """Remove tool call XML tags from text.
        
        Args:
            text: Text with tool calls
            
        Returns:
            Text with tool calls removed
        """
        # Remove tool_call tags
        text = re.sub(r'<tool_call>.*?</tool_call>', '', text, flags=re.DOTALL)
        text = re.sub(r'<function_call>.*?</function_call>', '', text, flags=re.DOTALL)
        
        # Remove tool_response tags  
        text = re.sub(r'<tool_response>.*?</tool_response>', '', text, flags=re.DOTALL)
        
        # Clean up whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        return text.strip()
    
    @staticmethod
    def has_tool_calls(text: str) -> bool:
        """Check if text contains tool calls.
        
        Args:
            text: Text to check
            
        Returns:
            True if tool calls present
        """
        return bool(
            '<tool_call>' in text or 
            '<function_call>' in text or
            '"function_call"' in text or
            '"tool_calls"' in text
        )


# Convenience functions
_parser: Optional[HermesParser] = None


def get_hermes_parser(**kwargs) -> HermesParser:
    """Get or create Hermes parser singleton."""
    global _parser
    if _parser is None:
        _parser = HermesParser(**kwargs)
    return _parser


def parse_tool_calls(text: str) -> List[ToolCall]:
    """Parse tool calls from text (convenience function)."""
    return get_hermes_parser().parse_tool_calls(text)


def has_tool_calls(text: str) -> bool:
    """Check if text has tool calls (convenience function)."""
    return HermesParser.has_tool_calls(text)
