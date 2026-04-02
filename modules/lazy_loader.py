"""
LADA v9.0 - Lazy Module Loader
Dramatically improves startup time by loading modules only when needed.

Before: ~10-15 seconds to load all 12 modules
After:  ~2-3 seconds (only essential modules loaded)

Also includes PluginWatcher for hot-reload of plugins via watchdog.
"""

import logging
import time
import threading
from typing import Dict, Any, Optional, Callable
from pathlib import Path
from functools import wraps

logger = logging.getLogger(__name__)


class LazyModuleLoader:
    """
    Lazy load modules only when first accessed.
    Thread-safe with double-checked locking pattern.
    """
    
    def __init__(self):
        self._modules: Dict[str, Any] = {}
        self._factories: Dict[str, Callable] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._load_times: Dict[str, float] = {}
        self._errors: Dict[str, str] = {}
        self._global_lock = threading.Lock()
        
    def register(self, name: str, factory: Callable):
        """
        Register a module factory for lazy loading.
        Factory is a callable that returns the module instance.
        """
        with self._global_lock:
            self._factories[name] = factory
            self._locks[name] = threading.Lock()
        logger.debug(f"[LazyLoader] Registered: {name}")
    
    def get(self, name: str) -> Optional[Any]:
        """
        Get a module, loading it on first access.
        Thread-safe with double-checked locking.
        """
        # Fast path: already loaded
        if name in self._modules:
            return self._modules[name]
        
        # Check if registered
        if name not in self._factories:
            logger.warning(f"[LazyLoader] Module not registered: {name}")
            return None
        
        # Slow path: need to load
        lock = self._locks.get(name)
        if not lock:
            return None
            
        with lock:
            # Double-check after acquiring lock
            if name in self._modules:
                return self._modules[name]
            
            try:
                start = time.time()
                logger.info(f"[LazyLoader] Loading {name}...")
                
                module = self._factories[name]()
                self._modules[name] = module
                
                load_time = time.time() - start
                self._load_times[name] = load_time
                
                logger.info(f"[LazyLoader] Loaded {name} in {load_time:.2f}s")
                return module
            
            except Exception as e:
                self._errors[name] = str(e)
                logger.error(f"[LazyLoader] Failed to load {name}: {e}")
                return None
    
    def get_or_none(self, name: str) -> Optional[Any]:
        """Get module if loaded, otherwise return None without loading."""
        return self._modules.get(name)
    
    def is_loaded(self, name: str) -> bool:
        """Check if a module is already loaded."""
        return name in self._modules
    
    def preload_async(self, *names: str):
        """Preload specific modules in background threads."""
        def load_module(name: str):
            try:
                self.get(name)
            except Exception as e:
                logger.error(f"[LazyLoader] Preload failed for {name}: {e}")
        
        for name in names:
            if name not in self._modules and name in self._factories:
                thread = threading.Thread(
                    target=load_module, 
                    args=(name,), 
                    daemon=True,
                    name=f"Preload-{name}"
                )
                thread.start()
    
    def preload_sync(self, *names: str):
        """Preload specific modules synchronously."""
        for name in names:
            if name not in self._modules:
                self.get(name)
    
    def unload(self, name: str) -> bool:
        """Unload a module to free memory."""
        if name in self._modules:
            with self._locks.get(name, threading.Lock()):
                if name in self._modules:
                    del self._modules[name]
                    if name in self._load_times:
                        del self._load_times[name]
                    logger.info(f"[LazyLoader] Unloaded {name}")
                    return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get loading statistics."""
        return {
            'registered': list(self._factories.keys()),
            'loaded': list(self._modules.keys()),
            'pending': [n for n in self._factories if n not in self._modules],
            'load_times': self._load_times.copy(),
            'total_load_time': sum(self._load_times.values()),
            'errors': self._errors.copy()
        }
    
    def __contains__(self, name: str) -> bool:
        return name in self._factories
    
    def __getitem__(self, name: str) -> Any:
        result = self.get(name)
        if result is None and name not in self._factories:
            raise KeyError(f"Module not registered: {name}")
        return result


# Module priority for startup optimization
class ModulePriority:
    """Define module loading priorities."""
    
    # Load immediately on startup (essential for basic operation)
    CRITICAL = [
        'nlu_engine',
        'memory_system',
    ]
    
    # Load in background right after startup
    HIGH = [
        'advanced_system_control',
        'window_manager',
        'gui_automator',
        'workflow_engine',
    ]
    
    # Load on first use
    MEDIUM = [
        'browser_tab_controller',
        'multi_tab_orchestrator',
        'task_orchestrator',
        'screen_vision',
    ]
    
    # Load only when explicitly needed
    LOW = [
        'gmail_controller',
        'calendar_controller',
        'screenshot_analysis',
        'pattern_learning',
        'proactive_agent',
    ]
    
    @classmethod
    def get_startup_modules(cls) -> list:
        """Get modules to load on startup."""
        return cls.CRITICAL
    
    @classmethod
    def get_background_modules(cls) -> list:
        """Get modules to preload in background."""
        return cls.HIGH
    
    @classmethod
    def get_all_ordered(cls) -> list:
        """Get all modules in priority order."""
        return cls.CRITICAL + cls.HIGH + cls.MEDIUM + cls.LOW


def lazy_property(loader_attr: str, module_name: str):
    """
    Decorator to create a lazy-loaded property.
    
    Usage:
        class MyClass:
            def __init__(self):
                self._loader = LazyModuleLoader()
            
            @lazy_property('_loader', 'my_module')
            def my_module(self):
                pass  # Property body is ignored
    """
    def decorator(func):
        prop_name = f'_lazy_{func.__name__}'
        
        @property
        @wraps(func)
        def wrapper(self):
            loader = getattr(self, loader_attr, None)
            if loader:
                return loader.get(module_name)
            return None
        
        return wrapper
    return decorator


# Global lazy loader instance
_global_loader: Optional[LazyModuleLoader] = None

def get_lazy_loader() -> LazyModuleLoader:
    """Get or create global lazy loader instance."""
    global _global_loader
    if _global_loader is None:
        _global_loader = LazyModuleLoader()
    return _global_loader


# =====================================================
# HOT-RELOAD: Plugin File Watcher
# =====================================================

# Conditional import for watchdog
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileSystemEvent
    WATCHDOG_OK = True
except ImportError:
    WATCHDOG_OK = False
    Observer = None
    FileSystemEventHandler = object


class PluginWatcher(FileSystemEventHandler if WATCHDOG_OK else object):
    """
    Watches the plugins/ directory for changes and hot-reloads plugins.

    Requires the 'watchdog' package. If not installed, hot-reload is disabled.

    Usage:
        from modules.plugin_system import get_plugin_registry
        registry = get_plugin_registry()
        watcher = PluginWatcher(registry)
        watcher.start()
    """

    DEBOUNCE_SECONDS = 0.5

    def __init__(self, plugin_registry=None, watch_dir: Optional[str] = None):
        if WATCHDOG_OK:
            super().__init__()

        self.plugin_registry = plugin_registry

        if watch_dir:
            self.watch_dir = Path(watch_dir)
        else:
            self.watch_dir = Path(__file__).parent.parent / 'plugins'

        self._observer = None
        self._running = False
        self._debounce_timers: Dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def start(self) -> bool:
        """Start watching the plugins directory."""
        if not WATCHDOG_OK:
            logger.warning("[PluginWatcher] watchdog not installed, hot-reload disabled")
            return False

        if not self.watch_dir.exists():
            logger.warning(f"[PluginWatcher] Watch directory not found: {self.watch_dir}")
            return False

        self._observer = Observer()
        self._observer.schedule(self, str(self.watch_dir), recursive=True)
        self._observer.daemon = True
        self._observer.start()
        self._running = True
        logger.info(f"[PluginWatcher] Watching: {self.watch_dir}")
        return True

    def stop(self):
        """Stop watching."""
        self._running = False
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
        # Cancel pending timers
        with self._lock:
            for timer in self._debounce_timers.values():
                timer.cancel()
            self._debounce_timers.clear()
        logger.info("[PluginWatcher] Stopped")

    def on_modified(self, event):
        """Called when a file is modified."""
        if not event.is_directory and event.src_path.endswith('.py'):
            self._debounced_reload(event.src_path, 'modified')

    def on_created(self, event):
        """Called when a file or directory is created."""
        if event.is_directory:
            # New plugin directory - trigger discovery
            self._debounced_reload(event.src_path, 'created_dir')
        elif event.src_path.endswith(('.py', '.json', '.yaml', '.yml')):
            self._debounced_reload(event.src_path, 'created')

    def on_deleted(self, event):
        """Called when a file or directory is deleted."""
        if event.is_directory:
            self._debounced_reload(event.src_path, 'deleted_dir')
        elif event.src_path.endswith('.py'):
            self._debounced_reload(event.src_path, 'deleted')

    def _debounced_reload(self, path: str, change_type: str):
        """Debounce file change events to avoid rapid-fire reloads."""
        with self._lock:
            # Cancel existing timer for this path
            if path in self._debounce_timers:
                self._debounce_timers[path].cancel()

            # Set new timer
            timer = threading.Timer(
                self.DEBOUNCE_SECONDS,
                self._do_reload,
                args=(path, change_type),
            )
            timer.daemon = True
            self._debounce_timers[path] = timer
            timer.start()

    def _do_reload(self, path: str, change_type: str):
        """Execute the actual plugin reload."""
        if not self.plugin_registry:
            return

        try:
            plugin_name = self._path_to_plugin_name(path)
            if not plugin_name:
                return

            if change_type == 'deleted_dir':
                # Plugin directory was deleted
                logger.info(f"[PluginWatcher] Plugin removed: {plugin_name}")
                self.plugin_registry.unload_plugin(plugin_name)

            elif change_type == 'created_dir':
                # New plugin directory - re-discover
                logger.info(f"[PluginWatcher] New plugin detected, re-discovering...")
                self.plugin_registry.discover_plugins()
                self.plugin_registry.load_plugin(plugin_name)
                self.plugin_registry.activate_plugin(plugin_name)

            elif change_type in ('modified', 'created'):
                # File changed - reload the plugin
                logger.info(f"[PluginWatcher] Reloading plugin: {plugin_name}")
                self.plugin_registry.unload_plugin(plugin_name)
                self.plugin_registry.discover_plugins()
                self.plugin_registry.load_plugin(plugin_name)
                self.plugin_registry.activate_plugin(plugin_name)
                logger.info(f"[PluginWatcher] Hot-reloaded: {plugin_name}")

            elif change_type == 'deleted':
                # A file was deleted but directory still exists - reload
                logger.info(f"[PluginWatcher] File deleted in {plugin_name}, reloading...")
                self.plugin_registry.unload_plugin(plugin_name)
                self.plugin_registry.discover_plugins()

        except Exception as e:
            logger.error(f"[PluginWatcher] Reload failed for {path}: {e}")

        # Cleanup timer reference
        with self._lock:
            self._debounce_timers.pop(path, None)

    def _path_to_plugin_name(self, path: str) -> Optional[str]:
        """Extract plugin name from a file path within the plugins directory."""
        try:
            rel = Path(path).relative_to(self.watch_dir)
            # First directory component is the plugin name
            parts = rel.parts
            if parts:
                return parts[0]
        except (ValueError, IndexError):
            pass
        return None

    @property
    def is_running(self) -> bool:
        return self._running


# Global watcher instance
_plugin_watcher: Optional[PluginWatcher] = None


def get_plugin_watcher(plugin_registry=None) -> PluginWatcher:
    """Get or create global plugin watcher instance."""
    global _plugin_watcher
    if _plugin_watcher is None:
        _plugin_watcher = PluginWatcher(plugin_registry=plugin_registry)
    return _plugin_watcher


# =====================================================
# TEST
# =====================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("LADA v9.0 - Lazy Loader Test")
    print("=" * 60)
    
    loader = LazyModuleLoader()
    
    # Register some test modules
    def create_test_module():
        time.sleep(0.5)  # Simulate slow import
        return {"name": "test_module", "loaded": True}
    
    loader.register("test1", create_test_module)
    loader.register("test2", create_test_module)
    loader.register("test3", create_test_module)
    
    print("\n📋 Registered modules:", list(loader._factories.keys()))
    print("📋 Loaded modules:", list(loader._modules.keys()))
    
    # Load one module
    print("\n🔄 Loading test1...")
    result = loader.get("test1")
    print(f"   Result: {result}")
    
    # Check stats
    print("\n📊 Stats:")
    stats = loader.get_stats()
    print(f"   Loaded: {stats['loaded']}")
    print(f"   Pending: {stats['pending']}")
    print(f"   Load times: {stats['load_times']}")
    
    # Preload async
    print("\n🚀 Preloading test2, test3 async...")
    loader.preload_async("test2", "test3")
    time.sleep(1.5)  # Wait for preload
    
    print("\n📊 Final Stats:")
    stats = loader.get_stats()
    print(f"   Loaded: {stats['loaded']}")
    print(f"   Total time: {stats['total_load_time']:.2f}s")
    
    print("\n✅ Lazy Loader test complete!")
