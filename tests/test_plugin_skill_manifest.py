"""Tests for OpenClaw SKILL.md compatibility in PluginRegistry."""

from pathlib import Path

from modules.plugin_system import PluginRegistry


def test_skill_manifest_discovery_and_execution(tmp_path: Path):
    plugins_dir = tmp_path / "plugins"
    plugin_dir = plugins_dir / "demo_skill"
    plugin_dir.mkdir(parents=True, exist_ok=True)

    skill_md = plugin_dir / "SKILL.md"
    skill_md.write_text(
        """---
name: demo_skill
version: 1.0.0
author: test
triggers: [\"hello skill\"]
---

# Demo Skill

Simple demo skill.

## Actions

### greet(query)
Returns a greeting.
""",
        encoding="utf-8",
    )

    skill_py = plugin_dir / "skill.py"
    skill_py.write_text(
        """def greet(query=''):\n    return f'handled:{query}'\n""",
        encoding="utf-8",
    )

    registry = PluginRegistry(plugins_dir=str(plugins_dir))

    discovered = registry.discover_plugins()
    assert "demo_skill" in discovered

    assert registry.load_plugin("demo_skill") is True
    assert registry.activate_plugin("demo_skill") is True

    result = registry.execute_handler("please hello skill now")
    assert result is not None
    assert "handled:please hello skill now" in result
