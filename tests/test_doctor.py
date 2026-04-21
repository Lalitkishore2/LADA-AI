"""
Tests for LADA Doctor Module.

Tests:
- Diagnostics runner
- Health checks
- Auto-fix engine
"""

import pytest
import tempfile
import os
import time
from unittest.mock import patch, MagicMock

from modules.doctor.diagnostics import (
    DiagnosticsRunner,
    Diagnostic,
    DiagnosticResult,
    DiagnosticsReport,
    DiagnosticSeverity,
    DiagnosticCategory,
)

from modules.doctor.health_checks import (
    HealthCheckRegistry,
    HealthCheck,
    HealthCheckResult,
    HealthStatus,
    OverallHealth,
)

from modules.doctor.auto_fix import (
    AutoFixEngine,
    AutoFix,
    FixResult,
    FixStatus,
    FixRisk,
)


# ============================================================================
# Diagnostics Tests
# ============================================================================

class TestDiagnostic:
    """Tests for Diagnostic class."""
    
    def test_run_passing_diagnostic(self):
        """Test running a passing diagnostic."""
        def check_fn():
            return True, "All good", {"test": True}
        
        diag = Diagnostic(
            id="test-diag",
            name="Test Diagnostic",
            description="A test diagnostic",
            category=DiagnosticCategory.MODULE,
            check_fn=check_fn,
        )
        
        result = diag.run()
        
        assert result.passed is True
        assert result.severity == DiagnosticSeverity.INFO
        assert result.message == "All good"
        assert result.details["test"] is True
    
    def test_run_failing_diagnostic(self):
        """Test running a failing diagnostic."""
        def check_fn():
            return False, "Something wrong", {"error": "test"}
        
        diag = Diagnostic(
            id="test-diag",
            name="Test Diagnostic",
            description="A test diagnostic",
            category=DiagnosticCategory.CONFIG,
            check_fn=check_fn,
        )
        
        result = diag.run()
        
        assert result.passed is False
        assert result.severity == DiagnosticSeverity.ERROR
    
    def test_run_diagnostic_with_exception(self):
        """Test diagnostic that throws an exception."""
        def check_fn():
            raise ValueError("Test error")
        
        diag = Diagnostic(
            id="test-diag",
            name="Test Diagnostic",
            description="A test diagnostic",
            category=DiagnosticCategory.MODULE,
            check_fn=check_fn,
        )
        
        result = diag.run()
        
        assert result.passed is False
        assert "exception" in result.message.lower()


class TestDiagnosticsRunner:
    """Tests for DiagnosticsRunner."""
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def runner(self, temp_dir):
        return DiagnosticsRunner(reports_dir=temp_dir, max_workers=2)
    
    def test_register_diagnostic(self, runner):
        """Test registering a diagnostic."""
        diag = Diagnostic(
            id="custom-diag",
            name="Custom Diagnostic",
            description="A custom diagnostic",
            category=DiagnosticCategory.MODULE,
            check_fn=lambda: (True, "OK", {}),
        )
        
        result = runner.register(diag)
        assert result is True
        
        found = runner.get("custom-diag")
        assert found is not None
        assert found.name == "Custom Diagnostic"
    
    def test_unregister_diagnostic(self, runner):
        """Test unregistering a diagnostic."""
        diag = Diagnostic(
            id="to-remove",
            name="To Remove",
            description="Will be removed",
            category=DiagnosticCategory.MODULE,
            check_fn=lambda: (True, "OK", {}),
        )
        
        runner.register(diag)
        result = runner.unregister("to-remove")
        
        assert result is True
        assert runner.get("to-remove") is None
    
    def test_list_diagnostics(self, runner):
        """Test listing diagnostics."""
        diagnostics = runner.list_diagnostics()
        
        # Should have built-in diagnostics
        assert len(diagnostics) >= 1
    
    def test_list_by_category(self, runner):
        """Test listing diagnostics by category."""
        runner.register(Diagnostic(
            id="test-module",
            name="Test Module",
            description="Test",
            category=DiagnosticCategory.MODULE,
            check_fn=lambda: (True, "OK", {}),
        ))
        
        runner.register(Diagnostic(
            id="test-config",
            name="Test Config",
            description="Test",
            category=DiagnosticCategory.CONFIG,
            check_fn=lambda: (True, "OK", {}),
        ))
        
        module_diags = runner.list_diagnostics(category=DiagnosticCategory.MODULE)
        config_diags = runner.list_diagnostics(category=DiagnosticCategory.CONFIG)
        
        assert all(d.category == DiagnosticCategory.MODULE for d in module_diags)
        assert all(d.category == DiagnosticCategory.CONFIG for d in config_diags)
    
    def test_run_single(self, runner):
        """Test running a single diagnostic."""
        runner.register(Diagnostic(
            id="single-test",
            name="Single Test",
            description="Test",
            category=DiagnosticCategory.MODULE,
            check_fn=lambda: (True, "Single passed", {}),
        ))
        
        result = runner.run_single("single-test")
        
        assert result is not None
        assert result.passed is True
        assert result.message == "Single passed"
    
    def test_run_all_sequential(self, runner):
        """Test running all diagnostics sequentially."""
        runner.register(Diagnostic(
            id="seq-test-1",
            name="Seq Test 1",
            description="Test",
            category=DiagnosticCategory.MODULE,
            check_fn=lambda: (True, "OK 1", {}),
        ))
        
        runner.register(Diagnostic(
            id="seq-test-2",
            name="Seq Test 2",
            description="Test",
            category=DiagnosticCategory.MODULE,
            check_fn=lambda: (True, "OK 2", {}),
        ))
        
        report = runner.run_all(parallel=False)
        
        assert isinstance(report, DiagnosticsReport)
        assert report.total_checks >= 2
    
    def test_run_all_parallel(self, runner):
        """Test running all diagnostics in parallel."""
        runner.register(Diagnostic(
            id="par-test-1",
            name="Par Test 1",
            description="Test",
            category=DiagnosticCategory.MODULE,
            check_fn=lambda: (True, "OK", {}),
        ))
        
        runner.register(Diagnostic(
            id="par-test-2",
            name="Par Test 2",
            description="Test",
            category=DiagnosticCategory.MODULE,
            check_fn=lambda: (True, "OK", {}),
        ))
        
        report = runner.run_all(parallel=True)
        
        assert isinstance(report, DiagnosticsReport)
        assert report.total_checks >= 2
    
    def test_report_persistence(self, runner):
        """Test that reports are saved and can be loaded."""
        # Clear all existing diagnostics and add only simple ones
        runner._diagnostics.clear()
        
        runner.register(Diagnostic(
            id="persist-test",
            name="Persist Test",
            description="Test",
            category=DiagnosticCategory.MODULE,
            check_fn=lambda: (True, "OK", {"simple": "data"}),
        ))
        
        # Disable builtin system_info for this test
        original_get_system_info = runner._get_system_info
        runner._get_system_info = lambda: {"test": True}
        
        try:
            report = runner.run_all()
            report_id = report.id
            
            # Load saved report
            loaded = runner.get_report(report_id)
            
            assert loaded is not None
            assert loaded.id == report_id
        finally:
            runner._get_system_info = original_get_system_info
    
    def test_list_reports(self, runner):
        """Test listing reports."""
        # Clear and add simple diagnostic
        runner._diagnostics.clear()
        
        runner.register(Diagnostic(
            id="list-test",
            name="List Test",
            description="Test",
            category=DiagnosticCategory.MODULE,
            check_fn=lambda: (True, "OK", {}),
        ))
        
        # Disable builtin system_info for this test
        original_get_system_info = runner._get_system_info
        runner._get_system_info = lambda: {"test": True}
        
        try:
            runner.run_all()
            runner.run_all()
            
            reports = runner.list_reports()
            
            assert len(reports) >= 2
        finally:
            runner._get_system_info = original_get_system_info

    def test_provider_connectivity_uses_current_provider_manager_api(self, runner):
        """Provider connectivity should rely on check_all_health, not removed legacy methods."""
        class _FakeProviderManager:
            def auto_configure(self):
                return 2

            def check_all_health(self):
                return {
                    "provider-a": {"available": True},
                    "provider-b": {"available": False},
                }

        with patch("modules.providers.provider_manager.ProviderManager", _FakeProviderManager):
            passed, message, details = runner._check_provider_connectivity()

        assert passed is True
        assert message == "1/2 providers healthy"
        assert "providers" in details

    def test_provider_connectivity_reports_unconfigured_providers(self, runner):
        """Provider connectivity should return an actionable result when no providers are configured."""
        class _FakeProviderManager:
            def auto_configure(self):
                return 0

            def check_all_health(self):
                return {}

        with patch("modules.providers.provider_manager.ProviderManager", _FakeProviderManager):
            passed, message, details = runner._check_provider_connectivity()

        assert passed is False
        assert message == "No AI providers configured"
        assert details["fix_id"] == "set-api-key"


# ============================================================================
# Health Check Tests
# ============================================================================

class TestHealthCheck:
    """Tests for HealthCheck class."""
    
    def test_run_healthy_check(self):
        """Test running a healthy check."""
        def check_fn():
            return HealthStatus.HEALTHY, "All good", {}
        
        check = HealthCheck(
            id="test-check",
            name="Test Check",
            check_fn=check_fn,
        )
        
        result = check.run()
        
        assert result.status == HealthStatus.HEALTHY
        assert result.message == "All good"
    
    def test_run_unhealthy_check(self):
        """Test running an unhealthy check."""
        def check_fn():
            return HealthStatus.UNHEALTHY, "Something wrong", {"error": True}
        
        check = HealthCheck(
            id="test-check",
            name="Test Check",
            check_fn=check_fn,
        )
        
        result = check.run()
        
        assert result.status == HealthStatus.UNHEALTHY
    
    def test_last_result_stored(self):
        """Test that last result is stored."""
        check = HealthCheck(
            id="test-check",
            name="Test Check",
            check_fn=lambda: (HealthStatus.HEALTHY, "OK", {}),
        )
        
        check.run()
        
        assert check.last_result is not None
        assert check.last_run is not None


class TestHealthCheckRegistry:
    """Tests for HealthCheckRegistry."""
    
    @pytest.fixture
    def registry(self):
        return HealthCheckRegistry(enable_polling=False)
    
    def test_register_check(self, registry):
        """Test registering a health check."""
        check = HealthCheck(
            id="custom-check",
            name="Custom Check",
            check_fn=lambda: (HealthStatus.HEALTHY, "OK", {}),
        )
        
        result = registry.register(check)
        assert result is True
        
        found = registry.get("custom-check")
        assert found is not None
    
    def test_unregister_check(self, registry):
        """Test unregistering a health check."""
        check = HealthCheck(
            id="to-remove",
            name="To Remove",
            check_fn=lambda: (HealthStatus.HEALTHY, "OK", {}),
        )
        
        registry.register(check)
        result = registry.unregister("to-remove")
        
        assert result is True
        assert registry.get("to-remove") is None
    
    def test_run_all_healthy(self, registry):
        """Test running all checks when all healthy."""
        # Clear builtin checks and add only our test checks
        registry._checks.clear()
        
        registry.register(HealthCheck(
            id="check-1",
            name="Check 1",
            check_fn=lambda: (HealthStatus.HEALTHY, "OK", {}),
        ))
        
        registry.register(HealthCheck(
            id="check-2",
            name="Check 2",
            check_fn=lambda: (HealthStatus.HEALTHY, "OK", {}),
        ))
        
        health = registry.run_all()
        
        assert health.status == HealthStatus.HEALTHY
        assert health.healthy_count == 2
    
    def test_run_all_degraded(self, registry):
        """Test overall status when one check is degraded."""
        # Clear builtin checks
        registry._checks.clear()
        
        registry.register(HealthCheck(
            id="healthy-check",
            name="Healthy Check",
            check_fn=lambda: (HealthStatus.HEALTHY, "OK", {}),
        ))
        
        registry.register(HealthCheck(
            id="degraded-check",
            name="Degraded Check",
            check_fn=lambda: (HealthStatus.DEGRADED, "Warning", {}),
        ))
        
        health = registry.run_all()
        
        assert health.status == HealthStatus.DEGRADED
        assert health.degraded_count == 1
    
    def test_run_all_unhealthy(self, registry):
        """Test overall status when one check is unhealthy."""
        # Clear builtin checks
        registry._checks.clear()
        
        registry.register(HealthCheck(
            id="healthy-check",
            name="Healthy Check",
            check_fn=lambda: (HealthStatus.HEALTHY, "OK", {}),
        ))
        
        registry.register(HealthCheck(
            id="unhealthy-check",
            name="Unhealthy Check",
            check_fn=lambda: (HealthStatus.UNHEALTHY, "Error", {}),
        ))
        
        health = registry.run_all()
        
        assert health.status == HealthStatus.UNHEALTHY
        assert health.unhealthy_count == 1
    
    def test_get_health(self, registry):
        """Test getting current health."""
        registry.register(HealthCheck(
            id="test-check",
            name="Test Check",
            check_fn=lambda: (HealthStatus.HEALTHY, "OK", {}),
        ))
        
        health = registry.get_health()
        
        assert isinstance(health, OverallHealth)
    
    def test_history_tracking(self, registry):
        """Test health history tracking."""
        registry.register(HealthCheck(
            id="test-check",
            name="Test Check",
            check_fn=lambda: (HealthStatus.HEALTHY, "OK", {}),
        ))
        
        registry.run_all()
        registry.run_all()
        
        history = registry.get_history()
        
        assert len(history) >= 2


# ============================================================================
# Auto-Fix Tests
# ============================================================================

class TestAutoFix:
    """Tests for AutoFix class."""
    
    def test_to_dict(self):
        """Test converting fix to dict."""
        fix = AutoFix(
            id="test-fix",
            name="Test Fix",
            description="A test fix",
            risk=FixRisk.LOW,
            steps=["Step 1", "Step 2"],
        )
        
        data = fix.to_dict()
        
        assert data["id"] == "test-fix"
        assert data["risk"] == "low"
        assert len(data["steps"]) == 2


class TestAutoFixEngine:
    """Tests for AutoFixEngine."""
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def engine(self, temp_dir):
        return AutoFixEngine(history_dir=temp_dir)
    
    def test_register_fix(self, engine):
        """Test registering a fix."""
        fix = AutoFix(
            id="custom-fix",
            name="Custom Fix",
            description="A custom fix",
            fix_fn=lambda p: (True, "Fixed", {}),
        )
        
        result = engine.register(fix)
        assert result is True
        
        found = engine.get("custom-fix")
        assert found is not None
    
    def test_execute_successful_fix(self, engine):
        """Test executing a successful fix."""
        engine.register(AutoFix(
            id="success-fix",
            name="Success Fix",
            description="A fix that succeeds",
            risk=FixRisk.LOW,
            fix_fn=lambda p: (True, "Fixed successfully", {"data": "test"}),
        ))
        
        result = engine.execute("success-fix")
        
        assert result.status == FixStatus.SUCCESS
        assert result.message == "Fixed successfully"
    
    def test_execute_failing_fix(self, engine):
        """Test executing a failing fix."""
        engine.register(AutoFix(
            id="fail-fix",
            name="Fail Fix",
            description="A fix that fails",
            risk=FixRisk.LOW,
            fix_fn=lambda p: (False, "Fix failed", {"error": "test"}),
        ))
        
        result = engine.execute("fail-fix")
        
        assert result.status == FixStatus.FAILED
    
    def test_execute_with_exception(self, engine):
        """Test fix that throws exception."""
        def bad_fix(params):
            raise RuntimeError("Test error")
        
        engine.register(AutoFix(
            id="error-fix",
            name="Error Fix",
            description="A fix that throws",
            risk=FixRisk.LOW,
            fix_fn=bad_fix,
        ))
        
        result = engine.execute("error-fix")
        
        assert result.status == FixStatus.FAILED
        assert "exception" in result.message.lower()
    
    def test_execute_dry_run(self, engine):
        """Test dry run mode."""
        engine.register(AutoFix(
            id="dry-fix",
            name="Dry Fix",
            description="A fix to dry run",
            risk=FixRisk.LOW,
            steps=["Step 1", "Step 2"],
            fix_fn=lambda p: (True, "Fixed", {}),
        ))
        
        result = engine.execute("dry-fix", dry_run=True)
        
        assert result.status == FixStatus.PENDING
        assert "steps" in result.details
    
    def test_high_risk_requires_approval(self, engine):
        """Test that high risk fixes require approval."""
        engine.register(AutoFix(
            id="risky-fix",
            name="Risky Fix",
            description="A high risk fix",
            risk=FixRisk.HIGH,
            fix_fn=lambda p: (True, "Fixed", {}),
        ))
        
        # Without approval token
        result = engine.execute("risky-fix")
        
        assert result.status == FixStatus.PENDING
        assert result.details.get("requires_approval") is True
    
    def test_fix_with_prerequisites(self, engine):
        """Test fix with prerequisites."""
        engine.register(AutoFix(
            id="prereq-fix",
            name="Prerequisite Fix",
            description="Must run first",
            risk=FixRisk.LOW,
            fix_fn=lambda p: (True, "Prereq done", {}),
        ))
        
        engine.register(AutoFix(
            id="dependent-fix",
            name="Dependent Fix",
            description="Depends on prereq",
            risk=FixRisk.LOW,
            prerequisites=["prereq-fix"],
            fix_fn=lambda p: (True, "Done", {}),
        ))
        
        # Without prerequisite
        result = engine.execute("dependent-fix")
        assert result.status == FixStatus.SKIPPED
        
        # Run prerequisite
        engine.execute("prereq-fix")
        
        # Now dependent should work
        result = engine.execute("dependent-fix")
        assert result.status == FixStatus.SUCCESS
    
    def test_rollback(self, engine):
        """Test fix rollback."""
        rollback_called = {"called": False}
        
        def rollback_fn(data):
            rollback_called["called"] = True
            return True, "Rolled back"
        
        engine.register(AutoFix(
            id="rollback-fix",
            name="Rollback Fix",
            description="Can be rolled back",
            risk=FixRisk.LOW,
            fix_fn=lambda p: (True, "Fixed", {"rollback_data": {"key": "value"}}),
            rollback_fn=rollback_fn,
        ))
        
        # Execute fix
        engine.execute("rollback-fix")
        
        # Rollback
        result = engine.rollback("rollback-fix")
        
        assert result.status == FixStatus.ROLLED_BACK
        assert rollback_called["called"] is True
    
    def test_history_tracking(self, engine):
        """Test fix history tracking."""
        engine.register(AutoFix(
            id="history-fix",
            name="History Fix",
            description="Track in history",
            risk=FixRisk.LOW,
            fix_fn=lambda p: (True, "Fixed", {}),
        ))
        
        engine.execute("history-fix")
        engine.execute("history-fix")
        
        history = engine.get_history(fix_id="history-fix")
        
        assert len(history) >= 2
    
    def test_disabled_fix_skipped(self, engine):
        """Test that disabled fixes are skipped."""
        engine.register(AutoFix(
            id="disabled-fix",
            name="Disabled Fix",
            description="Is disabled",
            risk=FixRisk.LOW,
            enabled=False,
            fix_fn=lambda p: (True, "Fixed", {}),
        ))
        
        result = engine.execute("disabled-fix")
        
        assert result.status == FixStatus.SKIPPED

    def test_fix_reset_providers_uses_current_provider_manager_api(self, engine):
        """Reset providers fix should use check_all_health and report healthy count."""
        class _FakeProviderManager:
            def auto_configure(self):
                return 2

            def check_all_health(self):
                return {
                    "provider-a": {"available": True},
                    "provider-b": {"available": False},
                }

        with patch("modules.providers.provider_manager.ProviderManager", _FakeProviderManager):
            success, message, details = engine._fix_reset_providers({})

        assert success is True
        assert message == "Providers reset: 1 healthy"
        assert "providers" in details

    def test_fix_reset_providers_reports_missing_configuration(self, engine):
        """Reset providers fix should fail with guidance when no providers can be configured."""
        class _FakeProviderManager:
            def auto_configure(self):
                return 0

            def check_all_health(self):
                return {}

        with patch("modules.providers.provider_manager.ProviderManager", _FakeProviderManager):
            success, message, details = engine._fix_reset_providers({})

        assert success is False
        assert message == "No providers configured. Set API keys and retry."
        assert details["fix_id"] == "set-api-key"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
