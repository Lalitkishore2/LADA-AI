"""
LADA Skill Source Precedence

Manages skill source priority and per-agent allowlists.

Features:
- Multiple skill sources (builtin, plugins, marketplace, custom)
- Priority-based resolution
- Per-agent skill visibility
- Skill override prevention
"""

import os
import json
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class SkillSource(str, Enum):
    """Where a skill comes from."""
    BUILTIN = "builtin"           # Built into LADA core
    PLUGIN = "plugin"             # From an installed plugin
    MARKETPLACE = "marketplace"   # From marketplace download
    CUSTOM = "custom"             # User-created custom skill
    AGENT = "agent"               # Agent-specific skill


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class SkillEntry:
    """
    A registered skill with source metadata.
    """
    skill_id: str
    name: str
    source: SkillSource
    
    # Origin
    plugin_id: Optional[str] = None
    file_path: Optional[str] = None
    
    # Metadata
    description: str = ""
    version: str = "1.0"
    
    # State
    enabled: bool = True
    priority: int = 0  # Higher = preferred
    registered_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "source": self.source.value,
            "plugin_id": self.plugin_id,
            "file_path": self.file_path,
            "description": self.description,
            "version": self.version,
            "enabled": self.enabled,
            "priority": self.priority,
            "registered_at": self.registered_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillEntry":
        return cls(
            skill_id=data["skill_id"],
            name=data["name"],
            source=SkillSource(data.get("source", "custom")),
            plugin_id=data.get("plugin_id"),
            file_path=data.get("file_path"),
            description=data.get("description", ""),
            version=data.get("version", "1.0"),
            enabled=data.get("enabled", True),
            priority=data.get("priority", 0),
            registered_at=data.get("registered_at", datetime.now().isoformat()),
        )


@dataclass
class SkillPrecedence:
    """
    Precedence configuration for skill sources.
    """
    # Source priority (lower index = higher priority)
    source_order: List[SkillSource] = field(default_factory=lambda: [
        SkillSource.BUILTIN,
        SkillSource.AGENT,
        SkillSource.PLUGIN,
        SkillSource.MARKETPLACE,
        SkillSource.CUSTOM,
    ])
    
    # Override settings
    allow_plugin_override_builtin: bool = False
    allow_custom_override_plugin: bool = True
    
    # Per-agent allowlists/denylists
    agent_allowlists: Dict[str, List[str]] = field(default_factory=dict)  # agent_id -> skill patterns
    agent_denylists: Dict[str, List[str]] = field(default_factory=dict)   # agent_id -> skill patterns
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_order": [s.value for s in self.source_order],
            "allow_plugin_override_builtin": self.allow_plugin_override_builtin,
            "allow_custom_override_plugin": self.allow_custom_override_plugin,
            "agent_allowlists": self.agent_allowlists,
            "agent_denylists": self.agent_denylists,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillPrecedence":
        return cls(
            source_order=[SkillSource(s) for s in data.get("source_order", [
                "builtin", "agent", "plugin", "marketplace", "custom"
            ])],
            allow_plugin_override_builtin=data.get("allow_plugin_override_builtin", False),
            allow_custom_override_plugin=data.get("allow_custom_override_plugin", True),
            agent_allowlists=data.get("agent_allowlists", {}),
            agent_denylists=data.get("agent_denylists", {}),
        )


@dataclass
class SkillResolution:
    """Result of skill resolution."""
    skill: Optional[SkillEntry]
    found: bool
    conflict: bool = False
    conflicting_skills: List[SkillEntry] = field(default_factory=list)
    reason: str = ""


# ============================================================================
# Precedence Manager
# ============================================================================

class SkillPrecedenceManager:
    """
    Manages skill source precedence and visibility.
    
    Features:
    - Priority-based skill resolution
    - Per-agent visibility filtering
    - Conflict detection
    - Override prevention
    """
    
    def __init__(
        self,
        config_file: Optional[str] = None,
        skills_dir: Optional[str] = None,
    ):
        self._config_file = Path(config_file or os.getenv(
            "LADA_SKILL_PRECEDENCE_FILE",
            "config/skill_precedence.json"
        ))
        self._skills_dir = Path(skills_dir or os.getenv("LADA_SKILLS_DIR", "skills"))
        
        self._precedence = SkillPrecedence()
        self._skills: Dict[str, List[SkillEntry]] = {}  # skill_id -> list of entries (multiple sources)
        self._lock = threading.RLock()
        
        # Load config
        self._load_config()
        
        logger.info("[SkillPrecedenceManager] Initialized")
    
    def register_skill(self, skill: SkillEntry) -> bool:
        """
        Register a skill entry.
        
        Multiple entries can exist for the same skill_id from different sources.
        Resolution picks the highest-priority one.
        """
        with self._lock:
            if skill.skill_id not in self._skills:
                self._skills[skill.skill_id] = []
            
            # Check for duplicate from same source
            existing = [
                s for s in self._skills[skill.skill_id]
                if s.source == skill.source and s.plugin_id == skill.plugin_id
            ]
            if existing:
                # Update existing
                self._skills[skill.skill_id].remove(existing[0])
            
            self._skills[skill.skill_id].append(skill)
            return True
    
    def unregister_skill(
        self,
        skill_id: str,
        source: Optional[SkillSource] = None,
        plugin_id: Optional[str] = None,
    ) -> bool:
        """
        Unregister a skill entry.
        
        If source/plugin_id specified, removes only that entry.
        Otherwise removes all entries for skill_id.
        """
        with self._lock:
            if skill_id not in self._skills:
                return False
            
            if source or plugin_id:
                original_count = len(self._skills[skill_id])
                self._skills[skill_id] = [
                    s for s in self._skills[skill_id]
                    if not (
                        (source is None or s.source == source) and
                        (plugin_id is None or s.plugin_id == plugin_id)
                    )
                ]
                return len(self._skills[skill_id]) < original_count
            else:
                del self._skills[skill_id]
                return True
    
    def resolve_skill(
        self,
        skill_id: str,
        agent_id: Optional[str] = None,
    ) -> SkillResolution:
        """
        Resolve which skill implementation to use.
        
        Considers:
        - Source precedence
        - Per-agent visibility
        - Override rules
        """
        with self._lock:
            if skill_id not in self._skills:
                return SkillResolution(
                    skill=None,
                    found=False,
                    reason=f"Skill '{skill_id}' not found",
                )
            
            entries = self._skills[skill_id]
            
            # Filter by agent visibility
            if agent_id:
                entries = self._filter_for_agent(entries, agent_id)
            
            # Filter enabled only
            entries = [e for e in entries if e.enabled]
            
            if not entries:
                return SkillResolution(
                    skill=None,
                    found=False,
                    reason=f"No enabled skill entries for '{skill_id}'",
                )
            
            # Check for conflicts
            conflict = len(entries) > 1
            
            # Sort by precedence
            sorted_entries = self._sort_by_precedence(entries)
            
            # Apply override rules
            best = sorted_entries[0]
            if conflict:
                best = self._apply_override_rules(sorted_entries)
            
            return SkillResolution(
                skill=best,
                found=True,
                conflict=conflict,
                conflicting_skills=sorted_entries if conflict else [],
                reason="Resolved by precedence" if conflict else "Unique match",
            )
    
    def list_skills(
        self,
        agent_id: Optional[str] = None,
        source: Optional[SkillSource] = None,
        enabled_only: bool = True,
    ) -> List[SkillEntry]:
        """
        List all skills, optionally filtered.
        
        Returns resolved skills (one per skill_id).
        """
        with self._lock:
            result = []
            
            for skill_id in self._skills:
                resolution = self.resolve_skill(skill_id, agent_id)
                if resolution.found and resolution.skill:
                    skill = resolution.skill
                    
                    if source and skill.source != source:
                        continue
                    if enabled_only and not skill.enabled:
                        continue
                    
                    result.append(skill)
            
            return result
    
    def list_all_entries(
        self,
        skill_id: Optional[str] = None,
    ) -> Dict[str, List[SkillEntry]]:
        """List all skill entries (including conflicts)."""
        with self._lock:
            if skill_id:
                return {skill_id: self._skills.get(skill_id, [])}
            return dict(self._skills)
    
    def get_skills_for_agent(
        self,
        agent_id: str,
    ) -> List[SkillEntry]:
        """Get all skills visible to an agent."""
        return self.list_skills(agent_id=agent_id, enabled_only=True)
    
    def is_skill_allowed_for_agent(
        self,
        skill_id: str,
        agent_id: str,
    ) -> Tuple[bool, str]:
        """Check if a skill is allowed for an agent."""
        with self._lock:
            # Check denylist first
            if agent_id in self._precedence.agent_denylists:
                for pattern in self._precedence.agent_denylists[agent_id]:
                    if self._pattern_matches(pattern, skill_id):
                        return False, f"Skill '{skill_id}' is denied for agent '{agent_id}'"
            
            # Check allowlist
            if agent_id in self._precedence.agent_allowlists:
                for pattern in self._precedence.agent_allowlists[agent_id]:
                    if self._pattern_matches(pattern, skill_id):
                        return True, "Skill is in agent allowlist"
                # Has allowlist but skill not in it
                return False, f"Skill '{skill_id}' not in allowlist for agent '{agent_id}'"
            
            # No specific rules - allow
            return True, "No agent-specific restrictions"
    
    def set_agent_allowlist(
        self,
        agent_id: str,
        patterns: List[str],
    ) -> None:
        """Set allowlist for an agent."""
        with self._lock:
            self._precedence.agent_allowlists[agent_id] = patterns
            self._save_config()
    
    def set_agent_denylist(
        self,
        agent_id: str,
        patterns: List[str],
    ) -> None:
        """Set denylist for an agent."""
        with self._lock:
            self._precedence.agent_denylists[agent_id] = patterns
            self._save_config()
    
    def set_source_order(self, order: List[SkillSource]) -> None:
        """Set source precedence order."""
        with self._lock:
            self._precedence.source_order = order
            self._save_config()
    
    def get_precedence(self) -> SkillPrecedence:
        """Get current precedence config."""
        with self._lock:
            return self._precedence
    
    def set_precedence(self, precedence: SkillPrecedence) -> None:
        """Set entire precedence config."""
        with self._lock:
            self._precedence = precedence
            self._save_config()
    
    def _filter_for_agent(
        self,
        entries: List[SkillEntry],
        agent_id: str,
    ) -> List[SkillEntry]:
        """Filter entries based on agent visibility rules."""
        result = []
        for entry in entries:
            allowed, _ = self.is_skill_allowed_for_agent(entry.skill_id, agent_id)
            if allowed:
                result.append(entry)
        return result
    
    def _sort_by_precedence(self, entries: List[SkillEntry]) -> List[SkillEntry]:
        """Sort entries by source precedence and priority."""
        def sort_key(entry: SkillEntry) -> Tuple[int, int]:
            try:
                source_idx = self._precedence.source_order.index(entry.source)
            except ValueError:
                source_idx = len(self._precedence.source_order)
            
            # Lower source index = higher precedence
            # Higher priority = higher precedence (negate for sort)
            return (source_idx, -entry.priority)
        
        return sorted(entries, key=sort_key)
    
    def _apply_override_rules(self, sorted_entries: List[SkillEntry]) -> SkillEntry:
        """Apply override rules to pick best entry."""
        best = sorted_entries[0]
        
        # Check if plugin trying to override builtin
        if not self._precedence.allow_plugin_override_builtin:
            builtin_entries = [e for e in sorted_entries if e.source == SkillSource.BUILTIN]
            if builtin_entries and best.source in (SkillSource.PLUGIN, SkillSource.MARKETPLACE):
                # Force builtin to win
                return builtin_entries[0]
        
        # Check if custom trying to override plugin
        if not self._precedence.allow_custom_override_plugin:
            plugin_entries = [e for e in sorted_entries if e.source == SkillSource.PLUGIN]
            if plugin_entries and best.source == SkillSource.CUSTOM:
                # Force plugin to win
                return plugin_entries[0]
        
        return best
    
    def _pattern_matches(self, pattern: str, skill_id: str) -> bool:
        """Check if a glob pattern matches a skill ID."""
        import fnmatch
        return fnmatch.fnmatch(skill_id, pattern)
    
    def _load_config(self):
        """Load config from disk."""
        if self._config_file.exists():
            try:
                with open(self._config_file, 'r') as f:
                    data = json.load(f)
                self._precedence = SkillPrecedence.from_dict(data)
            except Exception as e:
                logger.warning(f"[SkillPrecedenceManager] Failed to load config: {e}")
    
    def _save_config(self):
        """Save config to disk."""
        try:
            self._config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config_file, 'w') as f:
                json.dump(self._precedence.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"[SkillPrecedenceManager] Failed to save config: {e}")


# ============================================================================
# Singleton
# ============================================================================

_manager_instance: Optional[SkillPrecedenceManager] = None
_manager_lock = threading.Lock()


def get_precedence_manager() -> SkillPrecedenceManager:
    """Get singleton SkillPrecedenceManager instance."""
    global _manager_instance
    if _manager_instance is None:
        with _manager_lock:
            if _manager_instance is None:
                _manager_instance = SkillPrecedenceManager()
    return _manager_instance
