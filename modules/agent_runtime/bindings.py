"""
LADA Agent Bindings

Maps channels and peers to specific agents for routing.
Supports:
- Channel type -> agent bindings (e.g., telegram -> agent_1)
- Peer -> agent bindings (e.g., user@telegram:12345 -> agent_2)
- Default agent fallback
- Binding persistence

Built on channel binding patterns.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from modules.agent_runtime.agent_registry import (
    AgentConfig,
    get_registry,
    DEFAULT_AGENT_ID,
)

logger = logging.getLogger(__name__)

# Default bindings file
DEFAULT_BINDINGS_FILE = os.getenv("LADA_AGENT_BINDINGS_FILE", "data/agent_bindings.json")


@dataclass
class ChannelBinding:
    """
    Binding rule for routing a channel to an agent.
    """
    binding_id: str
    channel_type: str              # e.g., "telegram", "discord", "gui", "api"
    peer_pattern: str = "*"        # Peer ID pattern (supports * wildcard)
    agent_id: str = DEFAULT_AGENT_ID
    priority: int = 0              # Higher priority = checked first
    enabled: bool = True
    description: str = ""
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def matches(self, channel_type: str, peer_id: str) -> bool:
        """
        Check if this binding matches the given channel and peer.
        """
        if not self.enabled:
            return False
        
        if self.channel_type != "*" and self.channel_type.lower() != channel_type.lower():
            return False
        
        if self.peer_pattern == "*":
            return True
        
        # Simple pattern matching
        if "*" in self.peer_pattern:
            # Wildcard matching
            pattern = self.peer_pattern.lower()
            peer = peer_id.lower()
            
            if pattern.startswith("*") and pattern.endswith("*"):
                # *substring*
                return pattern[1:-1] in peer
            elif pattern.startswith("*"):
                # *suffix
                return peer.endswith(pattern[1:])
            elif pattern.endswith("*"):
                # prefix*
                return peer.startswith(pattern[:-1])
            else:
                # exact match with wildcards in middle not supported
                return pattern == peer
        else:
            return self.peer_pattern.lower() == peer_id.lower()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "binding_id": self.binding_id,
            "channel_type": self.channel_type,
            "peer_pattern": self.peer_pattern,
            "agent_id": self.agent_id,
            "priority": self.priority,
            "enabled": self.enabled,
            "description": self.description,
            "created_at_ms": self.created_at_ms,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChannelBinding":
        return cls(
            binding_id=str(data.get("binding_id", "")),
            channel_type=str(data.get("channel_type", "*")),
            peer_pattern=str(data.get("peer_pattern", "*")),
            agent_id=str(data.get("agent_id", DEFAULT_AGENT_ID)),
            priority=int(data.get("priority", 0)),
            enabled=bool(data.get("enabled", True)),
            description=str(data.get("description", "")),
            created_at_ms=int(data.get("created_at_ms", int(time.time() * 1000))),
            metadata=dict(data.get("metadata", {})),
        )


class AgentBindings:
    """
    Manages channel-to-agent bindings for routing.
    
    Resolution order:
    1. Exact peer match (highest priority first)
    2. Pattern match (highest priority first)
    3. Channel type default
    4. Global default agent
    """
    
    def __init__(self, bindings_file: str = DEFAULT_BINDINGS_FILE):
        self._bindings: Dict[str, ChannelBinding] = {}
        self._bindings_file = bindings_file
        self._lock = threading.RLock()
        
        # Cache for resolved bindings
        self._resolution_cache: Dict[Tuple[str, str], str] = {}
        self._cache_ttl_seconds = 60
        self._cache_timestamps: Dict[Tuple[str, str], float] = {}
    
    def load_from_disk(self) -> int:
        """
        Load bindings from disk.
        
        Returns number of bindings loaded.
        """
        with self._lock:
            path = Path(self._bindings_file)
            if not path.exists():
                logger.debug(f"Bindings file doesn't exist: {self._bindings_file}")
                return 0
            
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                bindings_list = data.get("bindings", [])
                for binding_data in bindings_list:
                    binding = ChannelBinding.from_dict(binding_data)
                    if binding.binding_id:
                        self._bindings[binding.binding_id] = binding
                
                self._resolution_cache.clear()
                logger.info(f"Loaded {len(self._bindings)} agent bindings")
                return len(self._bindings)
            except Exception as e:
                logger.error(f"Failed to load bindings from {self._bindings_file}: {e}")
                return 0
    
    def save_to_disk(self) -> bool:
        """
        Save bindings to disk.
        
        Returns True if successful.
        """
        with self._lock:
            path = Path(self._bindings_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            try:
                data = {
                    "version": "1.0",
                    "saved_at_ms": int(time.time() * 1000),
                    "bindings": [b.to_dict() for b in self._bindings.values()],
                }
                
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                
                logger.debug(f"Saved {len(self._bindings)} agent bindings")
                return True
            except Exception as e:
                logger.error(f"Failed to save bindings to {self._bindings_file}: {e}")
                return False
    
    def add_binding(self, binding: ChannelBinding) -> bool:
        """
        Add or update a binding.
        
        Returns True if successful.
        """
        with self._lock:
            if not binding.binding_id:
                logger.error("Cannot add binding without binding_id")
                return False
            
            self._bindings[binding.binding_id] = binding
            self._resolution_cache.clear()
            
            logger.debug(f"Added binding {binding.binding_id}: {binding.channel_type}/{binding.peer_pattern} -> {binding.agent_id}")
            return True
    
    def remove_binding(self, binding_id: str) -> bool:
        """
        Remove a binding.
        
        Returns True if binding was found and removed.
        """
        with self._lock:
            if binding_id not in self._bindings:
                return False
            
            del self._bindings[binding_id]
            self._resolution_cache.clear()
            
            logger.debug(f"Removed binding {binding_id}")
            return True
    
    def get_binding(self, binding_id: str) -> Optional[ChannelBinding]:
        """Get binding by ID."""
        with self._lock:
            return self._bindings.get(binding_id)
    
    def list_bindings(self) -> List[ChannelBinding]:
        """List all bindings."""
        with self._lock:
            return list(self._bindings.values())
    
    def list_bindings_for_channel(self, channel_type: str) -> List[ChannelBinding]:
        """List bindings for a specific channel type."""
        with self._lock:
            return [
                b for b in self._bindings.values()
                if b.channel_type == "*" or b.channel_type.lower() == channel_type.lower()
            ]
    
    def resolve_agent(self, channel_type: str, peer_id: str) -> str:
        """
        Resolve channel and peer to agent ID.
        
        Returns agent ID for routing. Falls back to default agent.
        """
        cache_key = (channel_type.lower(), peer_id.lower())
        
        with self._lock:
            # Check cache
            if cache_key in self._resolution_cache:
                cached_time = self._cache_timestamps.get(cache_key, 0)
                if time.time() - cached_time < self._cache_ttl_seconds:
                    return self._resolution_cache[cache_key]
            
            # Find matching bindings
            matching = []
            for binding in self._bindings.values():
                if binding.matches(channel_type, peer_id):
                    matching.append(binding)
            
            # Sort by priority (highest first)
            matching.sort(key=lambda b: (-b.priority, b.binding_id))
            
            if matching:
                agent_id = matching[0].agent_id
            else:
                agent_id = DEFAULT_AGENT_ID
            
            # Verify agent exists
            registry = get_registry()
            if not registry.get(agent_id):
                logger.warning(f"Bound agent {agent_id} not found, using default")
                agent_id = DEFAULT_AGENT_ID
            
            # Cache result
            self._resolution_cache[cache_key] = agent_id
            self._cache_timestamps[cache_key] = time.time()
            
            return agent_id
    
    def resolve_agent_config(self, channel_type: str, peer_id: str) -> AgentConfig:
        """
        Resolve channel and peer to agent configuration.
        
        Returns AgentConfig for routing.
        """
        agent_id = self.resolve_agent(channel_type, peer_id)
        registry = get_registry()
        return registry.get_or_default(agent_id)
    
    def bind_peer_to_agent(
        self,
        channel_type: str,
        peer_id: str,
        agent_id: str,
        priority: int = 100,
        description: str = "",
    ) -> str:
        """
        Convenience method to create a peer-specific binding.
        
        Returns the binding ID.
        """
        import uuid
        binding_id = f"peer_{uuid.uuid4().hex[:12]}"
        
        binding = ChannelBinding(
            binding_id=binding_id,
            channel_type=channel_type,
            peer_pattern=peer_id,
            agent_id=agent_id,
            priority=priority,
            description=description or f"Peer binding for {peer_id}",
        )
        
        self.add_binding(binding)
        return binding_id
    
    def bind_channel_to_agent(
        self,
        channel_type: str,
        agent_id: str,
        priority: int = 50,
        description: str = "",
    ) -> str:
        """
        Convenience method to create a channel-wide binding.
        
        Returns the binding ID.
        """
        import uuid
        binding_id = f"channel_{channel_type}_{uuid.uuid4().hex[:8]}"
        
        binding = ChannelBinding(
            binding_id=binding_id,
            channel_type=channel_type,
            peer_pattern="*",
            agent_id=agent_id,
            priority=priority,
            description=description or f"Channel binding for {channel_type}",
        )
        
        self.add_binding(binding)
        return binding_id
    
    def clear_cache(self) -> None:
        """Clear the resolution cache."""
        with self._lock:
            self._resolution_cache.clear()
            self._cache_timestamps.clear()
    
    def count(self) -> int:
        """Get total binding count."""
        with self._lock:
            return len(self._bindings)


# Singleton bindings instance
_bindings: Optional[AgentBindings] = None
_bindings_lock = threading.Lock()


def get_bindings() -> AgentBindings:
    """Get the singleton agent bindings instance."""
    global _bindings
    if _bindings is None:
        with _bindings_lock:
            if _bindings is None:
                _bindings = AgentBindings()
                _bindings.load_from_disk()
    return _bindings


def resolve_agent_for_channel(channel_type: str, peer_id: str) -> AgentConfig:
    """Convenience function to resolve agent for a channel."""
    return get_bindings().resolve_agent_config(channel_type, peer_id)
