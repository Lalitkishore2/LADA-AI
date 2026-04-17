"""
LADA Health Checks

Provides lightweight, continuous health monitoring.

Features:
- Component health checks
- Resource monitoring
- Service availability
- Background health polling
"""

import os
import time
import json
import logging
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class HealthStatus(str, Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class HealthCheckResult:
    """Result of a single health check."""
    id: str
    name: str
    status: HealthStatus
    message: str
    
    # Timing
    latency_ms: float = 0.0
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Additional data
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "latency_ms": self.latency_ms,
            "checked_at": self.checked_at,
            "details": self.details,
        }


@dataclass
class HealthCheck:
    """
    A health check definition.
    
    Check function should return (status, message, details).
    """
    id: str
    name: str
    description: str = ""
    
    # Check function: () -> (status: HealthStatus, message: str, details: dict)
    check_fn: Callable[[], tuple] = None
    
    # Configuration
    interval_seconds: float = 30.0  # How often to run
    timeout_seconds: float = 10.0   # Max time to wait
    enabled: bool = True
    
    # Last result
    last_result: Optional[HealthCheckResult] = None
    last_run: Optional[datetime] = None
    
    def run(self) -> HealthCheckResult:
        """Execute the health check."""
        start = time.time()
        
        try:
            status, message, details = self.check_fn()
        except Exception as e:
            status = HealthStatus.UNHEALTHY
            message = f"Check failed: {str(e)}"
            details = {"error": str(e)}
        
        latency = (time.time() - start) * 1000
        
        result = HealthCheckResult(
            id=self.id,
            name=self.name,
            status=status,
            message=message,
            latency_ms=latency,
            details=details,
        )
        
        self.last_result = result
        self.last_run = datetime.now()
        
        return result


@dataclass
class OverallHealth:
    """Overall system health summary."""
    status: HealthStatus
    message: str
    
    # Component statuses
    components: List[HealthCheckResult] = field(default_factory=list)
    
    # Metrics
    healthy_count: int = 0
    degraded_count: int = 0
    unhealthy_count: int = 0
    
    # Timing
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "message": self.message,
            "components": [c.to_dict() for c in self.components],
            "metrics": {
                "healthy": self.healthy_count,
                "degraded": self.degraded_count,
                "unhealthy": self.unhealthy_count,
            },
            "checked_at": self.checked_at,
        }


# ============================================================================
# Health Check Registry
# ============================================================================

class HealthCheckRegistry:
    """
    Registry for health checks with background polling.
    
    Features:
    - Register/unregister health checks
    - Background health polling
    - Overall health aggregation
    - Health history
    """
    
    def __init__(
        self,
        enable_polling: bool = True,
        default_interval: float = 30.0,
    ):
        self._checks: Dict[str, HealthCheck] = {}
        self._lock = threading.RLock()
        
        self._enable_polling = enable_polling
        self._default_interval = default_interval
        self._polling_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # History
        self._history: List[OverallHealth] = []
        self._max_history = 100
        
        # Register built-in checks
        self._register_builtin_checks()
        
        # Start polling if enabled
        if enable_polling:
            self._start_polling()
        
        logger.info(f"[HealthCheckRegistry] Initialized with {len(self._checks)} checks")
    
    def register(self, check: HealthCheck) -> bool:
        """Register a health check."""
        with self._lock:
            self._checks[check.id] = check
        return True
    
    def unregister(self, check_id: str) -> bool:
        """Unregister a health check."""
        with self._lock:
            if check_id in self._checks:
                del self._checks[check_id]
                return True
        return False
    
    def get(self, check_id: str) -> Optional[HealthCheck]:
        """Get health check by ID."""
        with self._lock:
            return self._checks.get(check_id)
    
    def list_checks(self) -> List[HealthCheck]:
        """List all health checks."""
        with self._lock:
            return list(self._checks.values())
    
    def run_check(self, check_id: str) -> Optional[HealthCheckResult]:
        """Run a specific health check."""
        check = self.get(check_id)
        if not check or not check.enabled:
            return None
        
        return check.run()
    
    def run_all(self) -> OverallHealth:
        """Run all health checks and return overall health."""
        with self._lock:
            checks = [c for c in self._checks.values() if c.enabled]
        
        results = []
        for check in checks:
            try:
                result = check.run()
                results.append(result)
            except Exception as e:
                results.append(HealthCheckResult(
                    id=check.id,
                    name=check.name,
                    status=HealthStatus.UNKNOWN,
                    message=f"Check error: {str(e)}",
                ))
        
        # Calculate overall status
        healthy = sum(1 for r in results if r.status == HealthStatus.HEALTHY)
        degraded = sum(1 for r in results if r.status == HealthStatus.DEGRADED)
        unhealthy = sum(1 for r in results if r.status == HealthStatus.UNHEALTHY)
        
        if unhealthy > 0:
            overall_status = HealthStatus.UNHEALTHY
            message = f"{unhealthy} component(s) unhealthy"
        elif degraded > 0:
            overall_status = HealthStatus.DEGRADED
            message = f"{degraded} component(s) degraded"
        elif healthy > 0:
            overall_status = HealthStatus.HEALTHY
            message = "All components healthy"
        else:
            overall_status = HealthStatus.UNKNOWN
            message = "No health checks registered"
        
        health = OverallHealth(
            status=overall_status,
            message=message,
            components=results,
            healthy_count=healthy,
            degraded_count=degraded,
            unhealthy_count=unhealthy,
        )
        
        # Add to history
        with self._lock:
            self._history.append(health)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
        
        return health
    
    def get_health(self) -> OverallHealth:
        """
        Get current health status.
        
        Returns last polled health or runs checks if not available.
        """
        with self._lock:
            if self._history:
                return self._history[-1]
        
        return self.run_all()
    
    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get health history."""
        with self._lock:
            return [h.to_dict() for h in self._history[-limit:]]
    
    def stop(self):
        """Stop background polling."""
        self._stop_event.set()
        if self._polling_thread:
            self._polling_thread.join(timeout=5)
    
    def _start_polling(self):
        """Start background polling thread."""
        if self._polling_thread and self._polling_thread.is_alive():
            return
        
        self._stop_event.clear()
        self._polling_thread = threading.Thread(
            target=self._polling_loop,
            daemon=True,
            name="health-check-poller",
        )
        self._polling_thread.start()
    
    def _polling_loop(self):
        """Background polling loop."""
        while not self._stop_event.is_set():
            try:
                self.run_all()
            except Exception as e:
                logger.error(f"[HealthCheckRegistry] Polling error: {e}")
            
            self._stop_event.wait(self._default_interval)
    
    def _register_builtin_checks(self):
        """Register built-in health checks."""
        
        # Memory check
        self.register(HealthCheck(
            id="memory",
            name="Memory Usage",
            description="Check system memory usage",
            check_fn=self._check_memory,
            interval_seconds=60.0,
        ))
        
        # Storage check
        self.register(HealthCheck(
            id="storage",
            name="Storage Space",
            description="Check available storage space",
            check_fn=self._check_storage,
            interval_seconds=300.0,
        ))
        
        # API server check
        self.register(HealthCheck(
            id="api-server",
            name="API Server",
            description="Check API server responsiveness",
            check_fn=self._check_api_server,
            interval_seconds=30.0,
        ))
    
    def _check_memory(self) -> tuple:
        """Check memory usage."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            
            if mem.percent > 90:
                return HealthStatus.UNHEALTHY, f"Memory critical: {mem.percent}%", {
                    "percent": mem.percent,
                    "available_gb": round(mem.available / (1024**3), 2),
                }
            elif mem.percent > 75:
                return HealthStatus.DEGRADED, f"Memory high: {mem.percent}%", {
                    "percent": mem.percent,
                    "available_gb": round(mem.available / (1024**3), 2),
                }
            
            return HealthStatus.HEALTHY, f"Memory OK: {mem.percent}%", {
                "percent": mem.percent,
                "available_gb": round(mem.available / (1024**3), 2),
            }
        except ImportError:
            return HealthStatus.UNKNOWN, "psutil not available", {}
    
    def _check_storage(self) -> tuple:
        """Check storage space."""
        data_dir = Path(os.getenv("LADA_DATA_DIR", "data"))
        
        try:
            import shutil
            total, used, free = shutil.disk_usage(data_dir.parent)
            free_gb = free / (1024**3)
            used_percent = (used / total) * 100
            
            if free_gb < 1:
                return HealthStatus.UNHEALTHY, f"Storage critical: {free_gb:.1f}GB free", {
                    "free_gb": round(free_gb, 2),
                    "used_percent": round(used_percent, 1),
                }
            elif free_gb < 5:
                return HealthStatus.DEGRADED, f"Storage low: {free_gb:.1f}GB free", {
                    "free_gb": round(free_gb, 2),
                    "used_percent": round(used_percent, 1),
                }
            
            return HealthStatus.HEALTHY, f"Storage OK: {free_gb:.1f}GB free", {
                "free_gb": round(free_gb, 2),
                "used_percent": round(used_percent, 1),
            }
        except Exception as e:
            return HealthStatus.UNKNOWN, f"Storage check failed: {e}", {}
    
    def _check_api_server(self) -> tuple:
        """Check API server responsiveness."""
        # This is a placeholder - actual implementation would check port 5000
        return HealthStatus.HEALTHY, "API server check placeholder", {}


# ============================================================================
# Singleton
# ============================================================================

_registry_instance: Optional[HealthCheckRegistry] = None
_registry_lock = threading.Lock()


def get_health_registry() -> HealthCheckRegistry:
    """Get singleton HealthCheckRegistry instance."""
    global _registry_instance
    if _registry_instance is None:
        with _registry_lock:
            if _registry_instance is None:
                _registry_instance = HealthCheckRegistry()
    return _registry_instance
