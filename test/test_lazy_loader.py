"""Tests for modules/lazy_loader.py"""
import threading
import time
from unittest.mock import MagicMock

import pytest


class TestLazyModuleLoader:
    """Tests for LazyModuleLoader class"""

    def test_init(self):
        from modules.lazy_loader import LazyModuleLoader

        loader = LazyModuleLoader()
        assert loader._modules == {}
        assert loader._factories == {}
        assert loader._locks == {}

    def test_register(self):
        from modules.lazy_loader import LazyModuleLoader

        loader = LazyModuleLoader()

        def factory():
            return "test_module"

        loader.register("test", factory)
        assert "test" in loader._factories
        assert "test" in loader._locks

    def test_get_loads_module(self):
        from modules.lazy_loader import LazyModuleLoader

        loader = LazyModuleLoader()
        loader.register("test", lambda: {"loaded": True})

        result = loader.get("test")
        assert result == {"loaded": True}
        assert "test" in loader._modules

    def test_get_cached_module(self):
        from modules.lazy_loader import LazyModuleLoader

        loader = LazyModuleLoader()
        call_count = [0]

        def factory():
            call_count[0] += 1
            return "module"

        loader.register("test", factory)

        # First call loads
        loader.get("test")
        # Second call should use cache
        loader.get("test")

        assert call_count[0] == 1

    def test_get_unregistered_module(self):
        from modules.lazy_loader import LazyModuleLoader

        loader = LazyModuleLoader()
        result = loader.get("nonexistent")
        assert result is None

    def test_get_or_none_loaded(self):
        from modules.lazy_loader import LazyModuleLoader

        loader = LazyModuleLoader()
        loader._modules["test"] = "loaded_module"

        result = loader.get_or_none("test")
        assert result == "loaded_module"

    def test_get_or_none_not_loaded(self):
        from modules.lazy_loader import LazyModuleLoader

        loader = LazyModuleLoader()
        result = loader.get_or_none("test")
        assert result is None

    def test_is_loaded(self):
        from modules.lazy_loader import LazyModuleLoader

        loader = LazyModuleLoader()
        loader._modules["loaded"] = "module"

        assert loader.is_loaded("loaded") is True
        assert loader.is_loaded("not_loaded") is False

    def test_get_handles_factory_error(self):
        from modules.lazy_loader import LazyModuleLoader

        loader = LazyModuleLoader()

        def failing_factory():
            raise RuntimeError("Factory failed")

        loader.register("failing", failing_factory)
        result = loader.get("failing")

        assert result is None
        assert "failing" in loader._errors

    def test_preload_async(self):
        from modules.lazy_loader import LazyModuleLoader

        loader = LazyModuleLoader()
        loader.register("mod1", lambda: "module1")
        loader.register("mod2", lambda: "module2")

        loader.preload_async("mod1", "mod2")

        # Give threads time to complete
        time.sleep(0.2)

        assert loader.is_loaded("mod1")
        assert loader.is_loaded("mod2")

    def test_thread_safety(self):
        from modules.lazy_loader import LazyModuleLoader

        loader = LazyModuleLoader()
        call_count = [0]

        def slow_factory():
            call_count[0] += 1
            time.sleep(0.05)
            return "module"

        loader.register("test", slow_factory)

        threads = [threading.Thread(target=lambda: loader.get("test")) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Factory should only be called once due to locking
        assert call_count[0] == 1
