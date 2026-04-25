"""Phase 6 rollout flag and compatibility validation tests."""

from types import SimpleNamespace

from modules.ai_command_agent import AICommandAgent


class _DummyProviderManager:
    def get_best_model(self, _text, tier=None):
        return {"model_id": "gpt-test", "provider_id": "openai", "tier": tier}

    def get_provider_for_model(self, _model_id):
        return SimpleNamespace()


class _DummyToolRegistry:
    def __init__(self):
        self._tools = []

    def to_ai_schema(self):
        return []


def test_skill_md_flag_disables_plugin_path_by_default(monkeypatch):
    monkeypatch.setenv("LADA_SKILL_MD_ENABLED", "false")

    agent = AICommandAgent(_DummyProviderManager(), _DummyToolRegistry(), config={"comet_enabled": False})

    assert agent.plugin_enabled is False


def test_skill_md_flag_enables_plugin_path_by_default(monkeypatch):
    monkeypatch.setenv("LADA_SKILL_MD_ENABLED", "true")

    agent = AICommandAgent(_DummyProviderManager(), _DummyToolRegistry(), config={"comet_enabled": False})

    assert agent.plugin_enabled is True


def test_explicit_config_overrides_skill_md_default(monkeypatch):
    monkeypatch.setenv("LADA_SKILL_MD_ENABLED", "false")

    agent = AICommandAgent(
        _DummyProviderManager(),
        _DummyToolRegistry(),
        config={"plugin_enabled": True, "comet_enabled": False},
    )

    assert agent.plugin_enabled is True
