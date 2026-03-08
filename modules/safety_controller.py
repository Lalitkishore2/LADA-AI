# safety_controller.py
# Safety Layer with Privacy Mode, Undo, Confirmation, and Audit Logging

import json
import logging
from typing import Dict, List, Any, Tuple, Callable
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, asdict
import hashlib
import sqlite3

logger = logging.getLogger(__name__)


class ActionSeverity(Enum):
    """Action severity levels"""
    SAFE = "safe"  # No confirmation needed
    WARNING = "warning"  # Show warning
    DANGEROUS = "dangerous"  # Require confirmation
    CRITICAL = "critical"  # Require PIN + confirmation


class PrivacyLevel(Enum):
    """Privacy levels"""
    PUBLIC = "public"  # Log everything
    PRIVATE = "private"  # Don't log commands
    SECURE = "secure"  # Require PIN for actions


@dataclass
class AuditLog:
    """Audit log entry"""
    timestamp: str
    action: str
    parameters: Dict[str, Any]
    result: str
    user: str = "system"
    severity: str = "normal"
    ip_address: str = None
    
    def to_dict(self):
        return asdict(self)


@dataclass
class UndoAction:
    """Reversible action for undo"""
    action_id: str
    action_type: str
    original_state: Dict[str, Any]
    reverse_function: Callable
    timestamp: str
    description: str


class SensitiveDataDetector:
    """Detect sensitive information in text"""
    
    PATTERNS = {
        'password': [
            r'(?:password|pwd|pass)\s*[:=]\s*[^\s]+',
            r'password["\']?\s*[:=]\s*["\']?([^"\']+)["\']?',
        ],
        'credit_card': [
            r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
            r'\b\d{4}\s\d{4}\s\d{4}\s\d{4}\b',
        ],
        'ssn': [
            r'\b\d{3}-\d{2}-\d{4}\b',
        ],
        'email': [
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        ],
        'phone': [
            r'\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b',
        ],
        'bank_account': [
            r'(?:account|acct|iban)\s*[:=]\s*[a-zA-Z0-9]{8,34}',
        ],
        'api_key': [
            r'(?:api[_-]?key|token|secret)\s*[:=]\s*[a-zA-Z0-9_-]{20,}',
        ],
        'ssn_alt': [
            r'\b\d{3}\s\d{2}\s\d{4}\b',
        ],
    }
    
    @classmethod
    def detect(cls, text: str) -> Dict[str, List[str]]:
        """Detect sensitive data in text"""
        import re
        found = {}
        for data_type, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    if data_type not in found:
                        found[data_type] = []
                    found[data_type].extend(matches)
        
        return {k: list(set(v)) for k, v in found.items()}
    
    @classmethod
    def redact(cls, text: str) -> str:
        """Replace sensitive data with [REDACTED]"""
        import re
        redacted = text
        for data_type, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                redacted = re.sub(pattern, f'[REDACTED-{data_type.upper()}]', redacted, flags=re.IGNORECASE)
        return redacted
    
    @classmethod
    def is_sensitive(cls, text: str) -> bool:
        """Check if text contains sensitive data"""
        return len(cls.detect(text)) > 0


class SafetyController:
    """Safety layer with privacy, undo, confirmation, and audit logging"""
    
    # Commands that require confirmation
    DANGEROUS_COMMANDS = {
        'delete_file': ActionSeverity.DANGEROUS,
        'delete_folder': ActionSeverity.DANGEROUS,
        'format_drive': ActionSeverity.CRITICAL,
        'delete_system_files': ActionSeverity.CRITICAL,
        'modify_registry': ActionSeverity.DANGEROUS,
        'disable_antivirus': ActionSeverity.CRITICAL,
        'uninstall_driver': ActionSeverity.DANGEROUS,
        'system_shutdown': ActionSeverity.WARNING,
        'password_change': ActionSeverity.DANGEROUS,
    }
    
    # Commands that are blacklisted
    BLACKLIST_COMMANDS = {
        'format_c_drive',
        'delete_system32',
        'disable_windows_defender',
        'remove_boot_files',
        'factory_reset_system',
    }
    
    def __init__(self, db_path: str = "jarvis_audit.db"):
        """Initialize safety controller"""
        self.privacy_mode = PrivacyLevel.PUBLIC
        self.security_pin = None
        self.security_pin_hash = None
        self.undo_stack = []
        self.max_undo_history = 50
        self.audit_db_path = db_path
        self.sensitive_detector = SensitiveDataDetector()
        
        # Initialize audit database
        self._init_audit_db()
    
    def _init_audit_db(self):
        """Initialize SQLite audit database"""
        try:
            conn = sqlite3.connect(self.audit_db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    parameters TEXT,
                    result TEXT,
                    user TEXT,
                    severity TEXT,
                    ip_address TEXT,
                    sensitive_data BOOLEAN DEFAULT 0
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS undo_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_id TEXT UNIQUE,
                    action_type TEXT,
                    original_state TEXT,
                    timestamp TEXT,
                    description TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("Audit database initialized")
        
        except Exception as e:
            logger.error(f"Error initializing audit database: {e}")
    
    def set_privacy_mode(self, mode: PrivacyLevel, pin: str = None) -> Dict[str, Any]:
        """
        Set privacy mode
        
        Args:
            mode: PUBLIC, PRIVATE, or SECURE
            pin: Security PIN for SECURE mode
        """
        if mode == PrivacyLevel.SECURE and not pin:
            return {'success': False, 'error': 'PIN required for SECURE mode'}
        
        if pin:
            self.security_pin_hash = hashlib.sha256(pin.encode()).hexdigest()
        
        self.privacy_mode = mode
        logger.info(f"Privacy mode set to: {mode.value}")
        
        return {
            'success': True,
            'privacy_mode': mode.value,
            'message': f"Privacy mode set to {mode.value}"
        }
    
    def check_permission(self, 
                        command: str, 
                        parameters: Dict = None) -> Dict[str, Any]:
        """
        Check if command is allowed and what confirmation is needed
        
        Returns:
            {
                'allowed': True/False,
                'requires_confirmation': True/False,
                'severity': 'safe',
                'reason': 'This will delete files',
                'preview': 'Will delete: file.txt'
            }
        """
        parameters = parameters or {}
        
        # Check if blacklisted
        if command in self.BLACKLIST_COMMANDS:
            return {
                'allowed': False,
                'requires_confirmation': False,
                'severity': ActionSeverity.CRITICAL.value,
                'reason': f'Command is blacklisted: {command}',
                'preview': None
            }
        
        # Get severity
        severity = self.DANGEROUS_COMMANDS.get(command, ActionSeverity.SAFE)
        
        # Check if SECURE mode requires PIN
        if self.privacy_mode == PrivacyLevel.SECURE and severity.value != ActionSeverity.SAFE.value:
            return {
                'allowed': True,
                'requires_confirmation': True,
                'requires_pin': True,
                'severity': severity.value,
                'reason': 'PIN required in SECURE mode',
                'preview': str(parameters)
            }
        
        return {
            'allowed': True,
            'requires_confirmation': severity == ActionSeverity.DANGEROUS or severity == ActionSeverity.CRITICAL,
            'severity': severity.value,
            'reason': f'Action requires {severity.value} confirmation' if severity != ActionSeverity.SAFE else None,
            'preview': str(parameters) if severity == ActionSeverity.DANGEROUS or severity == ActionSeverity.CRITICAL else None
        }
    
    def confirm_action(self, 
                      action_id: str,
                      user_confirmation: bool,
                      pin: str = None) -> Dict[str, Any]:
        """
        Confirm potentially dangerous action
        
        Args:
            action_id: ID of the action to confirm
            user_confirmation: User's confirmation (yes/no)
            pin: Security PIN if required
        
        Returns:
            {'allowed': True/False, 'reason': '...'}
        """
        if not user_confirmation:
            logger.warning(f"User rejected action: {action_id}")
            return {'allowed': False, 'reason': 'Action cancelled by user'}
        
        # Verify PIN if set
        if pin and self.security_pin_hash:
            pin_hash = hashlib.sha256(pin.encode()).hexdigest()
            if pin_hash != self.security_pin_hash:
                return {'allowed': False, 'reason': 'Incorrect PIN'}
        
        return {'allowed': True, 'reason': 'Action confirmed'}
    
    def log_action(self,
                  action: str,
                  parameters: Dict = None,
                  result: str = None,
                  severity: str = "normal") -> Dict[str, Any]:
        """
        Log action to audit database
        
        Only logs if not in PRIVATE mode or if data not sensitive
        """
        parameters = parameters or {}
        
        # Check for sensitive data
        has_sensitive_data = self.sensitive_detector.is_sensitive(str(parameters))
        
        # Skip logging if PRIVATE mode and has sensitive data
        if self.privacy_mode == PrivacyLevel.PRIVATE and has_sensitive_data:
            logger.info(f"Skipping log (PRIVATE mode): {action}")
            return {'logged': False, 'reason': 'Private mode enabled'}
        
        try:
            conn = sqlite3.connect(self.audit_db_path)
            cursor = conn.cursor()
            
            # Redact if sensitive
            redacted_params = self.sensitive_detector.redact(str(parameters))
            
            cursor.execute('''
                INSERT INTO audit_log 
                (timestamp, action, parameters, result, user, severity, sensitive_data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().isoformat(),
                action,
                redacted_params,
                result,
                "user",
                severity,
                1 if has_sensitive_data else 0
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Action logged: {action}")
            return {
                'logged': True,
                'action': action,
                'timestamp': datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error logging action: {e}")
            return {'logged': False, 'error': str(e)}
    
    def register_undo(self,
                     action_id: str,
                     action_type: str,
                     original_state: Dict,
                     reverse_function: Callable,
                     description: str) -> Dict[str, Any]:
        """
        Register an action that can be undone
        
        Args:
            action_id: Unique ID for the action
            action_type: Type of action (file_delete, file_move, etc.)
            original_state: State before action
            reverse_function: Function to reverse the action
            description: Human-readable description
        """
        try:
            # Add to in-memory stack
            undo_action = UndoAction(
                action_id=action_id,
                action_type=action_type,
                original_state=original_state,
                reverse_function=reverse_function,
                timestamp=datetime.now().isoformat(),
                description=description
            )
            
            self.undo_stack.append(undo_action)
            
            # Trim stack if too large
            if len(self.undo_stack) > self.max_undo_history:
                self.undo_stack = self.undo_stack[-self.max_undo_history:]
            
            # Save to database
            conn = sqlite3.connect(self.audit_db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO undo_history 
                (action_id, action_type, original_state, timestamp, description)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                action_id,
                action_type,
                json.dumps(original_state),
                undo_action.timestamp,
                description
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Undo registered: {action_id} - {description}")
            return {
                'success': True,
                'action_id': action_id,
                'description': description
            }
        
        except Exception as e:
            logger.error(f"Error registering undo: {e}")
            return {'success': False, 'error': str(e)}
    
    def undo_last_action(self) -> Dict[str, Any]:
        """Undo the most recent action"""
        if not self.undo_stack:
            return {
                'success': False,
                'error': 'No actions to undo',
                'available_actions': 0
            }
        
        try:
            undo_action = self.undo_stack.pop()
            
            # Execute reverse function
            result = undo_action.reverse_function(undo_action.original_state)
            
            logger.info(f"Undo executed: {undo_action.description}")
            
            # Remove from database
            conn = sqlite3.connect(self.audit_db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM undo_history WHERE action_id = ?', (undo_action.action_id,))
            conn.commit()
            conn.close()
            
            return {
                'success': True,
                'action': undo_action.description,
                'available_actions': len(self.undo_stack)
            }
        
        except Exception as e:
            logger.error(f"Error undoing action: {e}")
            return {
                'success': False,
                'error': str(e),
                'available_actions': len(self.undo_stack)
            }
    
    def get_undo_history(self, limit: int = 10) -> Dict[str, Any]:
        """Get list of recent undoable actions"""
        try:
            conn = sqlite3.connect(self.audit_db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT action_id, action_type, description, timestamp
                FROM undo_history
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (limit,))
            
            actions = []
            for row in cursor.fetchall():
                actions.append({
                    'action_id': row[0],
                    'action_type': row[1],
                    'description': row[2],
                    'timestamp': row[3]
                })
            
            conn.close()
            
            return {
                'success': True,
                'total_available': len(self.undo_stack),
                'recent_actions': actions
            }
        
        except Exception as e:
            logger.error(f"Error getting undo history: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_audit_log(self, 
                     action_filter: str = None,
                     start_date: datetime = None,
                     end_date: datetime = None,
                     limit: int = 100) -> Dict[str, Any]:
        """Get audit log with optional filters"""
        try:
            conn = sqlite3.connect(self.audit_db_path)
            cursor = conn.cursor()
            
            query = 'SELECT timestamp, action, parameters, result, severity FROM audit_log WHERE 1=1'
            params = []
            
            if action_filter:
                query += ' AND action LIKE ?'
                params.append(f'%{action_filter}%')
            
            if start_date:
                query += ' AND timestamp >= ?'
                params.append(start_date.isoformat())
            
            if end_date:
                query += ' AND timestamp <= ?'
                params.append(end_date.isoformat())
            
            query += ' ORDER BY timestamp DESC LIMIT ?'
            params.append(limit)
            
            cursor.execute(query, params)
            
            logs = []
            for row in cursor.fetchall():
                logs.append({
                    'timestamp': row[0],
                    'action': row[1],
                    'parameters': row[2],
                    'result': row[3],
                    'severity': row[4]
                })
            
            conn.close()
            
            return {
                'success': True,
                'total_logs': len(logs),
                'logs': logs
            }
        
        except Exception as e:
            logger.error(f"Error getting audit log: {e}")
            return {'success': False, 'error': str(e)}
    
    def export_audit_log(self, export_path: str, encrypted: bool = True) -> Dict[str, Any]:
        """Export audit log to file (optionally encrypted)"""
        try:
            result = self.get_audit_log(limit=10000)
            
            if not result['success']:
                return result
            
            export_file = Path(export_path)
            export_file.parent.mkdir(parents=True, exist_ok=True)
            
            if encrypted:
                # Simple encryption with password
                from cryptography.fernet import Fernet
                key = Fernet.generate_key()
                cipher = Fernet(key)
                
                data = json.dumps(result['logs']).encode()
                encrypted_data = cipher.encrypt(data)
                
                # Save encrypted data and key separately
                with open(export_file, 'wb') as f:
                    f.write(encrypted_data)
                
                with open(export_file.with_suffix('.key'), 'wb') as f:
                    f.write(key)
            else:
                with open(export_file, 'w') as f:
                    json.dump(result['logs'], f, indent=2)
            
            logger.info(f"Audit log exported to: {export_file}")
            return {
                'success': True,
                'export_path': str(export_file),
                'encrypted': encrypted,
                'records': len(result['logs'])
            }
        
        except Exception as e:
            logger.error(f"Error exporting audit log: {e}")
            return {'success': False, 'error': str(e)}


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    safety = SafetyController()
    
    # Set privacy mode
    result = safety.set_privacy_mode(PrivacyLevel.PUBLIC)
    print("Set privacy:", result)
    
    # Check permission
    result = safety.check_permission('delete_file', {'file': 'test.txt'})
    print("Permission check:", result)
    
    # Log action
    result = safety.log_action('delete_file', {'file': 'test.txt'}, 'deleted successfully')
    print("Logged:", result)
    
    # Get audit log
    result = safety.get_audit_log(limit=5)
    print("Audit log entries:", result['total_logs'])
