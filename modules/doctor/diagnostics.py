"""
LADA Diagnostics Engine

Provides comprehensive runtime diagnostics for LADA components.

Features:
- Provider connectivity checks
- Module availability verification
- Configuration validation
- Performance benchmarks
- Dependency chain verification
"""

import os
import sys
import time
import json
import logging
import threading
import importlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class DiagnosticSeverity(str, Enum):
    """Severity level of a diagnostic result."""
    INFO = "info"           # Informational only
    WARNING = "warning"     # Non-critical issue
    ERROR = "error"         # Critical issue, affects functionality
    CRITICAL = "critical"   # System cannot function properly


class DiagnosticCategory(str, Enum):
    """Category of diagnostic checks."""
    PROVIDER = "provider"       # AI provider connectivity
    MODULE = "module"           # Module availability
    CONFIG = "config"           # Configuration validation
    NETWORK = "network"         # Network connectivity
    STORAGE = "storage"         # Storage/persistence
    MEMORY = "memory"           # Memory usage
    PERFORMANCE = "performance" # Performance benchmarks
    SECURITY = "security"       # Security checks
    DEPENDENCY = "dependency"   # External dependencies


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class DiagnosticResult:
    """Result of a single diagnostic check."""
    id: str
    name: str
    category: DiagnosticCategory
    severity: DiagnosticSeverity
    passed: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    
    # Timing
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # Fix information
    fixable: bool = False
    fix_id: Optional[str] = None
    fix_description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category.value,
            "severity": self.severity.value,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "fixable": self.fixable,
            "fix_id": self.fix_id,
            "fix_description": self.fix_description,
        }


@dataclass
class Diagnostic:
    """
    A diagnostic check definition.
    
    The check function should return a tuple of (passed, message, details).
    """
    id: str
    name: str
    description: str
    category: DiagnosticCategory
    
    # Check function: () -> (passed: bool, message: str, details: dict)
    check_fn: Callable[[], tuple]
    
    # Configuration
    timeout_seconds: float = 30.0
    enabled: bool = True
    priority: int = 0  # Higher = run first
    
    # Dependencies
    depends_on: List[str] = field(default_factory=list)
    
    # Fix reference
    fix_id: Optional[str] = None
    
    def run(self) -> DiagnosticResult:
        """Execute the diagnostic check."""
        start = time.time()
        
        try:
            passed, message, details = self.check_fn()
            severity = DiagnosticSeverity.INFO if passed else DiagnosticSeverity.ERROR
            
        except TimeoutError:
            passed = False
            message = f"Check timed out after {self.timeout_seconds}s"
            details = {"timeout": True}
            severity = DiagnosticSeverity.ERROR
            
        except Exception as e:
            passed = False
            message = f"Check failed with exception: {str(e)}"
            details = {"exception": type(e).__name__, "error": str(e)}
            severity = DiagnosticSeverity.ERROR
        
        duration = (time.time() - start) * 1000
        
        return DiagnosticResult(
            id=self.id,
            name=self.name,
            category=self.category,
            severity=severity,
            passed=passed,
            message=message,
            details=details,
            duration_ms=duration,
            fixable=self.fix_id is not None,
            fix_id=self.fix_id,
        )


@dataclass
class DiagnosticsReport:
    """Complete diagnostics report."""
    id: str
    timestamp: str
    duration_ms: float
    
    # Summary
    total_checks: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    
    # Results by category
    results: List[DiagnosticResult] = field(default_factory=list)
    
    # System info
    system_info: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "summary": {
                "total_checks": self.total_checks,
                "passed": self.passed,
                "failed": self.failed,
                "warnings": self.warnings,
            },
            "results": [r.to_dict() for r in self.results],
            "system_info": self.system_info,
        }


# ============================================================================
# Diagnostics Runner
# ============================================================================

class DiagnosticsRunner:
    """
    Runs diagnostic checks and produces reports.
    
    Features:
    - Parallel execution with dependency ordering
    - Timeout handling
    - Category filtering
    - Report persistence
    """
    
    def __init__(
        self,
        max_workers: int = 4,
        reports_dir: Optional[str] = None,
    ):
        self._diagnostics: Dict[str, Diagnostic] = {}
        self._max_workers = max_workers
        self._reports_dir = Path(reports_dir or os.getenv("LADA_DOCTOR_REPORTS_DIR", "data/doctor"))
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        
        self._lock = threading.RLock()
        
        # Register built-in diagnostics
        self._register_builtin_diagnostics()
        
        logger.info(f"[DiagnosticsRunner] Initialized with {len(self._diagnostics)} diagnostics")
    
    def register(self, diagnostic: Diagnostic) -> bool:
        """Register a diagnostic check."""
        with self._lock:
            self._diagnostics[diagnostic.id] = diagnostic
        return True
    
    def unregister(self, diagnostic_id: str) -> bool:
        """Unregister a diagnostic check."""
        with self._lock:
            if diagnostic_id in self._diagnostics:
                del self._diagnostics[diagnostic_id]
                return True
        return False
    
    def get(self, diagnostic_id: str) -> Optional[Diagnostic]:
        """Get diagnostic by ID."""
        with self._lock:
            return self._diagnostics.get(diagnostic_id)
    
    def list_diagnostics(
        self,
        category: Optional[DiagnosticCategory] = None,
    ) -> List[Diagnostic]:
        """List all diagnostics, optionally filtered by category."""
        with self._lock:
            diagnostics = list(self._diagnostics.values())
        
        if category:
            diagnostics = [d for d in diagnostics if d.category == category]
        
        return sorted(diagnostics, key=lambda d: (-d.priority, d.id))
    
    def run_all(
        self,
        categories: Optional[List[DiagnosticCategory]] = None,
        parallel: bool = True,
    ) -> DiagnosticsReport:
        """
        Run all diagnostics and produce a report.
        
        Args:
            categories: Optional list of categories to run
            parallel: Whether to run checks in parallel
        
        Returns:
            DiagnosticsReport with all results
        """
        import uuid
        
        report_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        
        # Get diagnostics to run
        with self._lock:
            diagnostics = list(self._diagnostics.values())
        
        if categories:
            diagnostics = [d for d in diagnostics if d.category in categories]
        
        diagnostics = [d for d in diagnostics if d.enabled]
        diagnostics = sorted(diagnostics, key=lambda d: (-d.priority, d.id))
        
        # Run diagnostics
        results: List[DiagnosticResult] = []
        
        if parallel and self._max_workers > 1:
            results = self._run_parallel(diagnostics)
        else:
            results = self._run_sequential(diagnostics)
        
        # Build report
        duration = (time.time() - start_time) * 1000
        
        report = DiagnosticsReport(
            id=report_id,
            timestamp=datetime.now().isoformat(),
            duration_ms=duration,
            total_checks=len(results),
            passed=sum(1 for r in results if r.passed),
            failed=sum(1 for r in results if not r.passed and r.severity == DiagnosticSeverity.ERROR),
            warnings=sum(1 for r in results if not r.passed and r.severity == DiagnosticSeverity.WARNING),
            results=results,
            system_info=self._get_system_info(),
        )
        
        # Persist report
        self._save_report(report)
        
        logger.info(
            f"[DiagnosticsRunner] Report {report_id}: "
            f"{report.passed}/{report.total_checks} passed in {duration:.0f}ms"
        )
        
        return report
    
    def run_single(self, diagnostic_id: str) -> Optional[DiagnosticResult]:
        """Run a single diagnostic check."""
        diagnostic = self.get(diagnostic_id)
        if not diagnostic:
            return None
        
        return diagnostic.run()
    
    def get_report(self, report_id: str) -> Optional[DiagnosticsReport]:
        """Load a saved report."""
        report_file = self._reports_dir / f"{report_id}.json"
        if not report_file.exists():
            return None
        
        try:
            with open(report_file, 'r') as f:
                data = json.load(f)
            
            results = [
                DiagnosticResult(
                    id=r["id"],
                    name=r["name"],
                    category=DiagnosticCategory(r["category"]),
                    severity=DiagnosticSeverity(r["severity"]),
                    passed=r["passed"],
                    message=r["message"],
                    details=r.get("details", {}),
                    duration_ms=r.get("duration_ms", 0),
                    timestamp=r.get("timestamp", ""),
                    fixable=r.get("fixable", False),
                    fix_id=r.get("fix_id"),
                )
                for r in data.get("results", [])
            ]
            
            summary = data.get("summary", {})
            return DiagnosticsReport(
                id=data["id"],
                timestamp=data["timestamp"],
                duration_ms=data.get("duration_ms", 0),
                total_checks=summary.get("total_checks", 0),
                passed=summary.get("passed", 0),
                failed=summary.get("failed", 0),
                warnings=summary.get("warnings", 0),
                results=results,
                system_info=data.get("system_info", {}),
            )
        except Exception as e:
            logger.error(f"[DiagnosticsRunner] Failed to load report {report_id}: {e}")
            return None
    
    def list_reports(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List recent reports."""
        reports = []
        
        for report_file in sorted(
            self._reports_dir.glob("*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )[:limit]:
            try:
                with open(report_file, 'r') as f:
                    data = json.load(f)
                
                summary = data.get("summary", {})
                reports.append({
                    "id": data.get("id"),
                    "timestamp": data.get("timestamp"),
                    "total_checks": summary.get("total_checks", 0),
                    "passed": summary.get("passed", 0),
                    "failed": summary.get("failed", 0),
                })
            except Exception:
                continue
        
        return reports
    
    def _run_sequential(self, diagnostics: List[Diagnostic]) -> List[DiagnosticResult]:
        """Run diagnostics sequentially."""
        results = []
        completed: Set[str] = set()
        
        for diagnostic in diagnostics:
            # Check dependencies
            if diagnostic.depends_on:
                deps_met = all(
                    d in completed
                    for d in diagnostic.depends_on
                )
                if not deps_met:
                    results.append(DiagnosticResult(
                        id=diagnostic.id,
                        name=diagnostic.name,
                        category=diagnostic.category,
                        severity=DiagnosticSeverity.WARNING,
                        passed=False,
                        message="Skipped: dependencies not met",
                        details={"missing_deps": [
                            d for d in diagnostic.depends_on if d not in completed
                        ]},
                    ))
                    continue
            
            result = diagnostic.run()
            results.append(result)
            
            if result.passed:
                completed.add(diagnostic.id)
        
        return results
    
    def _run_parallel(self, diagnostics: List[Diagnostic]) -> List[DiagnosticResult]:
        """Run diagnostics in parallel with dependency ordering."""
        results = []
        completed: Set[str] = set()
        pending = list(diagnostics)
        
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            while pending:
                # Find diagnostics with met dependencies
                ready = []
                still_pending = []
                
                for diag in pending:
                    deps_met = all(d in completed for d in diag.depends_on)
                    if deps_met:
                        ready.append(diag)
                    else:
                        still_pending.append(diag)
                
                if not ready:
                    # No progress possible, mark remaining as skipped
                    for diag in still_pending:
                        results.append(DiagnosticResult(
                            id=diag.id,
                            name=diag.name,
                            category=diag.category,
                            severity=DiagnosticSeverity.WARNING,
                            passed=False,
                            message="Skipped: circular dependency or failed dependency",
                        ))
                    break
                
                # Run ready diagnostics in parallel
                futures = {
                    executor.submit(diag.run): diag
                    for diag in ready
                }
                
                for future in as_completed(futures):
                    diag = futures[future]
                    try:
                        result = future.result()
                        results.append(result)
                        if result.passed:
                            completed.add(diag.id)
                    except Exception as e:
                        results.append(DiagnosticResult(
                            id=diag.id,
                            name=diag.name,
                            category=diag.category,
                            severity=DiagnosticSeverity.ERROR,
                            passed=False,
                            message=f"Execution error: {str(e)}",
                        ))
                
                pending = still_pending
        
        return results
    
    def _save_report(self, report: DiagnosticsReport):
        """Save report to disk."""
        report_file = self._reports_dir / f"{report.id}.json"
        try:
            with open(report_file, 'w') as f:
                json.dump(report.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"[DiagnosticsRunner] Failed to save report: {e}")
    
    def _get_system_info(self) -> Dict[str, Any]:
        """Collect system information."""
        import platform
        
        info = {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "hostname": platform.node(),
            "timestamp": datetime.now().isoformat(),
        }
        
        # Add memory info if available
        try:
            import psutil
            mem = psutil.virtual_memory()
            info["memory"] = {
                "total_gb": round(mem.total / (1024**3), 2),
                "available_gb": round(mem.available / (1024**3), 2),
                "percent_used": mem.percent,
            }
        except ImportError:
            pass
        
        return info
    
    def _register_builtin_diagnostics(self):
        """Register built-in diagnostic checks."""
        
        # Python version check
        self.register(Diagnostic(
            id="python-version",
            name="Python Version",
            description="Check Python version compatibility",
            category=DiagnosticCategory.DEPENDENCY,
            priority=100,
            check_fn=self._check_python_version,
        ))
        
        # Required modules check
        self.register(Diagnostic(
            id="core-modules",
            name="Core Modules",
            description="Check core LADA modules are importable",
            category=DiagnosticCategory.MODULE,
            priority=90,
            check_fn=self._check_core_modules,
        ))
        
        # Configuration check
        self.register(Diagnostic(
            id="env-config",
            name="Environment Configuration",
            description="Check required environment variables",
            category=DiagnosticCategory.CONFIG,
            priority=80,
            check_fn=self._check_env_config,
        ))
        
        # Provider connectivity
        self.register(Diagnostic(
            id="provider-connectivity",
            name="AI Provider Connectivity",
            description="Check AI provider API connectivity",
            category=DiagnosticCategory.PROVIDER,
            priority=70,
            check_fn=self._check_provider_connectivity,
            timeout_seconds=60.0,
        ))
        
        # Storage check
        self.register(Diagnostic(
            id="storage-access",
            name="Storage Access",
            description="Check data directory access",
            category=DiagnosticCategory.STORAGE,
            priority=60,
            check_fn=self._check_storage_access,
        ))
    
    def _check_python_version(self) -> tuple:
        """Check Python version compatibility."""
        version = sys.version_info
        required = (3, 11)
        
        if version >= required:
            return True, f"Python {version.major}.{version.minor}.{version.micro}", {}
        else:
            return False, f"Python {required[0]}.{required[1]}+ required, found {version.major}.{version.minor}", {
                "current": f"{version.major}.{version.minor}.{version.micro}",
                "required": f"{required[0]}.{required[1]}+",
            }
    
    def _check_core_modules(self) -> tuple:
        """Check core LADA modules are importable."""
        core_modules = [
            "lada_ai_router",
            "lada_jarvis_core",
            "lada_memory",
            "modules.providers.provider_manager",
            "modules.tool_registry",
            "modules.session_manager",
        ]
        
        failed = []
        details = {}
        
        for module in core_modules:
            try:
                importlib.import_module(module)
                details[module] = "ok"
            except ImportError as e:
                failed.append(module)
                details[module] = str(e)
        
        if failed:
            return False, f"{len(failed)} core module(s) failed to import", {
                "failed": failed,
                "details": details,
            }
        
        return True, f"All {len(core_modules)} core modules available", {"modules": details}
    
    def _check_env_config(self) -> tuple:
        """Check required environment variables."""
        # At least one AI key should be set
        ai_keys = [
            "GEMINI_API_KEY",
            "GROQ_API_KEY",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "MISTRAL_API_KEY",
        ]
        
        found_keys = [k for k in ai_keys if os.getenv(k)]
        
        if not found_keys:
            return False, "No AI provider API keys configured", {
                "checked_keys": ai_keys,
                "fix_id": "set-api-key",
            }
        
        # Check optional but recommended
        warnings = []
        if not os.getenv("LADA_WEB_PASSWORD"):
            warnings.append("LADA_WEB_PASSWORD not set (using default)")
        
        return True, f"{len(found_keys)} AI provider key(s) configured", {
            "configured_providers": found_keys,
            "warnings": warnings,
        }
    
    def _check_provider_connectivity(self) -> tuple:
        """Check AI provider API connectivity."""
        try:
            from modules.providers.provider_manager import ProviderManager
            
            pm = ProviderManager()
            status = pm.get_health_status()
            
            healthy = sum(1 for s in status.values() if s.get("healthy", False))
            total = len(status)
            
            if healthy == 0:
                return False, "No healthy AI providers", {"providers": status}
            
            return True, f"{healthy}/{total} providers healthy", {"providers": status}
            
        except Exception as e:
            return False, f"Provider check failed: {str(e)}", {"error": str(e)}
    
    def _check_storage_access(self) -> tuple:
        """Check data directory access."""
        data_dir = Path(os.getenv("LADA_DATA_DIR", "data"))
        
        if not data_dir.exists():
            try:
                data_dir.mkdir(parents=True)
            except Exception as e:
                return False, f"Cannot create data directory: {e}", {"path": str(data_dir)}
        
        # Check write access
        test_file = data_dir / ".write_test"
        try:
            test_file.write_text("test")
            test_file.unlink()
        except Exception as e:
            return False, f"Data directory not writable: {e}", {"path": str(data_dir)}
        
        return True, f"Data directory accessible: {data_dir}", {"path": str(data_dir)}


# ============================================================================
# Singleton
# ============================================================================

_runner_instance: Optional[DiagnosticsRunner] = None
_runner_lock = threading.Lock()


def get_diagnostics_runner() -> DiagnosticsRunner:
    """Get singleton DiagnosticsRunner instance."""
    global _runner_instance
    if _runner_instance is None:
        with _runner_lock:
            if _runner_instance is None:
                _runner_instance = DiagnosticsRunner()
    return _runner_instance
