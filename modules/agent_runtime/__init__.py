"""
LADA Agent Runtime - Multi-agent isolation and routing.

This package provides:
- Agent configuration and lifecycle management
- Per-agent workspace and state isolation
- Channel-to-agent routing and bindings
- Skill visibility controls per agent
"""

from modules.agent_runtime.agent_registry import (
    AgentConfig,
    AgentCapabilities,
    AgentStatus,
    AgentRegistry,
    get_registry,
    register_agent,
    get_agent,
    list_agents,
    DEFAULT_AGENT_ID,
)

from modules.agent_runtime.bindings import (
    ChannelBinding,
    AgentBindings,
    get_bindings,
    resolve_agent_for_channel,
)

__all__ = [
    # Agent registry
    "AgentConfig",
    "AgentCapabilities",
    "AgentStatus",
    "AgentRegistry",
    "get_registry",
    "register_agent",
    "get_agent",
    "list_agents",
    "DEFAULT_AGENT_ID",
    # Bindings
    "ChannelBinding",
    "AgentBindings",
    "get_bindings",
    "resolve_agent_for_channel",
]
