"""
LADA v9.0 - Permission System
Module 12: Safety gates, confirmation dialogs, risk assessment,
action auditing, and privilege levels.

Features:
- Permission levels (admin, user, guest, restricted)
- Risk assessment for commands
- Confirmation dialogs for dangerous operations
- Action auditing and logging
- Whitelist/blacklist command management
- Rate limiting
- Session-based permissions
- Emergency shutdown capability
"""

import os
import json
import logging
import hashlib
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
import re
import time

logger = logging.getLogger(__name__)


class PermissionLevel(Enum):
    """Permission levels for users/sessions."""
    ADMIN = 0      # Full access, no restrictions
    USER = 1       # Normal access, confirmations for dangerous ops
    GUEST = 2      # Limited access, many restrictions
    RESTRICTED = 3 # Read-only, no system modifications
    LOCKED = 4     # All commands blocked (emergency mode)


class RiskLevel(Enum):
    """Risk levels for commands."""
    SAFE = 0       # No risk, always allowed
    LOW = 1        # Minor risk, allowed by default
    MEDIUM = 2     # Moderate risk, may require confirmation
    HIGH = 3       # High risk, requires confirmation
    CRITICAL = 4   # Critical risk, requires admin + confirmation


class ActionCategory(Enum):
    """Categories of actions for permission control."""
    READ = "read"           # Reading files, status checks
    WRITE = "write"         # Writing files, modifications
    SYSTEM = "system"       # System operations
    NETWORK = "network"     # Network/internet operations
    EXECUTE = "execute"     # Running programs
    AUTOMATION = "automation"  # Automated sequences
    ADMIN = "admin"         # Administrative operations


@dataclass
class AuditEntry:
    """Represents an audited action."""
    id: str
    timestamp: datetime
    action: str
    category: ActionCategory
    risk_level: RiskLevel
    permission_level: PermissionLevel
    allowed: bool
    required_confirmation: bool
    confirmed: bool
    session_id: str
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat(),
            'action': self.action,
            'category': self.category.value,
            'risk_level': self.risk_level.name,
            'permission_level': self.permission_level.name,
            'allowed': self.allowed,
            'required_confirmation': self.required_confirmation,
            'confirmed': self.confirmed,
            'session_id': self.session_id,
            'details': self.details
        }


@dataclass
class CommandRule:
    """Rule for command permissions."""
    pattern: str           # Regex pattern for command matching
    category: ActionCategory
    risk_level: RiskLevel
    min_permission: PermissionLevel
    requires_confirmation: bool
    description: str = ""


class PermissionSystem:
    """
    Manages permissions, confirmations, and security.
    Acts as a safety gate for all JARVIS commands.
    """
    
    # Default dangerous patterns (require confirmation)
    DANGEROUS_PATTERNS = [
        (r"delete|remove|erase", RiskLevel.HIGH, "Deletion operations"),
        (r"format|wipe", RiskLevel.CRITICAL, "Format operations"),
        (r"shutdown|restart|reboot", RiskLevel.HIGH, "System power operations"),
        (r"install|uninstall", RiskLevel.MEDIUM, "Installation operations"),
        (r"execute|run\s+script", RiskLevel.HIGH, "Script execution"),
        (r"send\s+email|send\s+message", RiskLevel.MEDIUM, "Sending communications"),
        (r"transfer|move\s+\$|payment", RiskLevel.CRITICAL, "Financial operations"),
        (r"kill\s+process|terminate", RiskLevel.HIGH, "Process termination"),
        (r"modify\s+registry|regedit", RiskLevel.CRITICAL, "Registry modifications"),
        (r"admin|sudo|elevate", RiskLevel.CRITICAL, "Privilege escalation"),
    ]
    
    # Default safe patterns (never require confirmation)
    SAFE_PATTERNS = [
        r"what\s+time|current\s+time",
        r"weather|temperature|forecast",
        r"hello|hi|hey|good\s+morning",
        r"thank|thanks|thank\s+you",
        r"help|what\s+can\s+you",
        r"status|info|show|display|list",
        r"search|find|look\s+up",
        r"open\s+browser|open\s+app",
    ]
    
    def __init__(self, confirmation_callback: Callable[[str, str], bool] = None):
        """
        Initialize permission system.
        
        Args:
            confirmation_callback: Function to request user confirmation
                                 Takes (title, message), returns bool
        """
        self.confirmation_callback = confirmation_callback
        
        # Data storage
        self.data_dir = Path("data/permissions")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Current session
        self.session_id = self._generate_session_id()
        self.permission_level = PermissionLevel.USER  # Default level
        
        # Audit log
        self.audit_log: List[AuditEntry] = []
        self.max_audit_entries = 1000
        
        # Command rules
        self.rules: List[CommandRule] = []
        self._register_default_rules()
        
        # Whitelists and blacklists
        self.whitelist: Set[str] = set()  # Always allowed commands
        self.blacklist: Set[str] = set()  # Always blocked commands
        
        # Rate limiting
        self.rate_limits: Dict[str, List[datetime]] = {}
        self.default_rate_limit = 100  # Commands per minute
        self.category_rate_limits = {
            ActionCategory.EXECUTE: 10,
            ActionCategory.SYSTEM: 20,
            ActionCategory.NETWORK: 30,
            ActionCategory.ADMIN: 5
        }
        
        # Emergency state
        self.emergency_locked = False
        self.lock_reason = ""
        
        # Pending confirmations
        self.pending_confirmations: Dict[str, Dict] = {}
        
        # Lock for thread safety
        self._lock = threading.Lock()
        
        # Load saved data
        self._load_data()
        
        logger.info(f"[PermissionSystem] Initialized (Session: {self.session_id[:8]}...)")
    
    def _generate_session_id(self) -> str:
        """Generate unique session ID."""
        data = f"{datetime.now().isoformat()}_{os.getpid()}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def _register_default_rules(self):
        """Register default command rules."""
        # Safe operations
        self.rules.append(CommandRule(
            pattern=r"^(show|display|list|get|check|what|how|when|where|who)\b",
            category=ActionCategory.READ,
            risk_level=RiskLevel.SAFE,
            min_permission=PermissionLevel.GUEST,
            requires_confirmation=False,
            description="Read operations"
        ))
        
        # File write operations
        self.rules.append(CommandRule(
            pattern=r"(write|save|create|update|edit)\s+(file|document|note)",
            category=ActionCategory.WRITE,
            risk_level=RiskLevel.LOW,
            min_permission=PermissionLevel.USER,
            requires_confirmation=False,
            description="File write operations"
        ))
        
        # Delete operations
        self.rules.append(CommandRule(
            pattern=r"(delete|remove|erase)\s+(file|folder|document)",
            category=ActionCategory.WRITE,
            risk_level=RiskLevel.HIGH,
            min_permission=PermissionLevel.USER,
            requires_confirmation=True,
            description="Delete operations"
        ))
        
        # System operations
        self.rules.append(CommandRule(
            pattern=r"(shutdown|restart|reboot|sleep|hibernate)",
            category=ActionCategory.SYSTEM,
            risk_level=RiskLevel.HIGH,
            min_permission=PermissionLevel.USER,
            requires_confirmation=True,
            description="System power operations"
        ))
        
        # Process operations
        self.rules.append(CommandRule(
            pattern=r"(kill|terminate|end)\s+(process|task|program|app)",
            category=ActionCategory.SYSTEM,
            risk_level=RiskLevel.MEDIUM,
            min_permission=PermissionLevel.USER,
            requires_confirmation=True,
            description="Process termination"
        ))
        
        # Network operations
        self.rules.append(CommandRule(
            pattern=r"(send|email|post|upload|download)",
            category=ActionCategory.NETWORK,
            risk_level=RiskLevel.MEDIUM,
            min_permission=PermissionLevel.USER,
            requires_confirmation=False,
            description="Network operations"
        ))
        
        # Execution operations
        self.rules.append(CommandRule(
            pattern=r"(run|execute)\s+(script|command|program)",
            category=ActionCategory.EXECUTE,
            risk_level=RiskLevel.HIGH,
            min_permission=PermissionLevel.USER,
            requires_confirmation=True,
            description="Script execution"
        ))
        
        # Admin operations
        self.rules.append(CommandRule(
            pattern=r"(admin|sudo|elevate|root|system\s+settings)",
            category=ActionCategory.ADMIN,
            risk_level=RiskLevel.CRITICAL,
            min_permission=PermissionLevel.ADMIN,
            requires_confirmation=True,
            description="Administrative operations"
        ))
    
    # =====================================================
    # PERMISSION CHECKING
    # =====================================================
    
    def check_permission(
        self,
        command: str,
        auto_confirm: bool = False
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Check if command is allowed.
        
        Args:
            command: The command to check
            auto_confirm: If True, skip confirmation dialogs
            
        Returns:
            Tuple of (allowed, reason, details)
        """
        with self._lock:
            # Emergency lock check
            if self.emergency_locked:
                return (False, f"System locked: {self.lock_reason}", {
                    'blocked_by': 'emergency_lock'
                })
            
            # Locked permission level
            if self.permission_level == PermissionLevel.LOCKED:
                return (False, "Session is locked", {
                    'blocked_by': 'locked_session'
                })
            
            # Whitelist check (always allow)
            if self._in_whitelist(command):
                self._audit_action(command, True, False, False)
                return (True, "Whitelisted", {'whitelist': True})
            
            # Blacklist check (always deny)
            if self._in_blacklist(command):
                self._audit_action(command, False, False, False)
                return (False, "Command blacklisted", {'blacklist': True})
            
            # Rate limit check
            if not self._check_rate_limit(command):
                return (False, "Rate limit exceeded", {'rate_limited': True})
            
            # Find matching rule
            rule = self._find_matching_rule(command)
            
            # Assess risk
            risk = self._assess_risk(command, rule)
            
            # Permission level check
            min_level = rule.min_permission if rule else PermissionLevel.USER
            if self.permission_level.value > min_level.value:
                self._audit_action(command, False, False, False, risk_level=risk)
                return (False, f"Requires {min_level.name} permission", {
                    'required': min_level.name,
                    'current': self.permission_level.name
                })
            
            # Confirmation check
            needs_confirmation = self._needs_confirmation(command, rule, risk)
            
            if needs_confirmation and not auto_confirm:
                # Request confirmation
                confirmed = self._request_confirmation(command, risk)
                
                if not confirmed:
                    self._audit_action(command, False, True, False, risk_level=risk)
                    return (False, "Confirmation denied", {
                        'required_confirmation': True,
                        'confirmed': False
                    })
            
            # All checks passed
            self._audit_action(command, True, needs_confirmation, needs_confirmation, risk_level=risk)
            return (True, "Allowed", {
                'risk': risk.name,
                'category': rule.category.value if rule else 'unknown'
            })
    
    def _in_whitelist(self, command: str) -> bool:
        """Check if command is whitelisted."""
        cmd_lower = command.lower().strip()
        for pattern in self.whitelist:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                return True
        return False
    
    def _in_blacklist(self, command: str) -> bool:
        """Check if command is blacklisted."""
        cmd_lower = command.lower().strip()
        for pattern in self.blacklist:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                return True
        return False
    
    def _find_matching_rule(self, command: str) -> Optional[CommandRule]:
        """Find the most specific matching rule."""
        cmd_lower = command.lower().strip()
        
        for rule in self.rules:
            if re.search(rule.pattern, cmd_lower, re.IGNORECASE):
                return rule
        
        return None
    
    def _assess_risk(self, command: str, rule: Optional[CommandRule]) -> RiskLevel:
        """Assess risk level of command."""
        cmd_lower = command.lower().strip()
        
        # Check dangerous patterns
        for pattern, risk, _ in self.DANGEROUS_PATTERNS:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                return risk
        
        # Check safe patterns
        for pattern in self.SAFE_PATTERNS:
            if re.search(pattern, cmd_lower, re.IGNORECASE):
                return RiskLevel.SAFE
        
        # Use rule's risk level
        if rule:
            return rule.risk_level
        
        # Default to medium
        return RiskLevel.MEDIUM
    
    def _needs_confirmation(
        self,
        command: str,
        rule: Optional[CommandRule],
        risk: RiskLevel
    ) -> bool:
        """Determine if confirmation is needed."""
        # Admin users skip most confirmations
        if self.permission_level == PermissionLevel.ADMIN:
            return risk == RiskLevel.CRITICAL
        
        # Rule specifies confirmation
        if rule and rule.requires_confirmation:
            return True
        
        # High/critical risk always needs confirmation for non-admins
        if risk.value >= RiskLevel.HIGH.value:
            return True
        
        return False
    
    def _request_confirmation(self, command: str, risk: RiskLevel) -> bool:
        """Request user confirmation."""
        if self.confirmation_callback:
            title = f"{risk.name} Risk Operation"
            message = f"Allow this command?\n\n{command[:100]}..."
            return self.confirmation_callback(title, message)
        
        # If no callback, log and allow (with warning)
        logger.warning(f"[PermissionSystem] No confirmation callback, allowing: {command[:50]}")
        return True
    
    # =====================================================
    # RATE LIMITING
    # =====================================================
    
    def _check_rate_limit(self, command: str, category: ActionCategory = None) -> bool:
        """Check if command passes rate limit."""
        now = datetime.now()
        
        # Get applicable limit
        limit = self.default_rate_limit
        if category and category in self.category_rate_limits:
            limit = self.category_rate_limits[category]
        
        # Key for rate limiting
        key = f"{self.session_id}_{category.value if category else 'default'}"
        
        # Clean old entries
        if key in self.rate_limits:
            cutoff = now - timedelta(minutes=1)
            self.rate_limits[key] = [
                t for t in self.rate_limits[key] if t > cutoff
            ]
        else:
            self.rate_limits[key] = []
        
        # Check limit
        if len(self.rate_limits[key]) >= limit:
            return False
        
        # Add current request
        self.rate_limits[key].append(now)
        return True
    
    # =====================================================
    # AUDITING
    # =====================================================
    
    def _audit_action(
        self,
        action: str,
        allowed: bool,
        required_confirmation: bool,
        confirmed: bool,
        category: ActionCategory = ActionCategory.READ,
        risk_level: RiskLevel = RiskLevel.SAFE
    ):
        """Add action to audit log."""
        entry = AuditEntry(
            id=f"audit_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(self.audit_log)}",
            timestamp=datetime.now(),
            action=action[:200],  # Truncate long commands
            category=category,
            risk_level=risk_level,
            permission_level=self.permission_level,
            allowed=allowed,
            required_confirmation=required_confirmation,
            confirmed=confirmed,
            session_id=self.session_id
        )
        
        self.audit_log.append(entry)
        
        # Trim if too large
        if len(self.audit_log) > self.max_audit_entries:
            self.audit_log = self.audit_log[-self.max_audit_entries:]
    
    def get_audit_log(
        self,
        start_time: datetime = None,
        end_time: datetime = None,
        allowed_only: bool = None,
        risk_level: RiskLevel = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get filtered audit log entries."""
        entries = self.audit_log.copy()
        
        if start_time:
            entries = [e for e in entries if e.timestamp >= start_time]
        
        if end_time:
            entries = [e for e in entries if e.timestamp <= end_time]
        
        if allowed_only is not None:
            entries = [e for e in entries if e.allowed == allowed_only]
        
        if risk_level:
            entries = [e for e in entries if e.risk_level == risk_level]
        
        # Return most recent first
        entries = sorted(entries, key=lambda x: x.timestamp, reverse=True)
        
        return [e.to_dict() for e in entries[:limit]]
    
    def get_audit_stats(self) -> Dict[str, Any]:
        """Get audit statistics."""
        if not self.audit_log:
            return {'total': 0}
        
        total = len(self.audit_log)
        allowed = sum(1 for e in self.audit_log if e.allowed)
        denied = total - allowed
        
        by_risk = {}
        for level in RiskLevel:
            count = sum(1 for e in self.audit_log if e.risk_level == level)
            by_risk[level.name] = count
        
        by_category = {}
        for cat in ActionCategory:
            count = sum(1 for e in self.audit_log if e.category == cat)
            by_category[cat.value] = count
        
        return {
            'total': total,
            'allowed': allowed,
            'denied': denied,
            'denial_rate': (denied / total * 100) if total > 0 else 0,
            'by_risk': by_risk,
            'by_category': by_category
        }
    
    # =====================================================
    # PERMISSION LEVEL MANAGEMENT
    # =====================================================
    
    def set_permission_level(
        self,
        level: PermissionLevel,
        password: str = None
    ) -> Dict[str, Any]:
        """
        Set current permission level.
        Admin level requires password verification.
        """
        if level == PermissionLevel.ADMIN:
            if not self._verify_admin_password(password):
                return {'success': False, 'error': 'Invalid admin password'}
        
        old_level = self.permission_level
        self.permission_level = level
        
        logger.info(f"[PermissionSystem] Permission level: {old_level.name} -> {level.name}")
        
        return {
            'success': True,
            'old_level': old_level.name,
            'new_level': level.name
        }
    
    def _verify_admin_password(self, password: str) -> bool:
        """Verify admin password."""
        # In production, use proper password hashing
        # For now, simple check
        if not password:
            return False
        
        # Load stored hash
        try:
            creds_file = self.data_dir / 'admin_creds.json'
            if creds_file.exists():
                with open(creds_file, 'r') as f:
                    creds = json.load(f)
                stored_hash = creds.get('password_hash')
                if stored_hash:
                    input_hash = hashlib.sha256(password.encode()).hexdigest()
                    return input_hash == stored_hash
        except:
            pass
        
        # Default password for initial setup
        return password == "jarvis_admin"
    
    def set_admin_password(self, old_password: str, new_password: str) -> Dict[str, Any]:
        """Set or change admin password."""
        if not self._verify_admin_password(old_password):
            return {'success': False, 'error': 'Invalid current password'}
        
        if len(new_password) < 8:
            return {'success': False, 'error': 'Password must be at least 8 characters'}
        
        password_hash = hashlib.sha256(new_password.encode()).hexdigest()
        
        creds_file = self.data_dir / 'admin_creds.json'
        with open(creds_file, 'w') as f:
            json.dump({'password_hash': password_hash}, f)
        
        return {'success': True, 'message': 'Password updated'}
    
    def get_permission_level(self) -> Dict[str, Any]:
        """Get current permission level info."""
        return {
            'level': self.permission_level.name,
            'value': self.permission_level.value,
            'session_id': self.session_id[:8] + '...'
        }
    
    # =====================================================
    # WHITELIST & BLACKLIST
    # =====================================================
    
    def add_to_whitelist(self, pattern: str) -> Dict[str, Any]:
        """Add pattern to whitelist."""
        try:
            re.compile(pattern)  # Validate regex
            self.whitelist.add(pattern)
            self._save_data()
            return {'success': True, 'pattern': pattern}
        except re.error as e:
            return {'success': False, 'error': f'Invalid regex: {e}'}
    
    def remove_from_whitelist(self, pattern: str) -> Dict[str, Any]:
        """Remove pattern from whitelist."""
        if pattern in self.whitelist:
            self.whitelist.discard(pattern)
            self._save_data()
            return {'success': True}
        return {'success': False, 'error': 'Pattern not in whitelist'}
    
    def add_to_blacklist(self, pattern: str) -> Dict[str, Any]:
        """Add pattern to blacklist."""
        try:
            re.compile(pattern)
            self.blacklist.add(pattern)
            self._save_data()
            return {'success': True, 'pattern': pattern}
        except re.error as e:
            return {'success': False, 'error': f'Invalid regex: {e}'}
    
    def remove_from_blacklist(self, pattern: str) -> Dict[str, Any]:
        """Remove pattern from blacklist."""
        if pattern in self.blacklist:
            self.blacklist.discard(pattern)
            self._save_data()
            return {'success': True}
        return {'success': False, 'error': 'Pattern not in blacklist'}
    
    def get_lists(self) -> Dict[str, List[str]]:
        """Get whitelist and blacklist."""
        return {
            'whitelist': list(self.whitelist),
            'blacklist': list(self.blacklist)
        }
    
    # =====================================================
    # EMERGENCY CONTROLS
    # =====================================================
    
    def emergency_lock(self, reason: str = "Emergency lock activated") -> Dict[str, Any]:
        """Lock all operations immediately."""
        with self._lock:
            self.emergency_locked = True
            self.lock_reason = reason
            
            logger.warning(f"[PermissionSystem] EMERGENCY LOCK: {reason}")
            
            # Audit this action
            self._audit_action(
                "EMERGENCY_LOCK",
                True,
                False,
                False,
                ActionCategory.ADMIN,
                RiskLevel.CRITICAL
            )
            
            return {
                'success': True,
                'locked': True,
                'reason': reason
            }
    
    def emergency_unlock(self, password: str) -> Dict[str, Any]:
        """Unlock from emergency state."""
        if not self._verify_admin_password(password):
            return {'success': False, 'error': 'Invalid admin password'}
        
        with self._lock:
            self.emergency_locked = False
            self.lock_reason = ""
            
            logger.info("[PermissionSystem] Emergency lock lifted")
            
            return {'success': True, 'locked': False}
    
    def is_locked(self) -> bool:
        """Check if system is locked."""
        return self.emergency_locked
    
    # =====================================================
    # RULE MANAGEMENT
    # =====================================================
    
    def add_rule(
        self,
        pattern: str,
        category: ActionCategory,
        risk_level: RiskLevel,
        min_permission: PermissionLevel = PermissionLevel.USER,
        requires_confirmation: bool = True,
        description: str = ""
    ) -> Dict[str, Any]:
        """Add a new command rule."""
        try:
            re.compile(pattern)
        except re.error as e:
            return {'success': False, 'error': f'Invalid regex: {e}'}
        
        rule = CommandRule(
            pattern=pattern,
            category=category,
            risk_level=risk_level,
            min_permission=min_permission,
            requires_confirmation=requires_confirmation,
            description=description
        )
        
        self.rules.append(rule)
        self._save_data()
        
        return {'success': True, 'rule': pattern}
    
    def remove_rule(self, pattern: str) -> Dict[str, Any]:
        """Remove a rule by pattern."""
        original_len = len(self.rules)
        self.rules = [r for r in self.rules if r.pattern != pattern]
        
        if len(self.rules) < original_len:
            self._save_data()
            return {'success': True}
        return {'success': False, 'error': 'Rule not found'}
    
    def list_rules(self) -> List[Dict]:
        """List all rules."""
        return [{
            'pattern': r.pattern,
            'category': r.category.value,
            'risk': r.risk_level.name,
            'min_permission': r.min_permission.name,
            'requires_confirmation': r.requires_confirmation,
            'description': r.description
        } for r in self.rules]
    
    # =====================================================
    # CONFIRMATION MANAGEMENT
    # =====================================================
    
    def create_confirmation_request(
        self,
        command: str,
        reason: str = None,
        expires_seconds: int = 60
    ) -> Dict[str, Any]:
        """Create a pending confirmation request."""
        request_id = f"confirm_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        self.pending_confirmations[request_id] = {
            'command': command,
            'reason': reason,
            'created': datetime.now().isoformat(),
            'expires': (datetime.now() + timedelta(seconds=expires_seconds)).isoformat()
        }
        
        return {
            'request_id': request_id,
            'command': command,
            'expires_in': expires_seconds
        }
    
    def confirm_request(self, request_id: str, approved: bool) -> Dict[str, Any]:
        """Confirm or deny a pending request."""
        if request_id not in self.pending_confirmations:
            return {'success': False, 'error': 'Request not found or expired'}
        
        request = self.pending_confirmations.pop(request_id)
        
        # Check expiration
        expires = datetime.fromisoformat(request['expires'])
        if datetime.now() > expires:
            return {'success': False, 'error': 'Request expired'}
        
        if approved:
            return {
                'success': True,
                'approved': True,
                'command': request['command']
            }
        else:
            return {
                'success': True,
                'approved': False,
                'command': request['command']
            }
    
    def get_pending_confirmations(self) -> List[Dict]:
        """Get all pending confirmation requests."""
        now = datetime.now()
        
        # Clean expired
        expired = []
        for rid, req in self.pending_confirmations.items():
            expires = datetime.fromisoformat(req['expires'])
            if now > expires:
                expired.append(rid)
        
        for rid in expired:
            del self.pending_confirmations[rid]
        
        return [
            {'id': rid, **req}
            for rid, req in self.pending_confirmations.items()
        ]
    
    # =====================================================
    # RATE LIMIT CONFIGURATION
    # =====================================================
    
    def set_rate_limit(
        self,
        category: ActionCategory = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Set rate limit for a category or default."""
        if category:
            self.category_rate_limits[category] = limit
        else:
            self.default_rate_limit = limit
        
        return {
            'success': True,
            'category': category.value if category else 'default',
            'limit': limit
        }
    
    def get_rate_limits(self) -> Dict[str, int]:
        """Get all rate limits."""
        limits = {'default': self.default_rate_limit}
        for cat, limit in self.category_rate_limits.items():
            limits[cat.value] = limit
        return limits
    
    # =====================================================
    # DATA PERSISTENCE
    # =====================================================
    
    def _save_data(self):
        """Save permission data."""
        try:
            data = {
                'whitelist': list(self.whitelist),
                'blacklist': list(self.blacklist),
                'rate_limits': {
                    'default': self.default_rate_limit,
                    'categories': {
                        cat.value: limit
                        for cat, limit in self.category_rate_limits.items()
                    }
                },
                'custom_rules': [
                    {
                        'pattern': r.pattern,
                        'category': r.category.value,
                        'risk': r.risk_level.name,
                        'min_permission': r.min_permission.name,
                        'requires_confirmation': r.requires_confirmation,
                        'description': r.description
                    }
                    for r in self.rules[len(self._get_default_rules()):]  # Only custom rules
                ]
            }
            
            with open(self.data_dir / 'permissions.json', 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"[PermissionSystem] Save error: {e}")
    
    def _load_data(self):
        """Load permission data."""
        try:
            perm_file = self.data_dir / 'permissions.json'
            if perm_file.exists():
                with open(perm_file, 'r') as f:
                    data = json.load(f)
                
                self.whitelist = set(data.get('whitelist', []))
                self.blacklist = set(data.get('blacklist', []))
                
                if 'rate_limits' in data:
                    self.default_rate_limit = data['rate_limits'].get('default', 100)
                    for cat_str, limit in data['rate_limits'].get('categories', {}).items():
                        try:
                            cat = ActionCategory(cat_str)
                            self.category_rate_limits[cat] = limit
                        except:
                            pass
                
                # Load custom rules
                for rule_data in data.get('custom_rules', []):
                    try:
                        self.rules.append(CommandRule(
                            pattern=rule_data['pattern'],
                            category=ActionCategory(rule_data['category']),
                            risk_level=RiskLevel[rule_data['risk']],
                            min_permission=PermissionLevel[rule_data['min_permission']],
                            requires_confirmation=rule_data.get('requires_confirmation', True),
                            description=rule_data.get('description', '')
                        ))
                    except:
                        pass
                        
        except Exception as e:
            logger.error(f"[PermissionSystem] Load error: {e}")
    
    def _get_default_rules(self) -> List[CommandRule]:
        """Get count of default rules for saving."""
        # Count rules registered in _register_default_rules
        return []  # Placeholder
    
    def save_audit_log(self, filepath: str = None) -> Dict[str, Any]:
        """Save audit log to file."""
        if not filepath:
            filepath = self.data_dir / f"audit_{datetime.now().strftime('%Y%m%d')}.json"
        
        try:
            with open(filepath, 'w') as f:
                json.dump([e.to_dict() for e in self.audit_log], f, indent=2)
            return {'success': True, 'path': str(filepath)}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # =====================================================
    # STATUS & INFO
    # =====================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get permission system status."""
        return {
            'session_id': self.session_id[:8] + '...',
            'permission_level': self.permission_level.name,
            'emergency_locked': self.emergency_locked,
            'lock_reason': self.lock_reason if self.emergency_locked else None,
            'whitelist_count': len(self.whitelist),
            'blacklist_count': len(self.blacklist),
            'rules_count': len(self.rules),
            'pending_confirmations': len(self.pending_confirmations),
            'audit_entries': len(self.audit_log)
        }


# =====================================================
# SINGLETON & FACTORIES
# =====================================================

_permission_system = None

def get_permission_system(confirmation_callback: Callable = None) -> PermissionSystem:
    """Get or create permission system instance."""
    global _permission_system
    if _permission_system is None:
        _permission_system = PermissionSystem(confirmation_callback)
    return _permission_system

def create_permission_system(confirmation_callback: Callable = None) -> PermissionSystem:
    """Create new permission system instance."""
    return PermissionSystem(confirmation_callback)


# =====================================================
# SAFETY DECORATOR
# =====================================================

def require_permission(
    category: ActionCategory = ActionCategory.READ,
    min_level: PermissionLevel = PermissionLevel.USER
):
    """
    Decorator to require permission for a function.
    
    Usage:
        @require_permission(ActionCategory.SYSTEM, PermissionLevel.ADMIN)
        def dangerous_operation():
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            perm = get_permission_system()
            
            # Get command from function name
            command = func.__name__.replace('_', ' ')
            
            allowed, reason, details = perm.check_permission(command)
            
            if not allowed:
                raise PermissionError(f"Permission denied: {reason}")
            
            return func(*args, **kwargs)
        
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator


# =====================================================
# EXAMPLE USAGE & TESTS
# =====================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("LADA v9.0 - Permission System Test")
    print("=" * 60)
    
    # Simple confirmation callback for testing
    def test_confirm(title, message):
        print(f"   [CONFIRM] {title}: {message[:50]}...")
        return True  # Auto-approve for testing
    
    perm = PermissionSystem(confirmation_callback=test_confirm)
    
    # Test 1: Safe command
    print("\n✅ Test 1: Safe Command")
    allowed, reason, details = perm.check_permission("what time is it")
    print(f"   Command: 'what time is it'")
    print(f"   Allowed: {allowed}, Reason: {reason}")
    
    # Test 2: Medium risk command
    print("\n⚠️ Test 2: Medium Risk Command")
    allowed, reason, details = perm.check_permission("send email to john")
    print(f"   Command: 'send email to john'")
    print(f"   Allowed: {allowed}, Risk: {details.get('risk', 'N/A')}")
    
    # Test 3: High risk command (requires confirmation)
    print("\n🔴 Test 3: High Risk Command")
    allowed, reason, details = perm.check_permission("delete file important.txt")
    print(f"   Command: 'delete file important.txt'")
    print(f"   Allowed: {allowed}")
    
    # Test 4: Permission levels
    print("\n🔑 Test 4: Permission Levels")
    result = perm.set_permission_level(PermissionLevel.GUEST)
    print(f"   Set to GUEST: {result}")
    
    allowed, reason, details = perm.check_permission("delete file test.txt")
    print(f"   Delete as GUEST: Allowed={allowed}, Reason={reason}")
    
    # Reset to USER
    perm.set_permission_level(PermissionLevel.USER)
    
    # Test 5: Whitelist
    print("\n📋 Test 5: Whitelist")
    perm.add_to_whitelist(r"my\s+special\s+command")
    allowed, _, _ = perm.check_permission("my special command")
    print(f"   'my special command' whitelisted: {allowed}")
    
    # Test 6: Blacklist
    print("\n🚫 Test 6: Blacklist")
    perm.add_to_blacklist(r"dangerous\s+thing")
    allowed, reason, _ = perm.check_permission("dangerous thing")
    print(f"   'dangerous thing' blacklisted: Allowed={allowed}")
    
    # Test 7: Emergency lock
    print("\n🔒 Test 7: Emergency Lock")
    perm.emergency_lock("Testing emergency mode")
    allowed, reason, _ = perm.check_permission("any command")
    print(f"   Command during lock: Allowed={allowed}, Reason={reason}")
    
    # Unlock
    perm.emergency_unlock("jarvis_admin")
    print(f"   Unlocked: {not perm.is_locked()}")
    
    # Test 8: Audit log
    print("\n📊 Test 8: Audit Log")
    audit = perm.get_audit_log(limit=5)
    print(f"   Audit entries: {len(audit)}")
    for entry in audit[:3]:
        print(f"     - {entry['action'][:30]}... Allowed: {entry['allowed']}")
    
    # Test 9: Audit stats
    print("\n📈 Test 9: Audit Statistics")
    stats = perm.get_audit_stats()
    print(f"   Total: {stats['total']}")
    print(f"   Allowed: {stats['allowed']}")
    print(f"   Denied: {stats['denied']}")
    print(f"   Denial rate: {stats['denial_rate']:.1f}%")
    
    # Test 10: Status
    print("\n📋 Test 10: System Status")
    status = perm.get_status()
    print(f"   Permission level: {status['permission_level']}")
    print(f"   Emergency locked: {status['emergency_locked']}")
    print(f"   Rules: {status['rules_count']}")
    print(f"   Audit entries: {status['audit_entries']}")
    
    print("\n" + "=" * 60)
    print("✅ Permission System tests complete!")
