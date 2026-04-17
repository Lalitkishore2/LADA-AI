"""
LADA Plugin Policy Engine

Enforces allow/deny policies for plugins and skills.

Features:
- Glob pattern matching for plugin IDs
- Default allow/deny modes
- Agent-specific overrides
- Priority-based rule evaluation
"""

import os
import re
import json
import fnmatch
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

from modules.plugins.trust import TrustLevel, TrustSource, RiskLevel

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class PolicyAction(str, Enum):
    """What to do when a rule matches."""
    ALLOW = "allow"
    DENY = "deny"
    AUDIT = "audit"      # Allow but log
    PROMPT = "prompt"    # Ask user


class PolicyMode(str, Enum):
    """Default policy mode when no rules match."""
    ALLOW_ALL = "allow_all"   # Permissive - allow unless denied
    DENY_ALL = "deny_all"     # Restrictive - deny unless allowed


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class PolicyRule:
    """
    A single policy rule.
    """
    rule_id: str
    pattern: str              # Glob pattern for plugin IDs
    action: PolicyAction
    priority: int = 0         # Higher priority evaluated first
    
    # Conditions
    trust_levels: List[TrustLevel] = field(default_factory=list)  # If set, only match these
    sources: List[TrustSource] = field(default_factory=list)      # If set, only match these
    max_risk_level: Optional[RiskLevel] = None                    # Block above this
    
    # Scope
    agent_ids: List[str] = field(default_factory=list)  # If set, only apply to these agents
    
    # Metadata
    reason: str = ""
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def matches(
        self,
        plugin_id: str,
        trust_level: Optional[TrustLevel] = None,
        source: Optional[TrustSource] = None,
        risk_level: Optional[RiskLevel] = None,
        agent_id: Optional[str] = None,
    ) -> bool:
        """Check if this rule matches the given plugin."""
        if not self.enabled:
            return False
        
        # Pattern match
        if not fnmatch.fnmatch(plugin_id, self.pattern):
            return False
        
        # Trust level filter
        if self.trust_levels and trust_level and trust_level not in self.trust_levels:
            return False
        
        # Source filter
        if self.sources and source and source not in self.sources:
            return False
        
        # Risk level filter
        if self.max_risk_level and risk_level:
            risk_order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
            if risk_order.index(risk_level) > risk_order.index(self.max_risk_level):
                return False
        
        # Agent filter
        if self.agent_ids and agent_id not in self.agent_ids:
            return False
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "pattern": self.pattern,
            "action": self.action.value,
            "priority": self.priority,
            "trust_levels": [t.value for t in self.trust_levels],
            "sources": [s.value for s in self.sources],
            "max_risk_level": self.max_risk_level.value if self.max_risk_level else None,
            "agent_ids": self.agent_ids,
            "reason": self.reason,
            "enabled": self.enabled,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PolicyRule":
        return cls(
            rule_id=data["rule_id"],
            pattern=data["pattern"],
            action=PolicyAction(data["action"]),
            priority=data.get("priority", 0),
            trust_levels=[TrustLevel(t) for t in data.get("trust_levels", [])],
            sources=[TrustSource(s) for s in data.get("sources", [])],
            max_risk_level=RiskLevel(data["max_risk_level"]) if data.get("max_risk_level") else None,
            agent_ids=data.get("agent_ids", []),
            reason=data.get("reason", ""),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )


@dataclass
class PluginPolicy:
    """
    Complete policy configuration.
    """
    mode: PolicyMode = PolicyMode.ALLOW_ALL
    rules: List[PolicyRule] = field(default_factory=list)
    
    # Global settings
    block_untrusted: bool = False
    block_unscanned: bool = False
    require_signature: bool = False
    
    # Agent defaults
    default_agent_mode: PolicyMode = PolicyMode.ALLOW_ALL
    agent_overrides: Dict[str, PolicyMode] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "rules": [r.to_dict() for r in self.rules],
            "block_untrusted": self.block_untrusted,
            "block_unscanned": self.block_unscanned,
            "require_signature": self.require_signature,
            "default_agent_mode": self.default_agent_mode.value,
            "agent_overrides": {k: v.value for k, v in self.agent_overrides.items()},
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginPolicy":
        return cls(
            mode=PolicyMode(data.get("mode", "allow_all")),
            rules=[PolicyRule.from_dict(r) for r in data.get("rules", [])],
            block_untrusted=data.get("block_untrusted", False),
            block_unscanned=data.get("block_unscanned", False),
            require_signature=data.get("require_signature", False),
            default_agent_mode=PolicyMode(data.get("default_agent_mode", "allow_all")),
            agent_overrides={k: PolicyMode(v) for k, v in data.get("agent_overrides", {}).items()},
        )


@dataclass
class PolicyDecision:
    """Result of a policy evaluation."""
    allowed: bool
    action: PolicyAction
    matched_rule: Optional[PolicyRule] = None
    reason: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "action": self.action.value,
            "matched_rule_id": self.matched_rule.rule_id if self.matched_rule else None,
            "reason": self.reason,
        }


# ============================================================================
# Policy Engine
# ============================================================================

class PluginPolicyEngine:
    """
    Evaluates plugin policies.
    
    Features:
    - Priority-based rule matching
    - Default modes (allow/deny all)
    - Trust-based filtering
    - Agent-specific policies
    """
    
    def __init__(
        self,
        policy_file: Optional[str] = None,
    ):
        self._policy_file = Path(policy_file or os.getenv(
            "LADA_PLUGIN_POLICY_FILE",
            "config/plugin_policy.json"
        ))
        
        self._policy = PluginPolicy()
        self._lock = threading.RLock()
        
        # Load existing policy
        self._load_policy()
        
        logger.info(f"[PluginPolicyEngine] Initialized with {len(self._policy.rules)} rules")
    
    def evaluate(
        self,
        plugin_id: str,
        trust_level: Optional[TrustLevel] = None,
        source: Optional[TrustSource] = None,
        risk_level: Optional[RiskLevel] = None,
        agent_id: Optional[str] = None,
        scan_passed: Optional[bool] = None,
        has_signature: bool = False,
    ) -> PolicyDecision:
        """
        Evaluate policy for a plugin.
        
        Args:
            plugin_id: Plugin identifier
            trust_level: Plugin's trust level
            source: Where plugin came from
            risk_level: Plugin's risk assessment
            agent_id: Agent requesting access
            scan_passed: Whether security scan passed
            has_signature: Whether plugin is signed
        
        Returns:
            PolicyDecision with allowed status and reason
        """
        with self._lock:
            # Global checks first
            if self._policy.block_untrusted and trust_level == TrustLevel.UNTRUSTED:
                return PolicyDecision(
                    allowed=False,
                    action=PolicyAction.DENY,
                    reason="Untrusted plugins are blocked by policy",
                )
            
            if self._policy.block_unscanned and scan_passed is False:
                return PolicyDecision(
                    allowed=False,
                    action=PolicyAction.DENY,
                    reason="Unscanned plugins are blocked by policy",
                )
            
            if self._policy.require_signature and not has_signature:
                return PolicyDecision(
                    allowed=False,
                    action=PolicyAction.DENY,
                    reason="Unsigned plugins are blocked by policy",
                )
            
            # Evaluate rules in priority order
            sorted_rules = sorted(
                self._policy.rules,
                key=lambda r: r.priority,
                reverse=True,
            )
            
            for rule in sorted_rules:
                if rule.matches(
                    plugin_id=plugin_id,
                    trust_level=trust_level,
                    source=source,
                    risk_level=risk_level,
                    agent_id=agent_id,
                ):
                    allowed = rule.action in (PolicyAction.ALLOW, PolicyAction.AUDIT)
                    return PolicyDecision(
                        allowed=allowed,
                        action=rule.action,
                        matched_rule=rule,
                        reason=rule.reason or f"Matched rule: {rule.rule_id}",
                    )
            
            # No rule matched - use default mode
            mode = self._get_effective_mode(agent_id)
            if mode == PolicyMode.ALLOW_ALL:
                return PolicyDecision(
                    allowed=True,
                    action=PolicyAction.ALLOW,
                    reason="Default policy: allow all",
                )
            else:
                return PolicyDecision(
                    allowed=False,
                    action=PolicyAction.DENY,
                    reason="Default policy: deny all",
                )
    
    def add_rule(self, rule: PolicyRule) -> bool:
        """Add a policy rule."""
        with self._lock:
            # Check for duplicate
            existing = [r for r in self._policy.rules if r.rule_id == rule.rule_id]
            if existing:
                # Update existing
                self._policy.rules.remove(existing[0])
            
            self._policy.rules.append(rule)
            self._save_policy()
        return True
    
    def remove_rule(self, rule_id: str) -> bool:
        """Remove a policy rule."""
        with self._lock:
            matching = [r for r in self._policy.rules if r.rule_id == rule_id]
            if matching:
                self._policy.rules.remove(matching[0])
                self._save_policy()
                return True
        return False
    
    def get_rule(self, rule_id: str) -> Optional[PolicyRule]:
        """Get a specific rule."""
        with self._lock:
            for rule in self._policy.rules:
                if rule.rule_id == rule_id:
                    return rule
        return None
    
    def list_rules(self) -> List[PolicyRule]:
        """List all rules."""
        with self._lock:
            return list(self._policy.rules)
    
    def set_mode(self, mode: PolicyMode) -> None:
        """Set default policy mode."""
        with self._lock:
            self._policy.mode = mode
            self._save_policy()
    
    def set_agent_mode(self, agent_id: str, mode: PolicyMode) -> None:
        """Set policy mode for a specific agent."""
        with self._lock:
            self._policy.agent_overrides[agent_id] = mode
            self._save_policy()
    
    def set_global_settings(
        self,
        block_untrusted: Optional[bool] = None,
        block_unscanned: Optional[bool] = None,
        require_signature: Optional[bool] = None,
    ) -> None:
        """Update global policy settings."""
        with self._lock:
            if block_untrusted is not None:
                self._policy.block_untrusted = block_untrusted
            if block_unscanned is not None:
                self._policy.block_unscanned = block_unscanned
            if require_signature is not None:
                self._policy.require_signature = require_signature
            self._save_policy()
    
    def get_policy(self) -> PluginPolicy:
        """Get current policy."""
        with self._lock:
            return self._policy
    
    def set_policy(self, policy: PluginPolicy) -> None:
        """Set entire policy."""
        with self._lock:
            self._policy = policy
            self._save_policy()
    
    def _get_effective_mode(self, agent_id: Optional[str]) -> PolicyMode:
        """Get effective mode for an agent."""
        if agent_id and agent_id in self._policy.agent_overrides:
            return self._policy.agent_overrides[agent_id]
        return self._policy.mode
    
    # ─── API Helper Methods ─────────────────────────────────────────────
    
    def get_policy_summary(self) -> Dict[str, Any]:
        """Get a summary of current policy for API responses."""
        with self._lock:
            return {
                "mode": self._policy.mode.value,
                "block_untrusted": self._policy.block_untrusted,
                "block_unscanned": self._policy.block_unscanned,
                "require_signature": self._policy.require_signature,
                "rules_count": len(self._policy.rules),
                "rules": [
                    {
                        "id": r.rule_id,
                        "pattern": r.pattern,
                        "action": r.action.value,
                        "priority": r.priority,
                        "enabled": r.enabled,
                    }
                    for r in self._policy.rules
                ],
                "agent_overrides": {
                    k: v.value for k, v in self._policy.agent_overrides.items()
                },
            }
    
    def check_permission(self, plugin_id: str, action: str) -> PolicyDecision:
        """
        Check if a plugin is allowed to perform an action.
        
        Simplified API wrapper around evaluate().
        """
        return self.evaluate(plugin_id=plugin_id)
    
    def add_to_allowlist(self, plugin_id: str) -> bool:
        """Add a plugin to the allowlist (high priority allow rule)."""
        rule = PolicyRule(
            rule_id=f"allow-{plugin_id}",
            pattern=plugin_id,
            action=PolicyAction.ALLOW,
            priority=800,  # High priority
            reason=f"Explicitly allowed via API",
        )
        return self.add_rule(rule)
    
    def add_to_denylist(self, plugin_id: str) -> bool:
        """Add a plugin to the denylist (high priority deny rule)."""
        rule = PolicyRule(
            rule_id=f"deny-{plugin_id}",
            pattern=plugin_id,
            action=PolicyAction.DENY,
            priority=850,  # Higher than allow
            reason=f"Explicitly denied via API",
        )
        return self.add_rule(rule)
    
    def remove_from_allowlist(self, plugin_id: str) -> bool:
        """Remove a plugin from the allowlist."""
        return self.remove_rule(f"allow-{plugin_id}")
    
    def remove_from_denylist(self, plugin_id: str) -> bool:
        """Remove a plugin from the denylist."""
        return self.remove_rule(f"deny-{plugin_id}")
    
    def _load_policy(self):
        """Load policy from disk."""
        if self._policy_file.exists():
            try:
                with open(self._policy_file, 'r') as f:
                    data = json.load(f)
                self._policy = PluginPolicy.from_dict(data)
            except Exception as e:
                logger.warning(f"[PluginPolicyEngine] Failed to load policy: {e}")
    
    def _save_policy(self):
        """Save policy to disk."""
        try:
            self._policy_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._policy_file, 'w') as f:
                json.dump(self._policy.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"[PluginPolicyEngine] Failed to save policy: {e}")


# ============================================================================
# Builtin Rules
# ============================================================================

def create_default_rules() -> List[PolicyRule]:
    """Create default policy rules."""
    return [
        # Always allow builtin plugins
        PolicyRule(
            rule_id="builtin-allow",
            pattern="*",
            action=PolicyAction.ALLOW,
            priority=1000,
            trust_levels=[TrustLevel.BUILTIN],
            reason="Built-in plugins are always allowed",
        ),
        
        # Allow verified marketplace plugins
        PolicyRule(
            rule_id="marketplace-verified",
            pattern="*",
            action=PolicyAction.ALLOW,
            priority=100,
            trust_levels=[TrustLevel.VERIFIED],
            sources=[TrustSource.MARKETPLACE],
            reason="Verified marketplace plugins are allowed",
        ),
        
        # Audit community plugins
        PolicyRule(
            rule_id="community-audit",
            pattern="*",
            action=PolicyAction.AUDIT,
            priority=50,
            trust_levels=[TrustLevel.COMMUNITY],
            reason="Community plugins are allowed with logging",
        ),
        
        # Block critical risk plugins
        PolicyRule(
            rule_id="critical-risk-block",
            pattern="*",
            action=PolicyAction.DENY,
            priority=900,
            max_risk_level=RiskLevel.HIGH,  # Block CRITICAL
            reason="Critical risk plugins are blocked",
        ),
    ]


# ============================================================================
# Singleton
# ============================================================================

_engine_instance: Optional[PluginPolicyEngine] = None
_engine_lock = threading.Lock()


def get_policy_engine() -> PluginPolicyEngine:
    """Get singleton PluginPolicyEngine instance."""
    global _engine_instance
    if _engine_instance is None:
        with _engine_lock:
            if _engine_instance is None:
                _engine_instance = PluginPolicyEngine()
    return _engine_instance
