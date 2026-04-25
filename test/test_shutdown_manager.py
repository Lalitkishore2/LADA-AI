"""
Unit Tests for Shutdown Manager Module

Tests thread registration, graceful shutdown, cleanup callbacks, and signal handling.
"""

import pytest
import threading
import time
from unittest.mock import Mock, patch

from modules.shutdown_manager import (
    ShutdownManager,
    get_shutdown_manager,
    start_managed_thread,
    register_cleanup
)


class TestShutdownManager:
    """Test suite for ShutdownManager class"""
    
    def test_initialization(self):
        """Test shutdown manager initialization"""
        manager = ShutdownManager(shutdown_timeout=5.0)
        
        assert manager.shutdown_timeout == 5.0
        assert manager._shutdown_requested is False
        assert manager._shutdown_complete is False
        assert len(manager._threads) == 0
        assert len(manager._cleanup_callbacks) == 0
    
    def test_register_thread(self):
        """Test registering a thread"""
        manager = ShutdownManager()
        
        def worker():
            time.sleep(1)
        
        thread = threading.Thread(target=worker, daemon=True)
        manager.register_thread(thread, name="worker_thread")
        
        assert "worker_thread" in manager._threads
        assert manager._threads["worker_thread"].thread is thread
    
    def test_register_thread_with_stop_event(self):
        """Test registering thread with stop event"""
        manager = ShutdownManager()
        stop_event = threading.Event()
        
        def worker(stop_evt):
            while not stop_evt.is_set():
                time.sleep(0.1)
        
        thread = threading.Thread(target=worker, args=(stop_event,), daemon=True)
        manager.register_thread(thread, name="stoppable_worker", stop_event=stop_event)
        
        managed = manager._threads["stoppable_worker"]
        assert managed.stop_event is stop_event
    
    def test_register_cleanup(self):
        """Test registering cleanup callback"""
        manager = ShutdownManager()
        callback = Mock()
        
        manager.register_cleanup(callback, description="test cleanup")
        
        assert len(manager._cleanup_callbacks) == 1
        assert callback in manager._cleanup_callbacks
    
    def test_unregister_thread(self):
        """Test unregistering a thread"""
        manager = ShutdownManager()
        
        thread = threading.Thread(target=lambda: None, daemon=True)
        manager.register_thread(thread, name="temp_thread")
        
        assert "temp_thread" in manager._threads
        
        manager.unregister_thread("temp_thread")
        
        assert "temp_thread" not in manager._threads
    
    def test_is_shutdown_requested(self):
        """Test checking shutdown status"""
        manager = ShutdownManager()
        
        assert manager.is_shutdown_requested() is False
        
        manager._shutdown_requested = True
        
        assert manager.is_shutdown_requested() is True
    
    def test_shutdown_sets_flag(self):
        """Test that shutdown sets the shutdown flag"""
        manager = ShutdownManager()
        
        manager.shutdown()
        
        assert manager._shutdown_requested is True
        assert manager._shutdown_complete is True
    
    def test_shutdown_signals_stop_events(self):
        """Test that shutdown signals stop events"""
        manager = ShutdownManager()
        stop_event = threading.Event()
        
        def worker(stop_evt):
            while not stop_evt.is_set():
                time.sleep(0.1)
        
        thread = threading.Thread(target=worker, args=(stop_event,), daemon=True)
        manager.register_thread(thread, name="worker", stop_event=stop_event)
        thread.start()
        
        # Shutdown should set the stop event
        manager.shutdown()
        
        assert stop_event.is_set()
        assert not thread.is_alive()
    
    def test_shutdown_calls_cleanup_callbacks(self):
        """Test that shutdown calls cleanup callbacks"""
        manager = ShutdownManager()
        callback1 = Mock()
        callback2 = Mock()
        
        manager.register_cleanup(callback1)
        manager.register_cleanup(callback2)
        
        manager.shutdown()
        
        callback1.assert_called_once()
        callback2.assert_called_once()
    
    def test_shutdown_waits_for_threads(self):
        """Test that shutdown waits for threads to complete"""
        manager = ShutdownManager(shutdown_timeout=2.0)
        
        def quick_worker():
            time.sleep(0.5)
        
        thread = threading.Thread(target=quick_worker, daemon=True)
        manager.register_thread(thread, name="quick_worker")
        thread.start()
        
        start_time = time.time()
        manager.shutdown()
        elapsed = time.time() - start_time
        
        # Should wait for thread (0.5s) but not timeout (2.0s)
        assert 0.4 < elapsed < 1.5
        assert not thread.is_alive()
    
    def test_shutdown_timeout_enforcement(self):
        """Test that shutdown enforces timeout"""
        manager = ShutdownManager(shutdown_timeout=1.0)
        
        def slow_worker():
            time.sleep(5.0)  # Will not finish in time
        
        thread = threading.Thread(target=slow_worker, daemon=True)
        manager.register_thread(thread, name="slow_worker")
        thread.start()
        
        start_time = time.time()
        manager.shutdown()
        elapsed = time.time() - start_time
        
        # Should timeout after ~1 second
        assert 0.9 < elapsed < 1.5
        # Thread may still be alive (daemon)
    
    def test_shutdown_runs_thread_cleanup(self):
        """Test that shutdown runs thread-specific cleanup"""
        manager = ShutdownManager()
        cleanup_func = Mock()
        
        thread = threading.Thread(target=lambda: None, daemon=True)
        manager.register_thread(thread, name="worker", cleanup_func=cleanup_func)
        thread.start()
        thread.join()  # Let it finish
        
        manager.shutdown()
        
        cleanup_func.assert_called_once()
    
    def test_shutdown_handles_cleanup_errors(self):
        """Test that shutdown continues even if cleanup fails"""
        manager = ShutdownManager()
        
        failing_callback = Mock(side_effect=Exception("cleanup failed"))
        success_callback = Mock()
        
        manager.register_cleanup(failing_callback)
        manager.register_cleanup(success_callback)
        
        # Should not raise, should continue
        manager.shutdown()
        
        failing_callback.assert_called_once()
        success_callback.assert_called_once()
    
    def test_get_status(self):
        """Test getting shutdown manager status"""
        manager = ShutdownManager()
        
        def worker():
            time.sleep(10)
        
        thread = threading.Thread(target=worker, daemon=True)
        manager.register_thread(thread, name="worker")
        thread.start()
        
        status = manager.get_status()
        
        assert status["shutdown_requested"] is False
        assert status["registered_threads"] == 1
        assert status["alive_threads"] == 1
        assert len(status["threads"]) == 1
        assert status["threads"][0]["name"] == "worker"
        assert status["threads"][0]["alive"] is True


class TestShutdownManagerSingleton:
    """Test singleton behavior of get_shutdown_manager()"""
    
    def test_singleton_returns_same_instance(self):
        """Test that get_shutdown_manager() returns same instance"""
        manager1 = get_shutdown_manager()
        manager2 = get_shutdown_manager()
        
        assert manager1 is manager2
    
    def test_singleton_thread_safety(self):
        """Test that singleton creation is thread-safe"""
        instances = []
        
        def get_instance():
            manager = get_shutdown_manager()
            instances.append(id(manager))
        
        threads = [threading.Thread(target=get_instance) for _ in range(10)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All instances should have same ID
        assert len(set(instances)) == 1


class TestStartManagedThread:
    """Test start_managed_thread convenience function"""
    
    def test_start_managed_thread_registers_and_starts(self):
        """Test that start_managed_thread registers and starts thread"""
        manager = get_shutdown_manager()
        executed = []
        
        def worker():
            executed.append(True)
        
        thread = start_managed_thread(target=worker, name="test_worker")
        
        # Wait for thread
        thread.join(timeout=1.0)
        
        assert len(executed) == 1
        assert thread.is_alive() is False
    
    def test_start_managed_thread_with_args(self):
        """Test start_managed_thread with arguments"""
        result = []
        
        def worker(a, b, c=None):
            result.append((a, b, c))
        
        thread = start_managed_thread(
            target=worker,
            name="args_worker",
            args=(1, 2),
            kwargs={"c": 3}
        )
        
        thread.join(timeout=1.0)
        
        assert result == [(1, 2, 3)]


class TestRegisterCleanup:
    """Test register_cleanup convenience function"""
    
    def test_register_cleanup_adds_callback(self):
        """Test that register_cleanup adds callback"""
        manager = get_shutdown_manager()
        callback = Mock()
        
        register_cleanup(callback, description="test cleanup")
        
        # Callback should be registered
        assert callback in manager._cleanup_callbacks


class TestSignalHandling:
    """Test signal handler integration"""
    
    @patch('signal.signal')
    def test_signal_handlers_registered(self, mock_signal):
        """Test that signal handlers are registered on init"""
        import signal
        
        manager = ShutdownManager()
        
        # Should register SIGINT and SIGTERM
        calls = mock_signal.call_args_list
        signals_registered = [call[0][0] for call in calls]
        
        assert signal.SIGINT in signals_registered
        assert signal.SIGTERM in signals_registered


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
