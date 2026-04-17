"""
LADA Action Policy Engine

Defines policies for action classification and approval requirements.

Features:
- Rule-based action matching
- Scope-aware permissions
- Agent-specific policies
- Pattern matching for command names
- Configurable severity levels
"""

import os
import re
import json
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Set, Callable, Pattern
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class ActionSeverity(str, Enum):
    """Action severity levels."""
    SAFE = "safe"           # No approval needed
    INFO = "info"           # Log only
    WARNING = "warning"     # Show warning, optional approval
    DANGEROUS = "dangerous" # Require explicit approval
    CRITICAL = "critical"   # Require approval + PIN/2FA
    FORBIDDEN = "forbidden" # Always blocked


class ApprovalType(str, Enum):
    """Type of approval required."""
    NONE = "none"                   # No approval
    IMPLICIT = "implicit"           # Auto-approved after timeout
    EXPLICIT = "explicit"           # User must approve
    EXPLICIT_PIN = "explicit_pin"   # User must approve with PIN
    MULTI_PARTY = "multi_party"     # Multiple approvers needed


class PolicyScope(str, Enum):
    """Scope a policy applies to."""
    GLOBAL = "global"       # All agents, all channels
    AGENT = "agent"         # Specific agent
    CHANNEL = "channel"     # Specific channel type
    SESSION = "session"     # Specific session


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class PolicyRule:
    """
    A single policy rule that matches actions.
    
    Rules are evaluated in priority order (higher = checked first).
    First matching rule determines the policy.
    """
    id: str
    name: str
    description: str = ""
    
    # Matching criteria
    action_pattern: str = "*"  # Glob pattern or regex
    command_patterns: List[str] = field(default_factory=list)  # Additional patterns
    parameter_conditions: Dict[str, Any] = field(default_factory=dict)  # param -> value/regex
    
    # Scope restrictions
    scope: PolicyScope = PolicyScope.GLOBAL
    agent_ids: Set[str] = field(default_factory=set)  # Empty = all agents
    channel_types: Set[str] = field(default_factory=set)  # Empty = all channels
    
    # Policy outcome
    severity: ActionSeverity = ActionSeverity.SAFE
    approval_type: ApprovalType = ApprovalType.NONE
    timeout_seconds: int = 86400  # 24 hours default
    requires_reason: bool = False
    
    # Priority
    priority: int = 0  # Higher = checked first
    enabled: bool = True
    
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    tags: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        # Compile patterns for efficient matching
        self._action_regex: Optional[Pattern] = None
        self._command_regexes: List[Pattern] = []
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile glob patterns to regex."""
        if self.action_pattern != "*":
            regex = self._glob_to_regex(self.action_pattern)
            self._action_regex = re.compile(regex, re.IGNORECASE)
        
        for pattern in self.command_patterns:
            regex = self._glob_to_regex(pattern)
            self._command_regexes.append(re.compile(regex, re.IGNORECASE))
    
    @staticmethod
    def _glob_to_regex(pattern: str) -> str:
        """Convert glob pattern to regex."""
        # Escape special regex chars except * and ?
        escaped = re.escape(pattern)
        # Convert glob wildcards to regex
        escaped = escaped.replace(r"\*", ".*")
        escaped = escaped.replace(r"\?", ".")
        return f"^{escaped}$"
    
    def matches_action(self, action: str) -> bool:
        """Check if action name matches this rule."""
        if self.action_pattern == "*":
            return True
        if self._action_regex:
            return bool(self._action_regex.match(action))
        return False
    
    def matches_command(self, command: str) -> bool:
        """Check if command text matches any pattern."""
        if not self._command_regexes:
            return True  # No command patterns = match all
        return any(r.match(command) for r in self._command_regexes)
    
    def matches_parameters(self, params: Dict[str, Any]) -> bool:
        """Check if parameters match conditions."""
        if not self.parameter_conditions:
            return True
        
        for key, expected in self.parameter_conditions.items():
            actual = params.get(key)
            if actual is None:
                return False
            
            if isinstance(expected, str) and expected.startswith("regex:"):
                pattern = expected[6:]
                if not re.match(pattern, str(actual), re.IGNORECASE):
                    return False
            elif actual != expected:
                return False
        
        return True
    
    def matches_scope(
        self,
        agent_id: Optional[str] = None,
        channel_type: Optional[str] = None,
    ) -> bool:
        """Check if scope matches."""
        if self.scope == PolicyScope.GLOBAL:
            return True
        
        if self.scope == PolicyScope.AGENT:
            if self.agent_ids and agent_id not in self.agent_ids:
                return False
        
        if self.scope == PolicyScope.CHANNEL:
            if self.channel_types and channel_type not in self.channel_types:
                return False
        
        return True
    
    def matches(
        self,
        action: str,
        command: str = "",
        params: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        channel_type: Optional[str] = None,
    ) -> bool:
        """Check if this rule matches the given action context."""
        if not self.enabled:
            return False
        
        return (
            self.matches_action(action) and
            self.matches_command(command) and
            self.matches_parameters(params or {}) and
            self.matches_scope(agent_id, channel_type)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "action_pattern": self.action_pattern,
            "command_patterns": self.command_patterns,
            "parameter_conditions": self.parameter_conditions,
            "scope": self.scope.value,
            "agent_ids": list(self.agent_ids),
            "channel_types": list(self.channel_types),
            "severity": self.severity.value,
            "approval_type": self.approval_type.value,
            "timeout_seconds": self.timeout_seconds,
            "requires_reason": self.requires_reason,
            "priority": self.priority,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "tags": self.tags,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PolicyRule":
        rule = cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            action_pattern=data.get("action_pattern", "*"),
            command_patterns=data.get("command_patterns", []),
            parameter_conditions=data.get("parameter_conditions", {}),
            scope=PolicyScope(data.get("scope", "global")),
            agent_ids=set(data.get("agent_ids", [])),
            channel_types=set(data.get("channel_types", [])),
            severity=ActionSeverity(data.get("severity", "safe")),
            approval_type=ApprovalType(data.get("approval_type", "none")),
            timeout_seconds=data.get("timeout_seconds", 86400),
            requires_reason=data.get("requires_reason", False),
            priority=data.get("priority", 0),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", datetime.now().isoformat()),
            tags=data.get("tags", []),
        )
        return rule


@dataclass
class PolicyMatch:
    """Result of a policy evaluation."""
    matched: bool
    rule: Optional[PolicyRule] = None
    severity: ActionSeverity = ActionSeverity.SAFE
    approval_type: ApprovalType = ApprovalType.NONE
    timeout_seconds: int = 86400
    requires_reason: bool = False
    message: str = ""
    
    @property
    def requires_approval(self) -> bool:
        return self.approval_type not in (ApprovalType.NONE, ApprovalType.IMPLICIT)
    
    @property
    def is_forbidden(self) -> bool:
        return self.severity == ActionSeverity.FORBIDDEN
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "matched": self.matched,
            "rule_id": self.rule.id if self.rule else None,
            "rule_name": self.rule.name if self.rule else None,
            "severity": self.severity.value,
            "approval_type": self.approval_type.value,
            "timeout_seconds": self.timeout_seconds,
            "requires_reason": self.requires_reason,
            "requires_approval": self.requires_approval,
            "is_forbidden": self.is_forbidden,
            "message": self.message,
        }


@dataclass
class ActionPolicy:
    """
    A complete policy definition with multiple rules.
    
    Policies can be layered - agent policies override global,
    session policies override agent, etc.
    """
    id: str
    name: str
    description: str = ""
    rules: List[PolicyRule] = field(default_factory=list)
    default_severity: ActionSeverity = ActionSeverity.SAFE
    default_approval: ApprovalType = ApprovalType.NONE
    enabled: bool = True
    priority: int = 0  # For policy layering
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def add_rule(self, rule: PolicyRule):
        """Add a rule to this policy."""
        self.rules.append(rule)
        # Keep sorted by priority (descending)
        self.rules.sort(key=lambda r: r.priority, reverse=True)
    
    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID."""
        for i, rule in enumerate(self.rules):
            if rule.id == rule_id:
                del self.rules[i]
                return True
        return False
    
    def evaluate(
        self,
        action: str,
        command: str = "",
        params: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        channel_type: Optional[str] = None,
    ) -> PolicyMatch:
        """Evaluate action against this policy."""
        if not self.enabled:
            return PolicyMatch(matched=False)
        
        # Check rules in priority order
        for rule in self.rules:
            if rule.matches(action, command, params, agent_id, channel_type):
                return PolicyMatch(
                    matched=True,
                    rule=rule,
                    severity=rule.severity,
                    approval_type=rule.approval_type,
                    timeout_seconds=rule.timeout_seconds,
                    requires_reason=rule.requires_reason,
                    message=rule.description,
                )
        
        # No rule matched, use defaults
        return PolicyMatch(
            matched=False,
            severity=self.default_severity,
            approval_type=self.default_approval,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "rules": [r.to_dict() for r in self.rules],
            "default_severity": self.default_severity.value,
            "default_approval": self.default_approval.value,
            "enabled": self.enabled,
            "priority": self.priority,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionPolicy":
        rules = [PolicyRule.from_dict(r) for r in data.get("rules", [])]
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            rules=rules,
            default_severity=ActionSeverity(data.get("default_severity", "safe")),
            default_approval=ApprovalType(data.get("default_approval", "none")),
            enabled=data.get("enabled", True),
            priority=data.get("priority", 0),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )


# ============================================================================
# Policy Engine
# ============================================================================

class PolicyEngine:
    """
    Central engine for policy evaluation.
    
    Manages multiple policies and evaluates actions against them.
    Supports policy layering with priority-based override.
    """
    
    DEFAULT_DIR = "config/policies"
    DEFAULT_POLICY_FILE = "default_policy.json"
    
    # Built-in dangerous actions
    BUILTIN_DANGEROUS = {
        "delete_file": ActionSeverity.DANGEROUS,
        "delete_folder": ActionSeverity.DANGEROUS,
        "delete_directory": ActionSeverity.DANGEROUS,
        "format_drive": ActionSeverity.CRITICAL,
        "format_disk": ActionSeverity.CRITICAL,
        "modify_registry": ActionSeverity.DANGEROUS,
        "edit_registry": ActionSeverity.DANGEROUS,
        "system_shutdown": ActionSeverity.WARNING,
        "system_restart": ActionSeverity.WARNING,
        "shutdown_computer": ActionSeverity.WARNING,
        "restart_computer": ActionSeverity.WARNING,
        "disable_antivirus": ActionSeverity.CRITICAL,
        "uninstall_software": ActionSeverity.DANGEROUS,
        "install_software": ActionSeverity.WARNING,
        "change_password": ActionSeverity.DANGEROUS,
        "send_email": ActionSeverity.WARNING,
        "execute_script": ActionSeverity.DANGEROUS,
        "run_command": ActionSeverity.DANGEROUS,
        "system_command": ActionSeverity.DANGEROUS,
    }
    
    # Built-in forbidden actions
    BUILTIN_FORBIDDEN = {
        "format_c_drive",
        "delete_system32",
        "disable_windows_defender_permanently",
        "remove_boot_files",
        "factory_reset_system",
        "wipe_all_data",
        "delete_all_files",
        "rm_rf_root",
    }
    
    def __init__(self, policies_dir: Optional[str] = None):
        self.policies_dir = Path(
            policies_dir or os.getenv("LADA_POLICIES_DIR", self.DEFAULT_DIR)
        )
        self.policies_dir.mkdir(parents=True, exist_ok=True)
        
        # Policies indexed by ID
        self._policies: Dict[str, ActionPolicy] = {}
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Load built-in and saved policies
        self._load_builtin_policy()
        self._load_policies()
        
        logger.info(f"[PolicyEngine] Initialized with {len(self._policies)} policies")
    
    def _load_builtin_policy(self):
        """Create built-in default policy."""
        policy = ActionPolicy(
            id="builtin",
            name="Built-in Safety Policy",
            description="Default LADA safety rules",
            priority=0,  # Lowest priority (overridable)
        )
        
        # Add forbidden actions
        for action in self.BUILTIN_FORBIDDEN:
            policy.add_rule(PolicyRule(
                id=f"forbidden_{action}",
                name=f"Block {action}",
                action_pattern=action,
                severity=ActionSeverity.FORBIDDEN,
                approval_type=ApprovalType.NONE,
                priority=1000,
            ))
        
        # Add dangerous actions
        for action, severity in self.BUILTIN_DANGEROUS.items():
            approval = ApprovalType.EXPLICIT
            if severity == ActionSeverity.CRITICAL:
                approval = ApprovalType.EXPLICIT_PIN
            elif severity == ActionSeverity.WARNING:
                approval = ApprovalType.IMPLICIT
            
            policy.add_rule(PolicyRule(
                id=f"builtin_{action}",
                name=f"Require approval for {action}",
                action_pattern=action,
                severity=severity,
                approval_type=approval,
                priority=100,
            ))
        
        self._policies["builtin"] = policy
    
    def _load_policies(self):
        """Load saved policies from disk."""
        try:
            for filepath in self.policies_dir.glob("*.json"):
                if filepath.name == self.DEFAULT_POLICY_FILE:
                    continue
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                policy = ActionPolicy.from_dict(data)
                self._policies[policy.id] = policy
            logger.info(f"[PolicyEngine] Loaded {len(self._policies) - 1} custom policies")
        except Exception as e:
            logger.error(f"[PolicyEngine] Failed to load policies: {e}")
    
    def _save_policy(self, policy: ActionPolicy):
        """Save a policy to disk."""
        try:
            filepath = self.policies_dir / f"{policy.id}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(policy.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"[PolicyEngine] Failed to save policy {policy.id}: {e}")
    
    # ========================================================================
    # Policy Management
    # ========================================================================
    
    def add_policy(self, policy: ActionPolicy, persist: bool = True) -> bool:
        """Add or update a policy."""
        with self._lock:
            self._policies[policy.id] = policy
            if persist and policy.id != "builtin":
                self._save_policy(policy)
        logger.info(f"[PolicyEngine] Added policy: {policy.id}")
        return True
    
    def get_policy(self, policy_id: str) -> Optional[ActionPolicy]:
        """Get policy by ID."""
        with self._lock:
            return self._policies.get(policy_id)
    
    def list_policies(self) -> List[ActionPolicy]:
        """List all policies."""
        with self._lock:
            return list(self._policies.values())
    
    def remove_policy(self, policy_id: str) -> bool:
        """Remove a policy (cannot remove builtin)."""
        if policy_id == "builtin":
            return False
        
        with self._lock:
            if policy_id in self._policies:
                del self._policies[policy_id]
                try:
                    filepath = self.policies_dir / f"{policy_id}.json"
                    if filepath.exists():
                        filepath.unlink()
                except Exception as e:
                    logger.error(f"[PolicyEngine] Failed to delete policy file: {e}")
                return True
        return False
    
    # ========================================================================
    # Policy Evaluation
    # ========================================================================
    
    def evaluate(
        self,
        action: str,
        command: str = "",
        params: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        channel_type: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> PolicyMatch:
        """
        Evaluate an action against all policies.
        
        Policies are checked in priority order (highest first).
        First matching rule from highest priority policy wins.
        """
        with self._lock:
            # Sort policies by priority (descending)
            sorted_policies = sorted(
                self._policies.values(),
                key=lambda p: p.priority,
                reverse=True,
            )
            
            best_match: Optional[PolicyMatch] = None
            
            for policy in sorted_policies:
                if not policy.enabled:
                    continue
                
                match = policy.evaluate(
                    action=action,
                    command=command,
                    params=params,
                    agent_id=agent_id,
                    channel_type=channel_type,
                )
                
                if match.matched:
                    return match
                
                # Keep track of default for fallback
                if best_match is None:
                    best_match = match
            
            # Return default match (no rules matched)
            return best_match or PolicyMatch(
                matched=False,
                severity=ActionSeverity.SAFE,
                approval_type=ApprovalType.NONE,
            )
    
    def check_permission(
        self,
        action: str,
        command: str = "",
        params: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        channel_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Check if action is permitted and what approval is needed.
        
        Returns compatibility dict matching safety_controller.check_permission()
        """
        match = self.evaluate(
            action=action,
            command=command,
            params=params,
            agent_id=agent_id,
            channel_type=channel_type,
        )
        
        return {
            "allowed": not match.is_forbidden,
            "requires_confirmation": match.requires_approval,
            "severity": match.severity.value,
            "approval_type": match.approval_type.value,
            "timeout_seconds": match.timeout_seconds,
            "requires_reason": match.requires_reason,
            "requires_pin": match.approval_type == ApprovalType.EXPLICIT_PIN,
            "reason": match.message,
            "rule_id": match.rule.id if match.rule else None,
        }
    
    # ========================================================================
    # Rule Shortcuts
    # ========================================================================
    
    def add_dangerous_action(
        self,
        action: str,
        severity: ActionSeverity = ActionSeverity.DANGEROUS,
        approval_type: ApprovalType = ApprovalType.EXPLICIT,
        description: str = "",
    ) -> bool:
        """Add a dangerous action rule to builtin policy."""
        rule = PolicyRule(
            id=f"custom_{action}",
            name=f"Dangerous: {action}",
            description=description,
            action_pattern=action,
            severity=severity,
            approval_type=approval_type,
            priority=200,
        )
        
        with self._lock:
            builtin = self._policies.get("builtin")
            if builtin:
                builtin.add_rule(rule)
                return True
        return False
    
    def add_forbidden_action(self, action: str) -> bool:
        """Add a forbidden action rule."""
        rule = PolicyRule(
            id=f"forbidden_{action}",
            name=f"Forbidden: {action}",
            action_pattern=action,
            severity=ActionSeverity.FORBIDDEN,
            priority=1000,
        )
        
        with self._lock:
            builtin = self._policies.get("builtin")
            if builtin:
                builtin.add_rule(rule)
                return True
        return False
    
    def add_safe_action(self, action: str) -> bool:
        """Whitelist an action as safe (high priority to override dangerous)."""
        rule = PolicyRule(
            id=f"safe_{action}",
            name=f"Safe: {action}",
            action_pattern=action,
            severity=ActionSeverity.SAFE,
            approval_type=ApprovalType.NONE,
            priority=500,  # Higher than dangerous rules
        )
        
        with self._lock:
            builtin = self._policies.get("builtin")
            if builtin:
                builtin.add_rule(rule)
                return True
        return False


# ============================================================================
# Singleton
# ============================================================================

_engine_instance: Optional[PolicyEngine] = None
_engine_lock = threading.Lock()


def get_policy_engine() -> PolicyEngine:
    """Get singleton PolicyEngine instance."""
    global _engine_instance
    if _engine_instance is None:
        with _engine_lock:
            if _engine_instance is None:
                _engine_instance = PolicyEngine()
    return _engine_instance
