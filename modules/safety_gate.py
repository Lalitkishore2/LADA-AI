"""
LADA v7.0 - Safety Gate System
Permission control and action logging for browser automation
"""

import os
import json
import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk levels for actions."""
    LOW = "low"       # Auto-approve (navigation, screenshots)
    MEDIUM = "medium" # Ask once, remember choice
    HIGH = "high"     # Always ask (payments, submissions)


class SafetyGate:
    """
    Permission and safety system for automated browser actions.
    Prevents accidental payments, form submissions, and other risky operations.
    """
    
    def __init__(self, ui_callback: Optional[Callable] = None, data_dir: str = None):
        """
        Initialize safety gate.
        
        Args:
            ui_callback: Optional callback for UI permission dialogs
                         signature: callback(message, risk_level) -> bool
            data_dir: Directory for storing permissions and logs
        """
        self.ui_callback = ui_callback
        self.data_dir = data_dir or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'data'
        )
        os.makedirs(self.data_dir, exist_ok=True)
        
        self.permissions_file = os.path.join(self.data_dir, 'permissions.json')
        self.action_log_file = os.path.join(self.data_dir, 'action_log.json')
        
        self.permissions = self._load_permissions()
        self.session_permissions: Dict[str, bool] = {}  # Temporary session permissions
        
        # Keywords that indicate different risk levels
        self.high_risk_keywords = [
            'pay', 'payment', 'book', 'booking', 'purchase', 'buy',
            'submit', 'confirm', 'checkout', 'credit card', 'debit card',
            'password', 'login', 'sign in', 'bank', 'transfer', 'order'
        ]
        
        self.medium_risk_keywords = [
            'form', 'fill', 'enter', 'input', 'add to cart', 'select',
            'subscribe', 'register', 'sign up', 'email', 'phone'
        ]
    
    def _load_permissions(self) -> Dict:
        """Load saved permissions from file."""
        try:
            if os.path.exists(self.permissions_file):
                with open(self.permissions_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load permissions: {e}")
        return {"allowed": [], "blocked": [], "preferences": {}}
    
    def _save_permissions(self):
        """Save permissions to file."""
        try:
            with open(self.permissions_file, 'w') as f:
                json.dump(self.permissions, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save permissions: {e}")
    
    def classify_risk(self, action_description: str) -> RiskLevel:
        """
        Classify risk level of an action.
        
        Args:
            action_description: Human-readable description of the action
            
        Returns:
            RiskLevel enum value
        """
        desc_lower = action_description.lower()
        
        # Check for high risk keywords
        for keyword in self.high_risk_keywords:
            if keyword in desc_lower:
                return RiskLevel.HIGH
        
        # Check for medium risk keywords
        for keyword in self.medium_risk_keywords:
            if keyword in desc_lower:
                return RiskLevel.MEDIUM
        
        return RiskLevel.LOW
    
    def is_safe(self, action_description: str, context: Optional[Dict] = None) -> bool:
        """
        Check if an action is safe without prompting.
        
        Args:
            action_description: Description of the action
            context: Optional additional context
            
        Returns:
            True if action is safe to proceed
        """
        risk = self.classify_risk(action_description)
        
        if risk == RiskLevel.LOW:
            return True
        
        # Check if we've already approved this action type
        action_key = self._get_action_key(action_description)
        if action_key in self.permissions.get('allowed', []):
            return True
        if action_key in self.permissions.get('blocked', []):
            return False
        
        # Check session permissions
        if action_key in self.session_permissions:
            return self.session_permissions[action_key]
        
        return False
    
    def ask_permission(self, action_description: str, risk_level: str = None,
                       context: Optional[Dict] = None) -> bool:
        """
        Ask user for permission to perform an action.
        
        Args:
            action_description: Human-readable description
            risk_level: Optional override for risk level ("low", "medium", "high")
            context: Optional additional context (amount, target, etc.)
            
        Returns:
            True if user approves
        """
        # Determine risk level
        if risk_level:
            risk = RiskLevel(risk_level)
        else:
            risk = self.classify_risk(action_description)
        
        # Auto-approve low risk
        if risk == RiskLevel.LOW:
            self.log_action(action_description, True, "auto-approved (low risk)")
            return True
        
        # Check existing permissions
        action_key = self._get_action_key(action_description)
        
        if action_key in self.permissions.get('allowed', []) and risk != RiskLevel.HIGH:
            self.log_action(action_description, True, "previously allowed")
            return True
        
        if action_key in self.permissions.get('blocked', []):
            self.log_action(action_description, False, "previously blocked")
            return False
        
        # Check session permissions for medium risk
        if risk == RiskLevel.MEDIUM and action_key in self.session_permissions:
            result = self.session_permissions[action_key]
            self.log_action(action_description, result, "session permission")
            return result
        
        # Need to ask user
        approved = self._prompt_user(action_description, risk, context)
        
        # Remember choice
        if risk == RiskLevel.MEDIUM:
            self.session_permissions[action_key] = approved
        
        self.log_action(action_description, approved, "user decision")
        return approved
    
    def _prompt_user(self, action_description: str, risk: RiskLevel,
                     context: Optional[Dict] = None) -> bool:
        """Prompt user for permission."""
        # Build message
        risk_emoji = {"low": "✅", "medium": "⚠️", "high": "🚨"}
        emoji = risk_emoji.get(risk.value, "❓")
        
        message = f"{emoji} Permission Required ({risk.value.upper()} RISK)\n\n"
        message += f"Action: {action_description}\n"
        
        if context:
            if 'amount' in context:
                message += f"Amount: ₹{context['amount']}\n"
            if 'target' in context:
                message += f"Target: {context['target']}\n"
        
        message += "\nDo you want to proceed?"
        
        # Use UI callback if available
        if self.ui_callback:
            try:
                return self.ui_callback(message, risk.value)
            except Exception as e:
                logger.error(f"UI callback failed: {e}")
        
        # Fallback to console prompt
        print("\n" + "=" * 50)
        print(message)
        print("=" * 50)
        
        try:
            response = input("Enter Y to approve, N to deny: ").strip().lower()
            return response in ['y', 'yes', 'ok', 'approve']
        except Exception:
            # Non-interactive mode - deny by default for safety
            logger.warning("Non-interactive mode - denying permission")
            return False
    
    def _get_action_key(self, action_description: str) -> str:
        """Generate a key for storing action permissions."""
        # Normalize description to create consistent key
        words = action_description.lower().split()
        # Keep only significant words
        significant = [w for w in words if len(w) > 3 and w not in ['the', 'and', 'for', 'with']]
        return "_".join(significant[:5])
    
    def remember_choice(self, action_description: str, allowed: bool, permanent: bool = False):
        """
        Remember user's permission choice.
        
        Args:
            action_description: Description of the action
            allowed: Whether to allow or block
            permanent: If True, save to file; otherwise session-only
        """
        action_key = self._get_action_key(action_description)
        
        if permanent:
            if allowed:
                if action_key not in self.permissions['allowed']:
                    self.permissions['allowed'].append(action_key)
                if action_key in self.permissions['blocked']:
                    self.permissions['blocked'].remove(action_key)
            else:
                if action_key not in self.permissions['blocked']:
                    self.permissions['blocked'].append(action_key)
                if action_key in self.permissions['allowed']:
                    self.permissions['allowed'].remove(action_key)
            self._save_permissions()
        else:
            self.session_permissions[action_key] = allowed
    
    def log_action(self, action: str, approved: bool, reason: str, result: str = None):
        """
        Log an action for auditing.
        
        Args:
            action: Description of the action
            approved: Whether it was approved
            reason: Why it was approved/denied
            result: Optional result of the action
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "approved": approved,
            "reason": reason,
            "result": result
        }
        
        # Append to log file
        try:
            logs = []
            if os.path.exists(self.action_log_file):
                with open(self.action_log_file, 'r') as f:
                    logs = json.load(f)
            
            logs.append(log_entry)
            
            # Keep only last 1000 entries
            if len(logs) > 1000:
                logs = logs[-1000:]
            
            with open(self.action_log_file, 'w') as f:
                json.dump(logs, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to log action: {e}")
        
        # Also log to console
        status = "✅ APPROVED" if approved else "❌ DENIED"
        logger.info(f"{status}: {action} ({reason})")
    
    def get_action_log(self, limit: int = 50) -> list:
        """Get recent action log entries."""
        try:
            if os.path.exists(self.action_log_file):
                with open(self.action_log_file, 'r') as f:
                    logs = json.load(f)
                    return logs[-limit:]
        except Exception:
            pass
        return []
    
    def reset_permissions(self):
        """Reset all saved permissions."""
        self.permissions = {"allowed": [], "blocked": [], "preferences": {}}
        self.session_permissions = {}
        self._save_permissions()
        logger.info("🔄 All permissions reset")
    
    def execute_if_safe(self, action_description: str, context: Dict,
                        callback: Callable, risk_level: str = None) -> Dict[str, Any]:
        """
        Execute a callback if the action is approved.
        
        Args:
            action_description: Description of the action
            context: Context passed to callback
            callback: Function to execute if approved
            risk_level: Optional risk level override
            
        Returns:
            {"approved": bool, "result": any, "error": str}
        """
        approved = self.ask_permission(action_description, risk_level, context)
        
        if not approved:
            return {
                "approved": False,
                "result": None,
                "error": "User denied permission"
            }
        
        try:
            result = callback(context)
            self.log_action(action_description, True, "executed", str(result)[:200])
            return {
                "approved": True,
                "result": result,
                "error": None
            }
        except Exception as e:
            self.log_action(action_description, True, "execution failed", str(e))
            return {
                "approved": True,
                "result": None,
                "error": str(e)
            }


# ============================================================
# EXAMPLE USAGE
# ============================================================
if __name__ == "__main__":
    print("🚀 Testing SafetyGate...")
    
    gate = SafetyGate()
    
    # Test risk classification
    tests = [
        ("Navigate to Google Flights", "low"),
        ("Fill search form with Delhi", "medium"),
        ("Submit payment of ₹5000", "high"),
        ("Take screenshot", "low"),
        ("Click book now button", "high"),
        ("Enter email address", "medium"),
    ]
    
    print("\n📊 Risk Classification Tests:")
    for action, expected in tests:
        risk = gate.classify_risk(action)
        status = "✅" if risk.value == expected else "❌"
        print(f"  {status} '{action}' -> {risk.value} (expected: {expected})")
    
    # Test permission flow
    print("\n🔐 Permission Tests:")
    
    # Low risk - auto approve
    result = gate.is_safe("Navigate to Google")
    print(f"  Low risk auto-approve: {result}")
    
    # High risk - needs permission
    result = gate.is_safe("Submit payment")
    print(f"  High risk without permission: {result}")
    
    # Check action log
    print("\n📝 Action Log (last 5):")
    for entry in gate.get_action_log(5):
        print(f"  {entry['timestamp']}: {entry['action']} - {'✅' if entry['approved'] else '❌'}")
    
    print("\n✅ SafetyGate test complete!")
