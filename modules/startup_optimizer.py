"""
LADA v9.0 - Startup Optimizer
Optimizes LADA startup by using lazy loading and background preloading.
"""

import os
import sys
import time
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class StartupOptimizer:
    """
    Optimizes LADA startup time.
    
    Strategies:
    1. Lazy load non-essential modules
    2. Preload important modules in background
    3. Defer heavy imports until needed
    4. Cache module instances
    """
    
    def __init__(self, jarvis_core=None):
        self.jarvis_core = jarvis_core
        self.startup_time = time.time()
        self._initialization_complete = False
        self._background_thread: Optional[threading.Thread] = None
        self._preload_complete = threading.Event()
        
        # Track what's been loaded
        self._loaded_modules: Dict[str, float] = {}
        self._pending_modules: list = []
        
    def optimize_imports(self):
        """
        Defer heavy imports that aren't needed immediately.
        Call this before main imports.
        """
        # Set environment to reduce import overhead
        os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
        
        # Reduce TensorFlow logging (if used)
        os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')
        
        # Suppress warnings during startup
        import warnings
        warnings.filterwarnings('ignore', category=UserWarning)
        
        logger.debug("[StartupOptimizer] Optimized import environment")
    
    def start_background_preload(self):
        """Start preloading modules in background."""
        if self._background_thread and self._background_thread.is_alive():
            return
        
        self._background_thread = threading.Thread(
            target=self._background_preloader,
            daemon=True,
            name="StartupPreloader"
        )
        self._background_thread.start()
        logger.info("[StartupOptimizer] Background preload started")
    
    def _background_preloader(self):
        """Background thread to preload modules."""
        try:
            from modules.lazy_loader import get_lazy_loader, ModulePriority
            loader = get_lazy_loader()
            
            # Wait a bit for UI to be responsive first
            time.sleep(0.5)
            
            # Preload HIGH priority modules
            for module_name in ModulePriority.get_background_modules():
                if module_name in loader:
                    loader.get(module_name)
                    time.sleep(0.1)  # Small delay between loads
            
            self._preload_complete.set()
            elapsed = time.time() - self.startup_time
            logger.info(f"[StartupOptimizer] Background preload complete in {elapsed:.2f}s")
            
        except Exception as e:
            logger.error(f"[StartupOptimizer] Background preload error: {e}")
            self._preload_complete.set()
    
    def wait_for_preload(self, timeout: float = 10.0) -> bool:
        """Wait for background preload to complete."""
        return self._preload_complete.wait(timeout)
    
    def get_startup_time(self) -> float:
        """Get elapsed time since startup."""
        return time.time() - self.startup_time
    
    def report_startup(self):
        """Report startup statistics."""
        elapsed = self.get_startup_time()
        
        report = [
            "",
            "=" * 50,
            "LADA v9.0 - Startup Report",
            "=" * 50,
            f"Total startup time: {elapsed:.2f}s",
            f"Modules loaded: {len(self._loaded_modules)}",
        ]
        
        if self._loaded_modules:
            report.append("\nModule load times:")
            for name, load_time in sorted(
                self._loaded_modules.items(), 
                key=lambda x: x[1], 
                reverse=True
            ):
                report.append(f"  {name}: {load_time:.3f}s")
        
        report.append("=" * 50)
        
        logger.info("\n".join(report))
        return "\n".join(report)


class FastImporter:
    """
    Speed up specific imports by caching and optimizing.
    """
    
    _cache: Dict[str, Any] = {}
    _import_times: Dict[str, float] = {}
    
    @classmethod
    def import_module(cls, module_path: str, fallback=None):
        """
        Import a module with caching and error handling.
        """
        if module_path in cls._cache:
            return cls._cache[module_path]
        
        try:
            start = time.time()
            
            parts = module_path.rsplit('.', 1)
            if len(parts) == 2:
                module = __import__(parts[0], fromlist=[parts[1]])
                result = getattr(module, parts[1], None)
            else:
                result = __import__(module_path)
            
            cls._import_times[module_path] = time.time() - start
            cls._cache[module_path] = result
            
            return result
            
        except Exception as e:
            logger.warning(f"[FastImporter] Failed to import {module_path}: {e}")
            return fallback
    
    @classmethod
    def get_import_stats(cls) -> Dict[str, float]:
        """Get import timing statistics."""
        return cls._import_times.copy()


def create_optimized_core():
    """
    Factory function to create LADA core with optimized startup.
    """
    from modules.lazy_loader import LazyModuleLoader, ModulePriority
    
    loader = LazyModuleLoader()
    
    # Register all module factories
    module_factories = {
        'nlu_engine': lambda: __import__('modules.nlu_engine', fromlist=['NLUEngine']).NLUEngine(),
        'memory_system': lambda: __import__('lada_memory', fromlist=['MemorySystem']).MemorySystem(),
        'workflow_engine': lambda: __import__('modules.workflow_engine', fromlist=['WorkflowEngine']).WorkflowEngine(),
        'window_manager': lambda: __import__('modules.window_manager', fromlist=['WindowManager']).WindowManager(),
        'gui_automator': lambda: __import__('modules.gui_automator', fromlist=['GUIAutomator']).GUIAutomator(),
        'advanced_system_control': lambda: __import__('modules.advanced_system_control', fromlist=['AdvancedSystemController']).AdvancedSystemController(),
        'browser_tab_controller': lambda: __import__('modules.browser_tab_controller', fromlist=['BrowserTabController']).BrowserTabController(),
        'screen_vision': lambda: __import__('modules.screen_vision', fromlist=['ScreenVision']).ScreenVision(),
    }
    
    # Add optional modules with error handling
    optional_modules = {
        'gmail_controller': 'modules.gmail_controller.GmailController',
        'calendar_controller': 'modules.calendar_controller.CalendarController',
        'proactive_agent': 'modules.proactive_agent.ProactiveAgent',
        'pattern_learning': 'modules.pattern_learning.PatternLearning',
    }
    
    for name, path in optional_modules.items():
        parts = path.rsplit('.', 1)
        module_factories[name] = lambda p=parts: (
            getattr(__import__(p[0], fromlist=[p[1]]), p[1], lambda: None)()
        )
    
    # Register all factories
    for name, factory in module_factories.items():
        loader.register(name, factory)
    
    # Preload only critical modules synchronously
    loader.preload_sync(*ModulePriority.CRITICAL)
    
    # Start background preload for high priority
    loader.preload_async(*ModulePriority.HIGH)
    
    return loader


# Global startup optimizer
_optimizer: Optional[StartupOptimizer] = None

def get_startup_optimizer() -> StartupOptimizer:
    """Get or create global startup optimizer."""
    global _optimizer
    if _optimizer is None:
        _optimizer = StartupOptimizer()
    return _optimizer


# =====================================================
# TEST
# =====================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("LADA v9.0 - Startup Optimizer Test")
    print("=" * 60)
    
    optimizer = StartupOptimizer()
    optimizer.optimize_imports()
    
    print(f"\n⏱️  Time since startup: {optimizer.get_startup_time():.3f}s")
    
    # Test fast importer
    print("\n🔄 Testing FastImporter...")
    
    # Import some standard modules
    FastImporter.import_module('os')
    FastImporter.import_module('json')
    FastImporter.import_module('threading')
    
    print(f"📊 Import stats: {FastImporter.get_import_stats()}")
    
    print(f"\n⏱️  Total time: {optimizer.get_startup_time():.3f}s")
    print("\n✅ Startup Optimizer test complete!")
