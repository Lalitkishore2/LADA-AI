"""Phase 1 tests for OpenClaw compatibility restoration and env-gated startup."""

from core.services import ServiceRegistry, build_default_registry
from integrations.lada_browser_adapter import LadaBrowserAdapter
from integrations.openclaw_gateway import OpenClawConfig


def test_default_registry_includes_openclaw_services():
    registry = build_default_registry()

    keys = set(registry.keys())
    assert "openclaw_gateway" in keys
    assert "openclaw_skills" in keys


def test_openclaw_services_are_env_gated(monkeypatch):
    registry = ServiceRegistry()
    registry.register(
        "openclaw_gateway",
        "integrations.openclaw_gateway",
        ["OpenClawGateway"],
        env_flag="LADA_OPENCLAW_MODE",
    )

    monkeypatch.delenv("LADA_OPENCLAW_MODE", raising=False)
    first_probe = registry.probe_all()
    assert first_probe["openclaw_gateway"] is False

    monkeypatch.setenv("LADA_OPENCLAW_MODE", "true")
    second_probe = registry.probe_all()
    assert second_probe["openclaw_gateway"] is True


def test_openclaw_gateway_config_uses_lada_env(monkeypatch):
    monkeypatch.setenv("LADA_OPENCLAW_GATEWAY_URL", "ws://localhost:19999")
    monkeypatch.setenv("LADA_OPENCLAW_RECONNECT", "false")
    monkeypatch.setenv("LADA_OPENCLAW_DEBUG", "true")

    # Ensure legacy aliases are not required when LADA_* vars are present.
    monkeypatch.delenv("OPENCLAW_GATEWAY_URL", raising=False)
    monkeypatch.delenv("OPENCLAW_RECONNECT", raising=False)
    monkeypatch.delenv("OPENCLAW_DEBUG", raising=False)

    config = OpenClawConfig.from_env()

    assert config.url == "ws://localhost:19999"
    assert config.auto_reconnect is False
    assert config.debug is True


def test_browser_adapter_prefers_active_openclaw_module_path():
    adapter = LadaBrowserAdapter(enabled=False)

    module_path = adapter._gateway_module_path()

    assert module_path.as_posix().endswith("integrations/openclaw_gateway.py")
