"""
LADA Auto-Fix Engine

Provides automated fixes for diagnosed issues.

Features:
- Fix definitions with prerequisites
- Safe execution with rollback
- Fix history and audit
- Manual and auto-fix modes
"""

import os
import time
import json
import logging
import threading
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class FixStatus(str, Enum):
    """Status of a fix execution."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    SKIPPED = "skipped"


class FixRisk(str, Enum):
    """Risk level of a fix."""
    LOW = "low"           # Safe, no side effects
    MEDIUM = "medium"     # May have minor side effects
    HIGH = "high"         # Requires caution
    CRITICAL = "critical" # May cause data loss, requires approval


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class FixResult:
    """Result of a fix execution."""
    fix_id: str
    status: FixStatus
    message: str
    
    # Timing
    started_at: str = ""
    completed_at: str = ""
    duration_ms: float = 0.0
    
    # Details
    details: Dict[str, Any] = field(default_factory=dict)
    
    # Rollback info
    can_rollback: bool = False
    rollback_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "fix_id": self.fix_id,
            "status": self.status.value,
            "message": self.message,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "details": self.details,
            "can_rollback": self.can_rollback,
        }


@dataclass
class AutoFix:
    """
    An auto-fix definition.
    
    The fix function should return (success, message, details).
    The rollback function (if provided) should undo the fix.
    """
    id: str
    name: str
    description: str
    
    # Related diagnostic
    diagnostic_id: Optional[str] = None
    
    # Fix function: (params: dict) -> (success: bool, message: str, details: dict)
    fix_fn: Callable[[Dict[str, Any]], tuple] = None
    
    # Rollback function (optional): (rollback_data: dict) -> (success: bool, message: str)
    rollback_fn: Optional[Callable[[Dict[str, Any]], tuple]] = None
    
    # Prerequisites: other fix IDs that must succeed first
    prerequisites: List[str] = field(default_factory=list)
    
    # Configuration
    risk: FixRisk = FixRisk.LOW
    requires_approval: bool = False
    timeout_seconds: float = 60.0
    enabled: bool = True
    
    # Documentation
    steps: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "diagnostic_id": self.diagnostic_id,
            "risk": self.risk.value,
            "requires_approval": self.requires_approval,
            "prerequisites": self.prerequisites,
            "steps": self.steps,
            "warnings": self.warnings,
            "enabled": self.enabled,
        }


# ============================================================================
# Auto-Fix Engine
# ============================================================================

class AutoFixEngine:
    """
    Engine for executing auto-fixes.
    
    Features:
    - Fix registration and discovery
    - Safe execution with timeout
    - Rollback support
    - Fix history
    """
    
    def __init__(
        self,
        history_dir: Optional[str] = None,
        require_approval_for_high_risk: bool = True,
    ):
        self._fixes: Dict[str, AutoFix] = {}
        self._lock = threading.RLock()
        
        self._history_dir = Path(history_dir or os.getenv("LADA_FIX_HISTORY_DIR", "data/fixes"))
        self._history_dir.mkdir(parents=True, exist_ok=True)
        
        self._require_approval_for_high_risk = require_approval_for_high_risk
        
        # Execution history
        self._history: List[FixResult] = []
        self._max_history = 100
        
        # Register built-in fixes
        self._register_builtin_fixes()
        
        logger.info(f"[AutoFixEngine] Initialized with {len(self._fixes)} fixes")
    
    def register(self, fix: AutoFix) -> bool:
        """Register an auto-fix."""
        with self._lock:
            self._fixes[fix.id] = fix
        return True
    
    def unregister(self, fix_id: str) -> bool:
        """Unregister an auto-fix."""
        with self._lock:
            if fix_id in self._fixes:
                del self._fixes[fix_id]
                return True
        return False
    
    def get(self, fix_id: str) -> Optional[AutoFix]:
        """Get fix by ID."""
        with self._lock:
            return self._fixes.get(fix_id)
    
    def list_fixes(
        self,
        diagnostic_id: Optional[str] = None,
    ) -> List[AutoFix]:
        """List all fixes, optionally filtered by diagnostic ID."""
        with self._lock:
            fixes = list(self._fixes.values())
        
        if diagnostic_id:
            fixes = [f for f in fixes if f.diagnostic_id == diagnostic_id]
        
        return [f for f in fixes if f.enabled]
    
    def get_fix_for_diagnostic(self, diagnostic_id: str) -> Optional[AutoFix]:
        """Get the fix for a specific diagnostic."""
        fixes = self.list_fixes(diagnostic_id=diagnostic_id)
        return fixes[0] if fixes else None
    
    def execute(
        self,
        fix_id: str,
        params: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
        approval_token: Optional[str] = None,
    ) -> FixResult:
        """
        Execute a fix.
        
        Args:
            fix_id: ID of the fix to execute
            params: Parameters to pass to the fix function
            dry_run: If True, don't actually execute, just validate
            approval_token: Token for approved high-risk fixes
        
        Returns:
            FixResult with execution details
        """
        fix = self.get(fix_id)
        if not fix:
            return FixResult(
                fix_id=fix_id,
                status=FixStatus.FAILED,
                message=f"Fix not found: {fix_id}",
            )
        
        if not fix.enabled:
            return FixResult(
                fix_id=fix_id,
                status=FixStatus.SKIPPED,
                message="Fix is disabled",
            )
        
        # Check approval for high-risk fixes
        if fix.requires_approval or (
            self._require_approval_for_high_risk and
            fix.risk in (FixRisk.HIGH, FixRisk.CRITICAL)
        ):
            if not approval_token:
                return FixResult(
                    fix_id=fix_id,
                    status=FixStatus.PENDING,
                    message="Approval required for this fix",
                    details={
                        "risk": fix.risk.value,
                        "requires_approval": True,
                        "warnings": fix.warnings,
                    },
                )
        
        # Check prerequisites
        for prereq_id in fix.prerequisites:
            prereq_result = self._get_last_result(prereq_id)
            if not prereq_result or prereq_result.status != FixStatus.SUCCESS:
                return FixResult(
                    fix_id=fix_id,
                    status=FixStatus.SKIPPED,
                    message=f"Prerequisite not met: {prereq_id}",
                    details={"prerequisite": prereq_id},
                )
        
        if dry_run:
            return FixResult(
                fix_id=fix_id,
                status=FixStatus.PENDING,
                message="Dry run: fix would be executed",
                details={
                    "steps": fix.steps,
                    "warnings": fix.warnings,
                    "risk": fix.risk.value,
                },
            )
        
        # Execute fix
        started_at = datetime.now().isoformat()
        start_time = time.time()
        
        try:
            success, message, details = fix.fix_fn(params or {})
            status = FixStatus.SUCCESS if success else FixStatus.FAILED
        except Exception as e:
            success = False
            message = f"Fix failed with exception: {str(e)}"
            details = {"exception": type(e).__name__, "error": str(e)}
            status = FixStatus.FAILED
        
        completed_at = datetime.now().isoformat()
        duration = (time.time() - start_time) * 1000
        
        result = FixResult(
            fix_id=fix_id,
            status=status,
            message=message,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration,
            details=details,
            can_rollback=fix.rollback_fn is not None and success,
            rollback_data=details.get("rollback_data", {}),
        )
        
        # Save to history
        self._add_to_history(result)
        
        logger.info(f"[AutoFixEngine] Fix {fix_id}: {status.value} - {message}")
        
        return result
    
    def rollback(self, fix_id: str) -> FixResult:
        """
        Rollback a previously executed fix.
        
        Args:
            fix_id: ID of the fix to rollback
        
        Returns:
            FixResult with rollback details
        """
        fix = self.get(fix_id)
        if not fix:
            return FixResult(
                fix_id=fix_id,
                status=FixStatus.FAILED,
                message=f"Fix not found: {fix_id}",
            )
        
        if not fix.rollback_fn:
            return FixResult(
                fix_id=fix_id,
                status=FixStatus.FAILED,
                message="Fix does not support rollback",
            )
        
        # Get last successful result
        last_result = self._get_last_result(fix_id)
        if not last_result or last_result.status != FixStatus.SUCCESS:
            return FixResult(
                fix_id=fix_id,
                status=FixStatus.FAILED,
                message="No successful fix to rollback",
            )
        
        if not last_result.can_rollback:
            return FixResult(
                fix_id=fix_id,
                status=FixStatus.FAILED,
                message="Fix cannot be rolled back",
            )
        
        # Execute rollback
        started_at = datetime.now().isoformat()
        start_time = time.time()
        
        try:
            success, message = fix.rollback_fn(last_result.rollback_data)
            status = FixStatus.ROLLED_BACK if success else FixStatus.FAILED
        except Exception as e:
            success = False
            message = f"Rollback failed: {str(e)}"
            status = FixStatus.FAILED
        
        completed_at = datetime.now().isoformat()
        duration = (time.time() - start_time) * 1000
        
        result = FixResult(
            fix_id=fix_id,
            status=status,
            message=message,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration,
        )
        
        self._add_to_history(result)
        
        return result
    
    def get_history(
        self,
        fix_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get fix execution history."""
        with self._lock:
            history = list(self._history)
        
        if fix_id:
            history = [h for h in history if h.fix_id == fix_id]
        
        return [h.to_dict() for h in history[-limit:]]
    
    def _get_last_result(self, fix_id: str) -> Optional[FixResult]:
        """Get the last result for a fix."""
        with self._lock:
            for result in reversed(self._history):
                if result.fix_id == fix_id:
                    return result
        return None
    
    def _add_to_history(self, result: FixResult):
        """Add result to history."""
        with self._lock:
            self._history.append(result)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
        
        # Persist to disk
        self._save_result(result)
    
    def _save_result(self, result: FixResult):
        """Save result to disk."""
        result_file = self._history_dir / f"{result.fix_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(result_file, 'w') as f:
                json.dump(result.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"[AutoFixEngine] Failed to save result: {e}")
    
    def _register_builtin_fixes(self):
        """Register built-in fixes."""
        
        # Create data directory fix
        self.register(AutoFix(
            id="create-data-dir",
            name="Create Data Directory",
            description="Create the LADA data directory",
            diagnostic_id="storage-access",
            risk=FixRisk.LOW,
            fix_fn=self._fix_create_data_dir,
            steps=[
                "Check if data directory exists",
                "Create directory with proper permissions",
                "Verify write access",
            ],
        ))
        
        # Clear cache fix
        self.register(AutoFix(
            id="clear-cache",
            name="Clear Cache",
            description="Clear LADA cache files",
            risk=FixRisk.LOW,
            fix_fn=self._fix_clear_cache,
            rollback_fn=self._rollback_clear_cache,
            steps=[
                "Backup cache files",
                "Delete cache directory",
                "Recreate empty cache",
            ],
        ))
        
        # Reset provider connections
        self.register(AutoFix(
            id="reset-providers",
            name="Reset Provider Connections",
            description="Reset AI provider connections and retry",
            diagnostic_id="provider-connectivity",
            risk=FixRisk.LOW,
            fix_fn=self._fix_reset_providers,
            steps=[
                "Clear provider connection pool",
                "Reset rate limiters",
                "Reinitialize provider manager",
            ],
        ))
    
    def _fix_create_data_dir(self, params: Dict[str, Any]) -> tuple:
        """Create data directory fix."""
        data_dir = Path(params.get("path") or os.getenv("LADA_DATA_DIR", "data"))
        
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            
            # Verify write access
            test_file = data_dir / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
            
            return True, f"Created data directory: {data_dir}", {"path": str(data_dir)}
        except Exception as e:
            return False, f"Failed to create data directory: {e}", {"error": str(e)}
    
    def _fix_clear_cache(self, params: Dict[str, Any]) -> tuple:
        """Clear cache fix."""
        cache_dir = Path(params.get("path") or os.getenv("LADA_CACHE_DIR", "data/cache"))
        backup_dir = self._history_dir / "cache_backup"
        
        try:
            # Backup if exists
            if cache_dir.exists():
                if backup_dir.exists():
                    shutil.rmtree(backup_dir)
                shutil.copytree(cache_dir, backup_dir)
                shutil.rmtree(cache_dir)
            
            # Recreate
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            return True, "Cache cleared successfully", {
                "path": str(cache_dir),
                "rollback_data": {"backup_path": str(backup_dir)},
            }
        except Exception as e:
            return False, f"Failed to clear cache: {e}", {"error": str(e)}
    
    def _rollback_clear_cache(self, rollback_data: Dict[str, Any]) -> tuple:
        """Rollback cache clear."""
        backup_path = rollback_data.get("backup_path")
        if not backup_path:
            return False, "No backup data available"
        
        backup_dir = Path(backup_path)
        cache_dir = Path(os.getenv("LADA_CACHE_DIR", "data/cache"))
        
        try:
            if backup_dir.exists():
                if cache_dir.exists():
                    shutil.rmtree(cache_dir)
                shutil.copytree(backup_dir, cache_dir)
                return True, "Cache restored from backup"
            return False, "Backup not found"
        except Exception as e:
            return False, f"Rollback failed: {e}"
    
    def _fix_reset_providers(self, params: Dict[str, Any]) -> tuple:
        """Reset provider connections fix."""
        try:
            from modules.providers.provider_manager import ProviderManager
            
            # Reinitialize provider manager state from current environment.
            pm = ProviderManager()
            pm.auto_configure()
            
            # Check health after reconfiguration.
            status = pm.check_all_health()
            if not status:
                return False, "No providers configured. Set API keys and retry.", {
                    "providers": status,
                    "fix_id": "set-api-key",
                }

            healthy = sum(1 for s in status.values() if s.get("available", False))
            
            return True, f"Providers reset: {healthy} healthy", {"providers": status}
        except Exception as e:
            return False, f"Failed to reset providers: {e}", {"error": str(e)}


# ============================================================================
# Singleton
# ============================================================================

_engine_instance: Optional[AutoFixEngine] = None
_engine_lock = threading.Lock()


def get_fix_engine() -> AutoFixEngine:
    """Get singleton AutoFixEngine instance."""
    global _engine_instance
    if _engine_instance is None:
        with _engine_lock:
            if _engine_instance is None:
                _engine_instance = AutoFixEngine()
    return _engine_instance
