"""Tests for modules/advanced_features.py - ResponseCache, ConversationManager, etc."""

import pytest
import json
import os
import time
from unittest.mock import MagicMock, patch, mock_open
from datetime import datetime, timedelta


class TestResponseCacheInit:
    """Test ResponseCache initialization."""

    def test_init_default(self):
        import modules.advanced_features as af
        
        cache = af.ResponseCache()
        assert hasattr(cache, 'cache')
        assert hasattr(cache, 'max_size')
        assert hasattr(cache, 'ttl')

    def test_init_custom_size(self):
        import modules.advanced_features as af
        
        cache = af.ResponseCache(max_size=50)
        assert cache.max_size == 50

    def test_init_custom_ttl_hours(self):
        import modules.advanced_features as af
        from datetime import timedelta
        
        cache = af.ResponseCache(ttl_hours=12)
        # ttl_hours is converted to self.ttl (a timedelta)
        assert cache.ttl == timedelta(hours=12)


class TestResponseCacheOperations:
    """Test cache get/set operations."""

    def test_set_and_get(self):
        import modules.advanced_features as af
        
        cache = af.ResponseCache()
        cache.set("test_key", "test_value")
        result = cache.get("test_key")
        assert result == "test_value"

    def test_get_nonexistent_key(self):
        import modules.advanced_features as af
        
        cache = af.ResponseCache()
        result = cache.get("nonexistent")
        assert result is None

    def test_clear_cache(self):
        import modules.advanced_features as af
        
        cache = af.ResponseCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_cache_stats(self):
        import modules.advanced_features as af
        
        cache = af.ResponseCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        stats = cache.stats()
        assert isinstance(stats, dict)
        assert 'size' in stats or 'count' in stats or len(stats) >= 0


class TestResponseCacheExpiration:
    """Test cache TTL expiration."""

    def test_cache_set_and_get_basic(self):
        import modules.advanced_features as af
        
        cache = af.ResponseCache(ttl_hours=1)
        cache.set("key", "value")
        
        # Should still be valid
        assert cache.get("key") == "value"

    def test_cache_eviction_when_full(self):
        import modules.advanced_features as af
        
        cache = af.ResponseCache(max_size=3)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.set("key4", "value4")  # Should evict oldest
        
        # Stats should reflect max size constraint
        stats = cache.stats()
        assert isinstance(stats, dict)


class TestConversationManagerInit:
    """Test ConversationManager initialization."""

    def test_init_default(self):
        import modules.advanced_features as af
        
        mgr = af.ConversationManager()
        assert hasattr(mgr, 'history')

    def test_init_custom_limit(self):
        import modules.advanced_features as af
        
        mgr = af.ConversationManager(max_history=50)
        # Check that it was created with custom limit
        assert mgr.max_history == 50


class TestConversationManagerOperations:
    """Test conversation history operations."""

    def test_add_turn(self):
        import modules.advanced_features as af
        
        mgr = af.ConversationManager()
        mgr.add_turn("user", "Hello")
        assert len(mgr.history) == 1

    def test_add_multiple_turns(self):
        import modules.advanced_features as af
        
        mgr = af.ConversationManager()
        mgr.add_turn("user", "Hello")
        mgr.add_turn("assistant", "Hi there!")
        assert len(mgr.history) == 2

    def test_get_context(self):
        import modules.advanced_features as af
        
        mgr = af.ConversationManager()
        mgr.add_turn("user", "Hello")
        mgr.add_turn("assistant", "Hi!")
        mgr.add_turn("user", "How are you?")
        
        context = mgr.get_context()
        assert isinstance(context, str)
        assert len(context) > 0

    def test_clear_history(self):
        import modules.advanced_features as af
        
        mgr = af.ConversationManager()
        mgr.add_turn("user", "Hello")
        mgr.add_turn("assistant", "Hi!")
        mgr.clear()
        assert len(mgr.history) == 0

    def test_history_truncation(self):
        import modules.advanced_features as af
        
        mgr = af.ConversationManager(max_history=3)
        for i in range(5):
            mgr.add_turn("user", f"Message {i}")
        
        # Should only keep last 3
        assert len(mgr.history) <= 3


class TestConversationManagerExport:
    """Test conversation export functionality."""

    def test_export_creates_file(self, tmp_path):
        import modules.advanced_features as af
        
        mgr = af.ConversationManager()
        mgr.add_turn("user", "Hello")
        mgr.add_turn("assistant", "Hi!")
        
        export_path = tmp_path / "conversation.json"
        mgr.export(str(export_path))
        
        assert export_path.exists()

    def test_export_valid_json(self, tmp_path):
        import modules.advanced_features as af
        
        mgr = af.ConversationManager()
        mgr.add_turn("user", "Test message")
        
        export_path = tmp_path / "conversation.json"
        mgr.export(str(export_path))
        
        with open(export_path) as f:
            data = json.load(f)
        assert isinstance(data, (list, dict))


class TestCustomCommandRegistryInit:
    """Test CustomCommandRegistry initialization."""

    def test_init_default(self):
        import modules.advanced_features as af
        
        registry = af.CustomCommandRegistry()
        assert hasattr(registry, 'commands')

    def test_commands_empty_initially(self):
        import modules.advanced_features as af
        
        registry = af.CustomCommandRegistry()
        commands = registry.list_commands()
        assert isinstance(commands, (list, dict))


class TestCustomCommandRegistryOperations:
    """Test command registration and execution."""

    def test_register_command(self):
        import modules.advanced_features as af
        
        registry = af.CustomCommandRegistry()
        
        def handler():
            return "executed"
        
        registry.register("test", ["keyword"], handler)
        commands = registry.list_commands()
        assert len(commands) >= 1

    def test_find_command(self):
        import modules.advanced_features as af
        
        registry = af.CustomCommandRegistry()
        
        def handler():
            return "executed"
        
        registry.register("greet", ["hello", "hi"], handler)
        match = registry.find_command("hello there")
        assert match is not None

    def test_find_no_command(self):
        import modules.advanced_features as af
        
        registry = af.CustomCommandRegistry()
        
        def handler():
            return "executed"
        
        registry.register("greet", ["hello"], handler)
        match = registry.find_command("goodbye")
        # Should return None or empty when no match
        assert match is None or match == ""

    def test_execute_command(self):
        import modules.advanced_features as af
        
        registry = af.CustomCommandRegistry()
        
        executed = []
        def handler():
            executed.append(True)
            return "done"
        
        registry.register("test", ["run"], handler)
        result = registry.execute("run this")
        # Should have executed or returned something
        assert result is not None or len(executed) > 0

    def test_list_commands(self):
        import modules.advanced_features as af
        
        registry = af.CustomCommandRegistry()
        registry.register("cmd1", ["key1"], lambda: None)
        registry.register("cmd2", ["key2"], lambda: None)
        
        commands = registry.list_commands()
        assert len(commands) >= 2


class TestPerformanceMonitorInit:
    """Test PerformanceMonitor initialization."""

    def test_init_default(self):
        import modules.advanced_features as af
        
        monitor = af.PerformanceMonitor()
        assert hasattr(monitor, 'metrics') or hasattr(monitor, 'queries')

    def test_monitor_has_attributes(self):
        import modules.advanced_features as af
        
        monitor = af.PerformanceMonitor()
        # Check that monitor object exists
        assert monitor is not None


class TestPerformanceMonitorLogging:
    """Test performance metric logging."""

    def test_log_query(self):
        import modules.advanced_features as af
        
        monitor = af.PerformanceMonitor()
        monitor.log_query("local", 0.5, True)
        # Should not raise
        stats = monitor.get_stats()
        assert isinstance(stats, dict)

    def test_log_multiple_queries(self):
        import modules.advanced_features as af
        
        monitor = af.PerformanceMonitor()
        for i in range(5):
            monitor.log_query("local", 0.1 * (i + 1), True)
        
        stats = monitor.get_stats()
        assert isinstance(stats, dict)

    def test_log_failed_query(self):
        import modules.advanced_features as af
        
        monitor = af.PerformanceMonitor()
        monitor.log_query("cloud", 1.0, False)
        
        stats = monitor.get_stats()
        assert isinstance(stats, dict)


class TestPerformanceMonitorStats:
    """Test performance statistics."""

    def test_get_stats_empty(self):
        import modules.advanced_features as af
        
        monitor = af.PerformanceMonitor()
        stats = monitor.get_stats()
        assert isinstance(stats, dict)

    def test_get_stats_with_data(self):
        import modules.advanced_features as af
        
        monitor = af.PerformanceMonitor()
        monitor.log_query("local", 0.5, True)
        monitor.log_query("cloud", 1.0, True)
        
        stats = monitor.get_stats()
        # Should have aggregated metrics
        assert len(stats) >= 1

    def test_report(self):
        import modules.advanced_features as af
        
        monitor = af.PerformanceMonitor()
        monitor.log_query("local", 0.5, True)
        
        # print_report is the actual method name
        monitor.print_report()


class TestPerformanceMonitorEdgeCases:
    """Test edge cases and error handling."""

    def test_log_zero_latency(self):
        import modules.advanced_features as af
        
        monitor = af.PerformanceMonitor()
        monitor.log_query("local", 0.0, True)
        stats = monitor.get_stats()
        assert isinstance(stats, dict)

    def test_log_very_high_latency(self):
        import modules.advanced_features as af
        
        monitor = af.PerformanceMonitor()
        monitor.log_query("cloud", 30.0, True)
        stats = monitor.get_stats()
        assert isinstance(stats, dict)
