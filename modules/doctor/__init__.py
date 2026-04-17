"""
LADA Doctor Module

Runtime health diagnostics with auto-fix capabilities.

Features:
- Provider connectivity checks
- Module availability checks
- Configuration validation
- Performance metrics
- Auto-fix suggestions and execution
"""

from modules.doctor.diagnostics import (
    Diagnostic,
    DiagnosticResult,
    DiagnosticSeverity,
    DiagnosticCategory,
    DiagnosticsRunner,
    get_diagnostics_runner,
)

from modules.doctor.health_checks import (
    HealthCheck,
    HealthCheckResult,
    HealthStatus,
    HealthCheckRegistry,
    get_health_registry,
)

from modules.doctor.auto_fix import (
    AutoFix,
    FixResult,
    FixStatus,
    AutoFixEngine,
    get_fix_engine,
)

__all__ = [
    # Diagnostics
    'Diagnostic',
    'DiagnosticResult',
    'DiagnosticSeverity',
    'DiagnosticCategory',
    'DiagnosticsRunner',
    'get_diagnostics_runner',
    # Health checks
    'HealthCheck',
    'HealthCheckResult',
    'HealthStatus',
    'HealthCheckRegistry',
    'get_health_registry',
    # Auto-fix
    'AutoFix',
    'FixResult',
    'FixStatus',
    'AutoFixEngine',
    'get_fix_engine',
]
