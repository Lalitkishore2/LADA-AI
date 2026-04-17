"""
LADA Task Maintenance

Handles task system maintenance operations:
- Startup reconciliation (reset stale tasks)
- Expired token cleanup
- History pruning
- Health monitoring
- Metrics collection
"""

import os
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass

from modules.tasks.task_registry import (
    TaskRegistry,
    TaskStatus,
    get_registry,
)

from modules.tasks.task_flow_registry import (
    TaskFlowRegistry,
    FlowStatus,
    get_flow_registry,
)

logger = logging.getLogger(__name__)


@dataclass
class MaintenanceStats:
    """Statistics from maintenance run."""
    stale_tasks_reset: int = 0
    expired_tokens_cleaned: int = 0
    completed_tasks_archived: int = 0
    flows_reconciled: int = 0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "stale_tasks_reset": self.stale_tasks_reset,
            "expired_tokens_cleaned": self.expired_tokens_cleaned,
            "completed_tasks_archived": self.completed_tasks_archived,
            "flows_reconciled": self.flows_reconciled,
            "errors": self.errors,
        }


@dataclass
class HealthStatus:
    """Task system health status."""
    healthy: bool = True
    total_tasks: int = 0
    active_tasks: int = 0
    paused_tasks: int = 0
    failed_tasks_24h: int = 0
    total_flows: int = 0
    active_flows: int = 0
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "healthy": self.healthy,
            "total_tasks": self.total_tasks,
            "active_tasks": self.active_tasks,
            "paused_tasks": self.paused_tasks,
            "failed_tasks_24h": self.failed_tasks_24h,
            "total_flows": self.total_flows,
            "active_flows": self.active_flows,
            "warnings": self.warnings,
        }


class TaskMaintenance:
    """
    Task system maintenance manager.
    
    Handles:
    - Startup reconciliation
    - Periodic cleanup
    - Health monitoring
    """
    
    DEFAULT_CLEANUP_INTERVAL = 3600  # 1 hour
    DEFAULT_ARCHIVE_AGE_HOURS = 24
    
    def __init__(
        self,
        task_registry: Optional[TaskRegistry] = None,
        flow_registry: Optional[TaskFlowRegistry] = None,
        cleanup_interval: int = None,
        archive_age_hours: int = None,
    ):
        self._task_registry = task_registry or get_registry()
        self._flow_registry = flow_registry or get_flow_registry()
        
        self._cleanup_interval = cleanup_interval or int(
            os.getenv("LADA_TASK_CLEANUP_INTERVAL", self.DEFAULT_CLEANUP_INTERVAL)
        )
        self._archive_age_hours = archive_age_hours or int(
            os.getenv("LADA_TASK_ARCHIVE_AGE_HOURS", self.DEFAULT_ARCHIVE_AGE_HOURS)
        )
        
        # Background cleanup
        self._cleanup_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Metrics
        self._last_maintenance: Optional[datetime] = None
        self._last_stats: Optional[MaintenanceStats] = None
        
        logger.info(f"[TaskMaintenance] Initialized (cleanup every {self._cleanup_interval}s)")
    
    # ========================================================================
    # Startup
    # ========================================================================
    
    def startup_reconcile(self) -> MaintenanceStats:
        """
        Reconcile task state after system restart.
        
        - Reset stale RUNNING tasks to PENDING
        - Cancel expired paused/approval tasks
        - Sync flow status with underlying tasks
        """
        stats = MaintenanceStats()
        
        try:
            # Reconcile task registry
            task_counts = self._task_registry.reconcile()
            stats.stale_tasks_reset = task_counts.get("stale_reset", 0)
            stats.expired_tokens_cleaned = task_counts.get("expired_cancelled", 0)
            
            # Reconcile flow statuses
            stats.flows_reconciled = self._reconcile_flows()
            
            logger.info(f"[TaskMaintenance] Startup reconciliation complete: {stats.to_dict()}")
            
        except Exception as e:
            stats.errors.append(f"Reconciliation error: {e}")
            logger.error(f"[TaskMaintenance] Startup reconciliation failed: {e}")
        
        self._last_maintenance = datetime.now()
        self._last_stats = stats
        return stats
    
    def _reconcile_flows(self) -> int:
        """Sync flow status with underlying task status."""
        reconciled = 0
        
        for flow in self._flow_registry.list_flows():
            task = self._task_registry.get(flow.id)
            if not task:
                continue
            
            # Map task status to flow status
            status_map = {
                TaskStatus.PENDING: FlowStatus.PENDING,
                TaskStatus.QUEUED: FlowStatus.PENDING,
                TaskStatus.RUNNING: FlowStatus.RUNNING,
                TaskStatus.COMPLETED: FlowStatus.COMPLETED,
                TaskStatus.FAILED: FlowStatus.FAILED,
                TaskStatus.CANCELLED: FlowStatus.CANCELLED,
                TaskStatus.PAUSED: FlowStatus.PAUSED,
                TaskStatus.WAITING: FlowStatus.RUNNING,
                TaskStatus.AWAITING_APPROVAL: FlowStatus.AWAITING_APPROVAL,
            }
            
            expected_status = status_map.get(task.status, FlowStatus.PENDING)
            
            if flow.status != expected_status:
                flow.status = expected_status
                if task.error:
                    flow.error = task.error
                reconciled += 1
        
        return reconciled
    
    # ========================================================================
    # Periodic Maintenance
    # ========================================================================
    
    def run_maintenance(self) -> MaintenanceStats:
        """Run full maintenance cycle."""
        stats = MaintenanceStats()
        
        try:
            # 1. Clean up completed tasks older than threshold
            archived = self._task_registry.cleanup_completed(self._archive_age_hours)
            stats.completed_tasks_archived = archived
            
            # 2. Clean expired paused tasks
            expired = self._cleanup_expired_tokens()
            stats.expired_tokens_cleaned = expired
            
            # 3. Reconcile flows
            stats.flows_reconciled = self._reconcile_flows()
            
            logger.info(f"[TaskMaintenance] Maintenance complete: {stats.to_dict()}")
            
        except Exception as e:
            stats.errors.append(f"Maintenance error: {e}")
            logger.error(f"[TaskMaintenance] Maintenance failed: {e}")
        
        self._last_maintenance = datetime.now()
        self._last_stats = stats
        return stats
    
    def _cleanup_expired_tokens(self) -> int:
        """Cancel tasks with expired resume tokens."""
        cleaned = 0
        now = datetime.now()
        
        for task in self._task_registry.list_tasks():
            if task.status in (TaskStatus.PAUSED, TaskStatus.AWAITING_APPROVAL):
                if task.expires_at:
                    try:
                        expires = datetime.fromisoformat(task.expires_at)
                        if now > expires:
                            self._task_registry.cancel(task.id, "Resume token expired")
                            cleaned += 1
                    except ValueError:
                        pass
        
        return cleaned
    
    # ========================================================================
    # Background Cleanup Thread
    # ========================================================================
    
    def start_background_cleanup(self):
        """Start background cleanup thread."""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            return
        
        self._stop_event.clear()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            name="TaskMaintenanceCleanup",
            daemon=True,
        )
        self._cleanup_thread.start()
        logger.info("[TaskMaintenance] Background cleanup started")
    
    def stop_background_cleanup(self):
        """Stop background cleanup thread."""
        self._stop_event.set()
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)
            self._cleanup_thread = None
        logger.info("[TaskMaintenance] Background cleanup stopped")
    
    def _cleanup_loop(self):
        """Background cleanup loop."""
        while not self._stop_event.is_set():
            try:
                self.run_maintenance()
            except Exception as e:
                logger.error(f"[TaskMaintenance] Cleanup loop error: {e}")
            
            # Wait for interval or stop event
            self._stop_event.wait(timeout=self._cleanup_interval)
    
    # ========================================================================
    # Health Monitoring
    # ========================================================================
    
    def get_health(self) -> HealthStatus:
        """Get current task system health status."""
        status = HealthStatus()
        
        try:
            # Task counts
            all_tasks = self._task_registry.list_tasks()
            status.total_tasks = len(all_tasks)
            status.active_tasks = sum(1 for t in all_tasks if t.is_active)
            status.paused_tasks = sum(
                1 for t in all_tasks 
                if t.status in (TaskStatus.PAUSED, TaskStatus.AWAITING_APPROVAL)
            )
            
            # Failed tasks in last 24 hours
            cutoff = datetime.now() - timedelta(hours=24)
            for entry in self._task_registry.get_history(limit=1000):
                if entry.get("status") == "failed":
                    try:
                        completed = datetime.fromisoformat(entry.get("completed_at", ""))
                        if completed > cutoff:
                            status.failed_tasks_24h += 1
                    except ValueError:
                        pass
            
            # Flow counts
            all_flows = self._flow_registry.list_flows()
            status.total_flows = len(all_flows)
            status.active_flows = sum(1 for f in all_flows if not f.is_terminal)
            
            # Warnings
            if status.failed_tasks_24h > 10:
                status.warnings.append(f"High failure rate: {status.failed_tasks_24h} failures in 24h")
            
            if status.paused_tasks > 20:
                status.warnings.append(f"Many paused tasks: {status.paused_tasks}")
            
            # Overall health
            status.healthy = len(status.warnings) == 0
            
        except Exception as e:
            status.healthy = False
            status.warnings.append(f"Health check error: {e}")
        
        return status
    
    # ========================================================================
    # Metrics
    # ========================================================================
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get task system metrics."""
        health = self.get_health()
        
        return {
            "health": health.to_dict(),
            "last_maintenance": self._last_maintenance.isoformat() if self._last_maintenance else None,
            "last_stats": self._last_stats.to_dict() if self._last_stats else None,
            "cleanup_interval": self._cleanup_interval,
            "archive_age_hours": self._archive_age_hours,
            "background_cleanup_running": bool(
                self._cleanup_thread and self._cleanup_thread.is_alive()
            ),
        }


# ============================================================================
# Singleton
# ============================================================================

_maintenance_instance: Optional[TaskMaintenance] = None
_maintenance_lock = threading.Lock()


def get_maintenance() -> TaskMaintenance:
    """Get singleton TaskMaintenance instance."""
    global _maintenance_instance
    if _maintenance_instance is None:
        with _maintenance_lock:
            if _maintenance_instance is None:
                _maintenance_instance = TaskMaintenance()
    return _maintenance_instance


def startup_tasks():
    """Run task system startup (reconciliation)."""
    maintenance = get_maintenance()
    return maintenance.startup_reconcile()
