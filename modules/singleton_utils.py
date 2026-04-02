"""
Thread-Safe Singleton Utilities - Automatic lock management for global singletons.

This module provides decorators and utilities to make singleton getters thread-safe
without manual lock management in every file.

Usage:
    @thread_safe_singleton
    def get_my_service():
        global _instance
        if _instance is None:
            _instance = MyService()
        return _instance

The decorator automatically adds thread-safe double-check locking.
"""

import threading
import functools
import logging
from typing import Callable, Any, Dict

logger = logging.getLogger(__name__)

# Global registry of singleton locks (one lock per function)
_singleton_locks: Dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


def thread_safe_singleton(func: Callable) -> Callable:
    """
    Decorator to make a singleton getter function thread-safe.
    
    Implements double-check locking pattern automatically.
    
    Args:
        func: Singleton getter function (e.g., get_provider_manager)
    
    Returns:
        Thread-safe wrapper function
    
    Example:
        @thread_safe_singleton
        def get_database():
            global _db
            if _db is None:
                _db = Database()
            return _db
    """
    # Get or create a lock for this function
    func_id = f"{func.__module__}.{func.__name__}"
    
    with _registry_lock:
        if func_id not in _singleton_locks:
            _singleton_locks[func_id] = threading.Lock()
    
    lock = _singleton_locks[func_id]
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Always acquire lock before calling func to prevent race conditions
        # The "fast path" optimization was racy - multiple threads could call func() concurrently
        with lock:
            result = func(*args, **kwargs)
            if result is None:
                logger.warning(f"[ThreadSafeSingleton] {func_id} returned None even after lock acquisition")
            return result
    
    return wrapper


class SingletonMeta(type):
    """
    Thread-safe singleton metaclass.
    
    Usage:
        class MyService(metaclass=SingletonMeta):
            def __init__(self):
                self.value = 42
        
        s1 = MyService()
        s2 = MyService()
        assert s1 is s2  # Same instance
    """
    
    _instances: Dict[type, Any] = {}
    _lock = threading.Lock()
    
    def __call__(cls, *args, **kwargs):
        # Fast path: if already instantiated, return immediately
        if cls in cls._instances:
            return cls._instances[cls]
        
        # Slow path: acquire lock and double-check
        with cls._lock:
            if cls not in cls._instances:
                instance = super().__call__(*args, **kwargs)
                cls._instances[cls] = instance
            return cls._instances[cls]


def get_all_singleton_locks() -> Dict[str, threading.Lock]:
    """
    Get all registered singleton locks (for debugging/testing).
    
    Returns:
        Dict mapping function IDs to their locks
    """
    with _registry_lock:
        return dict(_singleton_locks)


def clear_singleton_registry() -> None:
    """
    Clear all singleton locks (for testing only).
    
    WARNING: This should only be used in test teardown.
    Calling this during normal operation will break thread safety.
    """
    with _registry_lock:
        _singleton_locks.clear()
    
    with SingletonMeta._lock:
        SingletonMeta._instances.clear()
    
    logger.warning("[ThreadSafeSingleton] Cleared all singleton locks and instances")
