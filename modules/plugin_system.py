"""
LADA - Plugin System
OpenClaw-style extensible plugin architecture with manifest-based discovery,
capability registry, and lifecycle management.

Features:
- YAML manifest-based plugin discovery
- Capability-to-handler registry
- Plugin lifecycle hooks (init, activate, deactivate)
- Safe plugin loading with validation
- Plugin metadata and dependency checking
"""

import os
import time
import sys
import importlib
import logging
import json
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)

# Try to import YAML; fall back to JSON manifests
try:
    import yaml
    YAML_OK = True
except ImportError:
    YAML_OK = False
    logger.info("PyYAML not available, using JSON manifests only")

# Try to import watchdog for hot-reload support
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler as _FSHandler
    WATCHDOG_OK = True
except ImportError:
    WATCHDOG_OK = False
    Observer = None
    _FSHandler = object  # fallback base class


class PluginWatcher(_FSHandler):
    """
    File system watcher enabling hot-reload of plugins while LADA is running.
    Requires: pip install watchdog
    """
    def __init__(self, registry: 'PluginRegistry'):
        super().__init__()
        self._registry = registry
        self._debounce: Dict[str, float] = {}

    def on_modified(self, event) -> None:
        if event.is_directory:
            return
        plugin_dir_name = Path(event.src_path).parent.name
        now = time.time()
        # Debounce: ignore rapid successive events within 500ms
        if now - self._debounce.get(plugin_dir_name, 0) < 0.5:
            return
        self._debounce[plugin_dir_name] = now
        logger.info(f"[PluginSystem] Hot-reload triggered: {plugin_dir_name}")
        try:
            self._registry.deactivate_plugin(plugin_dir_name)
        except Exception:
            pass
        try:
            self._registry.unload_plugin(plugin_dir_name)
        except Exception:
            pass
        try:
            self._registry.load_plugin(plugin_dir_name)
            self._registry.activate_plugin(plugin_dir_name)
            logger.info(f"[PluginSystem] Hot-reloaded: {plugin_dir_name}")
        except Exception as e:
            logger.warning(f"[PluginSystem] Hot-reload failed for {plugin_dir_name}: {e}")

    def on_created(self, event) -> None:
        if not event.is_directory:
            return
        new_dir = Path(event.src_path).name
        if new_dir.startswith(('_', '.')):
            return
        logger.info(f"[PluginSystem] New plugin directory detected: {new_dir}")
        try:
            self._registry.discover_plugins()
            self._registry.load_all()
        except Exception as e:
            logger.warning(f"[PluginSystem] Auto-load failed for {new_dir}: {e}")

    def on_deleted(self, event) -> None:
        if not event.is_directory:
            return
        plugin_dir_name = Path(event.src_path).name
        logger.info(f"[PluginSystem] Plugin directory removed: {plugin_dir_name}")
        try:
            self._registry.unload_plugin(plugin_dir_name)
        except Exception:
            pass


class PluginState(Enum):
    """Plugin lifecycle states"""
    DISCOVERED = "discovered"
    LOADED = "loaded"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


@dataclass
class PluginManifest:
    """Plugin manifest describing metadata and capabilities"""
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    entry_point: str = "main.py"  # Relative to plugin directory
    class_name: str = ""  # Main class to instantiate
    capabilities: List[Dict[str, Any]] = field(default_factory=list)
    # Each capability: {'intent': str, 'keywords': List[str], 'handler': str}
    dependencies: List[str] = field(default_factory=list)  # pip packages
    permissions: List[str] = field(default_factory=list)  # Required permissions
    min_lada_version: str = ""
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PluginManifest':
        """Create manifest from dictionary (parsed YAML/JSON)."""
        return cls(
            name=data.get('name', 'unnamed'),
            version=data.get('version', '1.0.0'),
            description=data.get('description', ''),
            author=data.get('author', ''),
            entry_point=data.get('entry_point', 'main.py'),
            class_name=data.get('class_name', ''),
            capabilities=data.get('capabilities', []),
            dependencies=data.get('dependencies', []),
            permissions=data.get('permissions', []),
            min_lada_version=data.get('min_lada_version', ''),
            enabled=data.get('enabled', True),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            'name': self.name,
            'version': self.version,
            'description': self.description,
            'author': self.author,
            'entry_point': self.entry_point,
            'class_name': self.class_name,
            'capabilities': self.capabilities,
            'dependencies': self.dependencies,
            'permissions': self.permissions,
            'min_lada_version': self.min_lada_version,
            'enabled': self.enabled,
        }


@dataclass
class LoadedPlugin:
    """A loaded plugin instance with its metadata"""
    manifest: PluginManifest
    state: PluginState = PluginState.DISCOVERED
    instance: Any = None  # The plugin class instance
    module: Any = None  # The imported module
    directory: str = ""
    error: Optional[str] = None
    handlers: Dict[str, Callable] = field(default_factory=dict)
    # Maps intent -> handler method


class PluginRegistry:
    """
    Central registry for discovering, loading, and managing plugins.

    Directory structure expected:
    plugins/
      my_plugin/
        plugin.yaml (or plugin.json)
        main.py
        ...
    """

    MANIFEST_FILES = ['plugin.yaml', 'plugin.yml', 'plugin.json']

    def __init__(self, plugins_dir: Optional[str] = None):
        """
        Initialize plugin registry.

        Args:
            plugins_dir: Path to plugins directory. Defaults to ./plugins/
        """
        if plugins_dir:
            self.plugins_dir = Path(plugins_dir)
        else:
            self.plugins_dir = Path(os.path.dirname(os.path.dirname(__file__))) / 'plugins'

        self.plugins: Dict[str, LoadedPlugin] = {}
        self.capability_map: Dict[str, List[str]] = {}
        # Maps intent keyword -> [plugin_name, ...]

        # Ensure plugins directory exists
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"[PluginSystem] Registry initialized: {self.plugins_dir}")

    def discover_plugins(self) -> List[str]:
        """
        Scan plugins directory for plugin manifests.
        Returns list of discovered plugin names.
        """
        discovered = []

        if not self.plugins_dir.exists():
            logger.warning(f"[PluginSystem] Plugins directory not found: {self.plugins_dir}")
            return discovered

        for item in self.plugins_dir.iterdir():
            if not item.is_dir():
                continue
            if item.name.startswith(('_', '.')):
                continue

            manifest = self._load_manifest(item)
            if manifest:
                self.plugins[manifest.name] = LoadedPlugin(
                    manifest=manifest,
                    state=PluginState.DISCOVERED,
                    directory=str(item),
                )
                discovered.append(manifest.name)
                logger.info(f"[PluginSystem] Discovered: {manifest.name} v{manifest.version}")

        logger.info(f"[PluginSystem] Discovered {len(discovered)} plugins")
        return discovered

    def _load_manifest(self, plugin_dir: Path) -> Optional[PluginManifest]:
        """Load plugin manifest from directory."""
        for manifest_file in self.MANIFEST_FILES:
            manifest_path = plugin_dir / manifest_file
            if manifest_path.exists():
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        if manifest_file.endswith('.json'):
                            data = json.load(f)
                        elif YAML_OK:
                            data = yaml.safe_load(f)
                        else:
                            logger.warning(f"[PluginSystem] YAML not available, skipping {manifest_path}")
                            continue

                    return PluginManifest.from_dict(data)
                except Exception as e:
                    logger.error(f"[PluginSystem] Error loading manifest {manifest_path}: {e}")

        return None

    def load_plugin(self, name: str) -> bool:
        """
        Load a discovered plugin by importing its module and instantiating its class.
        Returns True on success.
        """
        if name not in self.plugins:
            logger.error(f"[PluginSystem] Plugin not found: {name}")
            return False

        plugin = self.plugins[name]
        manifest = plugin.manifest

        if not manifest.enabled:
            logger.info(f"[PluginSystem] Plugin disabled: {name}")
            plugin.state = PluginState.INACTIVE
            return False

        try:
            # Check dependencies
            if not self._check_dependencies(manifest.dependencies):
                plugin.state = PluginState.ERROR
                plugin.error = "Missing dependencies"
                return False

            # Import the module
            plugin_dir = Path(plugin.directory)
            entry_path = plugin_dir / manifest.entry_point

            if not entry_path.exists():
                plugin.state = PluginState.ERROR
                plugin.error = f"Entry point not found: {manifest.entry_point}"
                return False

            # Add plugin directory to path temporarily
            if str(plugin_dir) not in sys.path:
                sys.path.insert(0, str(plugin_dir))

            # Import the module
            module_name = f"plugins.{name}.{manifest.entry_point.replace('.py', '')}"
            spec = importlib.util.spec_from_file_location(module_name, entry_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            plugin.module = module

            # Instantiate the main class if specified
            if manifest.class_name and hasattr(module, manifest.class_name):
                cls = getattr(module, manifest.class_name)
                plugin.instance = cls()

                # Register capability handlers
                for cap in manifest.capabilities:
                    handler_name = cap.get('handler', '')
                    intent = cap.get('intent', '')
                    if handler_name and hasattr(plugin.instance, handler_name):
                        plugin.handlers[intent] = getattr(plugin.instance, handler_name)
                        # Register keywords for intent routing
                        for keyword in cap.get('keywords', []):
                            kw = keyword.lower()
                            if kw not in self.capability_map:
                                self.capability_map[kw] = []
                            self.capability_map[kw].append(name)

            plugin.state = PluginState.LOADED

            # Call init hook if available
            if plugin.instance and hasattr(plugin.instance, 'on_load'):
                plugin.instance.on_load()

            logger.info(f"[PluginSystem] Loaded: {name} ({len(plugin.handlers)} handlers)")
            return True

        except Exception as e:
            plugin.state = PluginState.ERROR
            plugin.error = str(e)
            logger.error(f"[PluginSystem] Failed to load {name}: {e}")
            return False

    def activate_plugin(self, name: str) -> bool:
        """Activate a loaded plugin."""
        if name not in self.plugins:
            return False

        plugin = self.plugins[name]
        if plugin.state != PluginState.LOADED:
            return False

        try:
            if plugin.instance and hasattr(plugin.instance, 'on_activate'):
                plugin.instance.on_activate()
            plugin.state = PluginState.ACTIVE
            logger.info(f"[PluginSystem] Activated: {name}")
            return True
        except Exception as e:
            plugin.error = str(e)
            logger.error(f"[PluginSystem] Activation failed for {name}: {e}")
            return False

    def deactivate_plugin(self, name: str) -> bool:
        """Deactivate an active plugin."""
        if name not in self.plugins:
            return False

        plugin = self.plugins[name]
        if plugin.state != PluginState.ACTIVE:
            return False

        try:
            if plugin.instance and hasattr(plugin.instance, 'on_deactivate'):
                plugin.instance.on_deactivate()
            plugin.state = PluginState.INACTIVE

            # Remove from capability map
            for kw, plugins in list(self.capability_map.items()):
                if name in plugins:
                    plugins.remove(name)
                    if not plugins:
                        del self.capability_map[kw]

            logger.info(f"[PluginSystem] Deactivated: {name}")
            return True
        except Exception as e:
            logger.error(f"[PluginSystem] Deactivation failed for {name}: {e}")
            return False

    def unload_plugin(self, name: str) -> bool:
        """Fully unload a plugin (for hot-reload)."""
        if name not in self.plugins:
            return False

        self.deactivate_plugin(name)

        plugin = self.plugins[name]
        if plugin.instance and hasattr(plugin.instance, 'on_unload'):
            try:
                plugin.instance.on_unload()
            except Exception:
                pass

        plugin.instance = None
        plugin.module = None
        plugin.handlers = {}
        plugin.state = PluginState.DISCOVERED

        logger.info(f"[PluginSystem] Unloaded: {name}")
        return True

    def load_all(self) -> Dict[str, bool]:
        """Discover and load all plugins. Returns {name: success}."""
        self.discover_plugins()
        results = {}
        for name in list(self.plugins.keys()):
            success = self.load_plugin(name)
            if success:
                self.activate_plugin(name)
            results[name] = success
        return results

    def find_handler(self, query: str) -> Optional[tuple]:
        """
        Find a plugin handler that matches the query.
        Returns (plugin_name, intent, handler_callable) or None.
        """
        q = query.lower()
        for keyword, plugin_names in self.capability_map.items():
            if keyword in q:
                for pname in plugin_names:
                    plugin = self.plugins.get(pname)
                    if plugin and plugin.state == PluginState.ACTIVE:
                        # Find which intent this keyword maps to
                        for cap in plugin.manifest.capabilities:
                            if keyword in [k.lower() for k in cap.get('keywords', [])]:
                                intent = cap.get('intent', '')
                                handler = plugin.handlers.get(intent)
                                if handler:
                                    return (pname, intent, handler)
        return None

    def execute_handler(self, query: str) -> Optional[str]:
        """
        Try to find and execute a plugin handler for the query.
        Returns the handler result or None if no handler matched.
        """
        match = self.find_handler(query)
        if not match:
            return None

        pname, intent, handler = match
        try:
            logger.info(f"[PluginSystem] Executing {pname}.{intent}")
            result = handler(query)
            return str(result) if result is not None else None
        except Exception as e:
            logger.error(f"[PluginSystem] Handler error ({pname}.{intent}): {e}")
            return None

    def get_plugin_list(self) -> List[Dict[str, Any]]:
        """Get plugin list with status for UI display."""
        return [
            {
                'name': p.manifest.name,
                'version': p.manifest.version,
                'description': p.manifest.description,
                'author': p.manifest.author,
                'state': p.state.value,
                'error': p.error,
                'capabilities': len(p.manifest.capabilities),
                'handlers': len(p.handlers),
            }
            for p in self.plugins.values()
        ]

    def _check_dependencies(self, dependencies: List[str]) -> bool:
        """Check if required pip packages are installed."""
        for dep in dependencies:
            # Extract package name (strip version specifiers)
            pkg = dep.split('>=')[0].split('==')[0].split('<=')[0].strip()
            try:
                importlib.import_module(pkg.replace('-', '_'))
            except ImportError:
                logger.warning(f"[PluginSystem] Missing dependency: {dep}")
                return False
        return True

    def start_watcher(self) -> bool:
        """
        Start filesystem watcher for hot-reloading plugins without restart.
        Requires watchdog: pip install watchdog

        Returns True if watcher started successfully, False if unavailable.
        """
        if not WATCHDOG_OK:
            logger.info("[PluginSystem] watchdog not installed — hot-reload disabled (pip install watchdog)")
            return False
        if getattr(self, '_observer', None) is not None:
            try:
                if self._observer.is_alive():
                    return True  # already running
            except Exception:
                pass
        try:
            self._observer = Observer()
            self._observer.schedule(
                PluginWatcher(self),
                str(self.plugins_dir),
                recursive=True,
            )
            self._observer.start()
            logger.info(f"[PluginSystem] Hot-reload active — watching {self.plugins_dir}")
            return True
        except Exception as e:
            logger.warning(f"[PluginSystem] Could not start plugin watcher: {e}")
            return False

    def stop_watcher(self) -> None:
        """Stop the filesystem watcher gracefully."""
        observer = getattr(self, '_observer', None)
        if observer is not None:
            try:
                observer.stop()
                observer.join(timeout=2.0)
            except Exception:
                pass
            self._observer = None
            logger.info("[PluginSystem] Hot-reload watcher stopped")


# Singleton
_plugin_registry = None


def get_plugin_registry(plugins_dir: Optional[str] = None) -> PluginRegistry:
    """Get or create plugin registry instance."""
    global _plugin_registry
    if _plugin_registry is None:
        _plugin_registry = PluginRegistry(plugins_dir=plugins_dir)
    return _plugin_registry
