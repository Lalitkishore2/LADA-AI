"""
LADA Agent Registry

Provides multi-agent support with:
- Agent configuration model (workspace, state, capabilities)
- Per-agent skill allowlists
- Agent lifecycle management
- Persistent agent configurations

Built on multi-agent routing patterns.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Default directories
DEFAULT_AGENTS_DIR = os.getenv("LADA_AGENTS_DIR", "data/agents")
DEFAULT_AGENT_ID = "default"


class AgentStatus(str, Enum):
    """Agent lifecycle status."""
    INACTIVE = "inactive"      # Not started
    STARTING = "starting"      # Initializing
    ACTIVE = "active"          # Running and accepting requests
    PAUSED = "paused"          # Temporarily suspended
    STOPPING = "stopping"      # Shutting down
    ERROR = "error"            # Failed state


@dataclass
class AgentCapabilities:
    """
    Agent capability declarations.
    
    Defines what an agent can do and what tools/skills it has access to.
    """
    # Core capabilities
    can_chat: bool = True
    can_execute_commands: bool = True
    can_use_tools: bool = True
    can_browse: bool = False
    can_control_desktop: bool = False
    
    # Skill restrictions
    allowed_skills: Set[str] = field(default_factory=set)  # Empty = all allowed
    denied_skills: Set[str] = field(default_factory=set)   # Explicit denials
    
    # Tool restrictions
    allowed_tools: Set[str] = field(default_factory=set)   # Empty = all allowed
    denied_tools: Set[str] = field(default_factory=set)    # Explicit denials
    
    # Resource limits
    max_concurrent_tasks: int = 5
    max_memory_mb: int = 512
    max_session_duration_seconds: int = 3600
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "can_chat": self.can_chat,
            "can_execute_commands": self.can_execute_commands,
            "can_use_tools": self.can_use_tools,
            "can_browse": self.can_browse,
            "can_control_desktop": self.can_control_desktop,
            "allowed_skills": list(self.allowed_skills),
            "denied_skills": list(self.denied_skills),
            "allowed_tools": list(self.allowed_tools),
            "denied_tools": list(self.denied_tools),
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "max_memory_mb": self.max_memory_mb,
            "max_session_duration_seconds": self.max_session_duration_seconds,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentCapabilities":
        return cls(
            can_chat=bool(data.get("can_chat", True)),
            can_execute_commands=bool(data.get("can_execute_commands", True)),
            can_use_tools=bool(data.get("can_use_tools", True)),
            can_browse=bool(data.get("can_browse", False)),
            can_control_desktop=bool(data.get("can_control_desktop", False)),
            allowed_skills=set(data.get("allowed_skills", [])),
            denied_skills=set(data.get("denied_skills", [])),
            allowed_tools=set(data.get("allowed_tools", [])),
            denied_tools=set(data.get("denied_tools", [])),
            max_concurrent_tasks=int(data.get("max_concurrent_tasks", 5)),
            max_memory_mb=int(data.get("max_memory_mb", 512)),
            max_session_duration_seconds=int(data.get("max_session_duration_seconds", 3600)),
        )
    
    def is_skill_allowed(self, skill_name: str) -> bool:
        """Check if a skill is allowed for this agent."""
        if skill_name in self.denied_skills:
            return False
        if self.allowed_skills and skill_name not in self.allowed_skills:
            return False
        return True
    
    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed for this agent."""
        if tool_name in self.denied_tools:
            return False
        if self.allowed_tools and tool_name not in self.allowed_tools:
            return False
        return True


@dataclass
class AgentConfig:
    """
    Configuration for a LADA agent instance.
    
    Each agent has isolated:
    - Workspace directory for file operations
    - State directory for persistent data
    - Session namespace
    - Skill/tool allowlist
    """
    agent_id: str
    name: str = ""
    description: str = ""
    
    # Isolation boundaries
    workspace_root: str = ""        # Root for agent file operations
    state_dir: str = ""             # Agent-specific state storage
    
    # Runtime configuration
    capabilities: AgentCapabilities = field(default_factory=AgentCapabilities)
    status: AgentStatus = AgentStatus.INACTIVE
    
    # Model preferences
    default_model: Optional[str] = None
    model_tier: str = "balanced"
    
    # Metadata
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    updated_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Runtime state (not persisted)
    active_sessions: Set[str] = field(default_factory=set)
    active_tasks: Set[str] = field(default_factory=set)
    
    def __post_init__(self):
        if not self.name:
            self.name = self.agent_id
        if not self.workspace_root:
            self.workspace_root = os.path.join(DEFAULT_AGENTS_DIR, self.agent_id, "workspace")
        if not self.state_dir:
            self.state_dir = os.path.join(DEFAULT_AGENTS_DIR, self.agent_id, "state")
    
    def to_dict(self, include_runtime: bool = False) -> Dict[str, Any]:
        """Serialize agent config to dictionary."""
        result = {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "workspace_root": self.workspace_root,
            "state_dir": self.state_dir,
            "capabilities": self.capabilities.to_dict(),
            "status": self.status.value,
            "default_model": self.default_model,
            "model_tier": self.model_tier,
            "created_at_ms": self.created_at_ms,
            "updated_at_ms": self.updated_at_ms,
            "metadata": self.metadata,
        }
        if include_runtime:
            result["active_sessions"] = list(self.active_sessions)
            result["active_tasks"] = list(self.active_tasks)
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentConfig":
        """Deserialize agent config from dictionary."""
        status_val = data.get("status", "inactive")
        try:
            status = AgentStatus(status_val)
        except ValueError:
            status = AgentStatus.INACTIVE
        
        caps_data = data.get("capabilities", {})
        capabilities = AgentCapabilities.from_dict(caps_data) if caps_data else AgentCapabilities()
        
        return cls(
            agent_id=str(data.get("agent_id", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            workspace_root=str(data.get("workspace_root", "")),
            state_dir=str(data.get("state_dir", "")),
            capabilities=capabilities,
            status=status,
            default_model=data.get("default_model"),
            model_tier=str(data.get("model_tier", "balanced")),
            created_at_ms=int(data.get("created_at_ms", int(time.time() * 1000))),
            updated_at_ms=int(data.get("updated_at_ms", int(time.time() * 1000))),
            metadata=dict(data.get("metadata", {})),
        )
    
    def ensure_directories(self) -> bool:
        """Create workspace and state directories if they don't exist."""
        try:
            Path(self.workspace_root).mkdir(parents=True, exist_ok=True)
            Path(self.state_dir).mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"Failed to create agent directories for {self.agent_id}: {e}")
            return False


class AgentRegistry:
    """
    Registry for managing multiple LADA agents.
    
    Provides:
    - Agent registration and lookup
    - Persistent agent configurations
    - Agent lifecycle management
    - Statistics and monitoring
    """
    
    def __init__(self, agents_dir: str = DEFAULT_AGENTS_DIR):
        self._agents: Dict[str, AgentConfig] = {}
        self._agents_dir = agents_dir
        self._lock = threading.RLock()
        self._initialized = False
        
        # Ensure default agent exists
        self._ensure_default_agent()
    
    def _ensure_default_agent(self) -> None:
        """Ensure the default agent always exists."""
        if DEFAULT_AGENT_ID not in self._agents:
            default_agent = AgentConfig(
                agent_id=DEFAULT_AGENT_ID,
                name="Default Agent",
                description="The default LADA agent with full capabilities",
                capabilities=AgentCapabilities(
                    can_browse=True,
                    can_control_desktop=True,
                ),
            )
            default_agent.status = AgentStatus.ACTIVE
            self._agents[DEFAULT_AGENT_ID] = default_agent
    
    def load_from_disk(self) -> int:
        """
        Load all agent configurations from disk.
        
        Returns number of agents loaded.
        """
        with self._lock:
            agents_path = Path(self._agents_dir)
            if not agents_path.exists():
                logger.info(f"Agents directory doesn't exist: {self._agents_dir}")
                self._initialized = True
                return 0
            
            loaded = 0
            for agent_dir in agents_path.iterdir():
                if not agent_dir.is_dir():
                    continue
                
                config_file = agent_dir / "config.json"
                if not config_file.exists():
                    continue
                
                try:
                    with open(config_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    agent = AgentConfig.from_dict(data)
                    agent.status = AgentStatus.INACTIVE  # Reset to inactive on load
                    self._agents[agent.agent_id] = agent
                    loaded += 1
                    logger.debug(f"Loaded agent config: {agent.agent_id}")
                except Exception as e:
                    logger.error(f"Failed to load agent config from {config_file}: {e}")
            
            self._ensure_default_agent()
            self._initialized = True
            logger.info(f"Loaded {loaded} agent configurations")
            return loaded
    
    def save_to_disk(self) -> int:
        """
        Save all agent configurations to disk.
        
        Returns number of agents saved.
        """
        with self._lock:
            Path(self._agents_dir).mkdir(parents=True, exist_ok=True)
            
            saved = 0
            for agent_id, agent in self._agents.items():
                agent_dir = Path(self._agents_dir) / agent_id
                agent_dir.mkdir(parents=True, exist_ok=True)
                
                config_file = agent_dir / "config.json"
                try:
                    with open(config_file, "w", encoding="utf-8") as f:
                        json.dump(agent.to_dict(), f, indent=2)
                    saved += 1
                except Exception as e:
                    logger.error(f"Failed to save agent config for {agent_id}: {e}")
            
            return saved
    
    def register(self, agent: AgentConfig) -> bool:
        """
        Register a new agent or update existing.
        
        Returns True if successful.
        """
        with self._lock:
            if not agent.agent_id:
                logger.error("Cannot register agent without agent_id")
                return False
            
            agent.updated_at_ms = int(time.time() * 1000)
            self._agents[agent.agent_id] = agent
            
            # Ensure directories exist
            agent.ensure_directories()
            
            logger.info(f"Registered agent: {agent.agent_id}")
            return True
    
    def unregister(self, agent_id: str) -> bool:
        """
        Unregister an agent.
        
        Returns True if agent was found and removed.
        """
        with self._lock:
            if agent_id == DEFAULT_AGENT_ID:
                logger.warning("Cannot unregister the default agent")
                return False
            
            if agent_id not in self._agents:
                return False
            
            agent = self._agents.pop(agent_id)
            logger.info(f"Unregistered agent: {agent_id}")
            return True
    
    def get(self, agent_id: str) -> Optional[AgentConfig]:
        """Get agent by ID."""
        with self._lock:
            return self._agents.get(agent_id)
    
    def get_or_default(self, agent_id: Optional[str]) -> AgentConfig:
        """Get agent by ID, or return default agent."""
        with self._lock:
            if agent_id and agent_id in self._agents:
                return self._agents[agent_id]
            return self._agents[DEFAULT_AGENT_ID]
    
    def list_all(self) -> List[AgentConfig]:
        """List all registered agents."""
        with self._lock:
            return list(self._agents.values())
    
    def list_active(self) -> List[AgentConfig]:
        """List all active agents."""
        with self._lock:
            return [a for a in self._agents.values() if a.status == AgentStatus.ACTIVE]
    
    def set_status(self, agent_id: str, status: AgentStatus) -> bool:
        """Update agent status."""
        with self._lock:
            agent = self._agents.get(agent_id)
            if not agent:
                return False
            
            old_status = agent.status
            agent.status = status
            agent.updated_at_ms = int(time.time() * 1000)
            
            logger.info(f"Agent {agent_id} status: {old_status.value} -> {status.value}")
            return True
    
    def add_session(self, agent_id: str, session_id: str) -> bool:
        """Track a session as belonging to an agent."""
        with self._lock:
            agent = self._agents.get(agent_id)
            if not agent:
                return False
            
            agent.active_sessions.add(session_id)
            return True
    
    def remove_session(self, agent_id: str, session_id: str) -> bool:
        """Remove session from agent tracking."""
        with self._lock:
            agent = self._agents.get(agent_id)
            if not agent:
                return False
            
            agent.active_sessions.discard(session_id)
            return True
    
    def get_agent_for_session(self, session_id: str) -> Optional[AgentConfig]:
        """Find agent that owns a session."""
        with self._lock:
            for agent in self._agents.values():
                if session_id in agent.active_sessions:
                    return agent
            return None
    
    def count(self) -> int:
        """Get total agent count."""
        with self._lock:
            return len(self._agents)
    
    def count_active(self) -> int:
        """Get active agent count."""
        with self._lock:
            return sum(1 for a in self._agents.values() if a.status == AgentStatus.ACTIVE)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        with self._lock:
            return {
                "total_agents": len(self._agents),
                "active_agents": sum(1 for a in self._agents.values() if a.status == AgentStatus.ACTIVE),
                "total_sessions": sum(len(a.active_sessions) for a in self._agents.values()),
                "total_tasks": sum(len(a.active_tasks) for a in self._agents.values()),
                "agents": [
                    {
                        "agent_id": a.agent_id,
                        "name": a.name,
                        "status": a.status.value,
                        "sessions": len(a.active_sessions),
                        "tasks": len(a.active_tasks),
                    }
                    for a in self._agents.values()
                ],
            }


# Singleton registry instance
_registry: Optional[AgentRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> AgentRegistry:
    """Get the singleton agent registry."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = AgentRegistry()
                _registry.load_from_disk()
    return _registry


def register_agent(agent: AgentConfig) -> bool:
    """Convenience function to register an agent."""
    return get_registry().register(agent)


def get_agent(agent_id: str) -> Optional[AgentConfig]:
    """Convenience function to get an agent."""
    return get_registry().get(agent_id)


def list_agents() -> List[AgentConfig]:
    """Convenience function to list all agents."""
    return get_registry().list_all()
