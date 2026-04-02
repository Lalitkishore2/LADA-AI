"""Tests for plugin runtime/API version compatibility checks."""

import json
from pathlib import Path

from modules.plugin_system import PluginRegistry, PluginState


def _write_plugin(plugin_root: Path, name: str, overrides: dict) -> Path:
    plugin_dir = plugin_root / name
    plugin_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": name,
        "version": "1.0.0",
        "description": "Versioned plugin",
        "entry_point": "main.py",
        "capabilities": [
            {
                "intent": "greet",
                "keywords": ["hello plugin"],
                "handler": "greet",
            }
        ],
        "plugin_api_version": "1",
    }
    manifest.update(overrides)

    (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin_dir / "main.py").write_text(
        "def greet(query=''):\n    return f'hello:{query}'\n",
        encoding="utf-8",
    )

    return plugin_dir


def test_plugin_rejected_when_min_version_not_met(tmp_path, monkeypatch):
    monkeypatch.setenv("LADA_VERSION", "8.0.0")
    monkeypatch.setenv("LADA_PLUGIN_API_VERSION", "1")

    _write_plugin(tmp_path, "future_plugin", {"min_lada_version": "9.0.0"})

    registry = PluginRegistry(plugins_dir=str(tmp_path))
    registry.discover_plugins()

    loaded = registry.load_plugin("future_plugin")

    assert loaded is False
    plugin = registry.plugins["future_plugin"]
    assert plugin.state == PluginState.ERROR
    assert "Requires LADA >= 9.0.0" in (plugin.error or "")


def test_plugin_rejected_when_api_major_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv("LADA_VERSION", "8.0.0")
    monkeypatch.setenv("LADA_PLUGIN_API_VERSION", "2")

    _write_plugin(tmp_path, "api_mismatch", {"plugin_api_version": "1"})

    registry = PluginRegistry(plugins_dir=str(tmp_path))
    registry.discover_plugins()

    loaded = registry.load_plugin("api_mismatch")

    assert loaded is False
    plugin = registry.plugins["api_mismatch"]
    assert plugin.state == PluginState.ERROR
    assert "Plugin API mismatch" in (plugin.error or "")


def test_plugin_loads_when_versions_are_compatible(tmp_path, monkeypatch):
    monkeypatch.setenv("LADA_VERSION", "8.3.0")
    monkeypatch.setenv("LADA_PLUGIN_API_VERSION", "1")

    _write_plugin(
        tmp_path,
        "compatible_plugin",
        {
            "min_lada_version": "8.0.0",
            "max_lada_version": "9.0.0",
            "plugin_api_version": "1",
        },
    )

    registry = PluginRegistry(plugins_dir=str(tmp_path))
    discovered = registry.discover_plugins()
    assert "compatible_plugin" in discovered

    loaded = registry.load_plugin("compatible_plugin")
    activated = registry.activate_plugin("compatible_plugin")

    assert loaded is True
    assert activated is True

    plugin_info = registry.get_plugin_list()[0]
    assert plugin_info["plugin_api_version"] == "1"
    assert plugin_info["min_lada_version"] == "8.0.0"
    assert plugin_info["max_lada_version"] == "9.0.0"
