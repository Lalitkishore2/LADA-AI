"""Phase 2 tests for SKILL.md adapter, plugin hot-reload, and command routing."""

from types import SimpleNamespace

from lada_jarvis_core import JarvisCommandProcessor
from modules.openclaw_skill_adapter import parse_skill_manifest
from modules.plugin_system import PluginWatcher


class _NoopExecutor:
    def try_handle(self, _cmd: str):
        return False, ""


class _FakePluginRegistry:
    def __init__(self, plugins_dir):
        self.plugins_dir = plugins_dir
        self.calls = []

    def resolve_plugin_name(self, directory_name: str):
        self.calls.append(("resolve", directory_name))
        return "demo-skill"

    def deactivate_plugin(self, name: str):
        self.calls.append(("deactivate", name))

    def unload_plugin(self, name: str):
        self.calls.append(("unload", name))

    def load_plugin(self, name: str):
        self.calls.append(("load", name))
        return True

    def activate_plugin(self, name: str):
        self.calls.append(("activate", name))
        return True

    def discover_plugins(self):
        self.calls.append(("discover",))


class _DummyCommandRegistry:
    def __init__(self):
        self.queries = []

    def execute_handler(self, query: str):
        self.queries.append(query)
        return "plugin handled"


def test_skill_adapter_parses_skill_markdown(tmp_path):
    plugin_dir = tmp_path / "demo_skill"
    plugin_dir.mkdir(parents=True, exist_ok=True)

    (plugin_dir / "skill.py").write_text(
        "def greet(query=''):\n    return f'hello:{query}'\n",
        encoding="utf-8",
    )

    skill_path = plugin_dir / "SKILL.md"
    skill_path.write_text(
        """---
name: demo_skill
version: 1.2.3
author: tester
triggers: [\"hello skill\", \"demo trigger\"]
dependencies: [\"requests\"]
permissions: [\"network\"]
enabled: true
---

# Demo Skill

Simple demo skill.

## Actions

### greet(query)
Returns a greeting.
""",
        encoding="utf-8",
    )

    manifest = parse_skill_manifest(
        skill_path=skill_path,
        plugin_dir=plugin_dir,
        yaml_loader=None,
        default_plugin_api_version="1",
    )

    assert manifest is not None
    assert manifest["name"] == "demo_skill"
    assert manifest["entry_point"] == "skill.py"
    assert manifest["enabled"] is True
    assert manifest["dependencies"] == ["requests"]
    assert manifest["permissions"] == ["network"]
    assert manifest["capabilities"][0]["intent"] == "greet"
    assert manifest["capabilities"][0]["keywords"] == ["hello skill", "demo trigger"]


def test_plugin_watcher_debounces_skill_file_reload(tmp_path, monkeypatch):
    plugins_dir = tmp_path / "plugins"
    (plugins_dir / "demo_skill").mkdir(parents=True, exist_ok=True)

    registry = _FakePluginRegistry(plugins_dir)
    watcher = PluginWatcher(registry)

    times = iter([100.0, 100.2])
    monkeypatch.setattr("modules.plugin_system.time.time", lambda: next(times))

    event = SimpleNamespace(
        is_directory=False,
        src_path=str(plugins_dir / "demo_skill" / "nested" / "hello.skill.md"),
    )

    watcher.on_modified(event)
    watcher.on_modified(event)

    assert registry.calls.count(("deactivate", "demo-skill")) == 1
    assert registry.calls.count(("unload", "demo-skill")) == 1
    assert registry.calls.count(("load", "demo-skill")) == 1
    assert registry.calls.count(("activate", "demo-skill")) == 1


def test_process_routes_to_plugin_handler_when_builtins_do_not_match():
    proc = JarvisCommandProcessor.__new__(JarvisCommandProcessor)
    proc._record_activity = lambda: None
    proc.pending_confirmation = None
    proc.privacy_mode = False
    proc.executors = [_NoopExecutor()]
    proc.files = None
    proc.plugin_registry = _DummyCommandRegistry()
    proc._plugin_commands_enabled = True
    proc._plugin_handlers_ready = True

    handled, response = JarvisCommandProcessor.process(
        proc,
        "launch my custom workspace automation",
    )

    assert handled is True
    assert response == "plugin handled"
    assert proc.plugin_registry.queries == ["launch my custom workspace automation"]
