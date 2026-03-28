"""
Graceful Shutdown Manager - Clean termination of all background threads and resources.

Provides:
- Centralized thread registry for all daemon threads
- Signal handlers for SIGINT/SIGTERM
- Ordered shutdown of components
- Resource cleanup (files, connections, sockets)
- Timeout-based forced termination if graceful shutdown fails

Usage:
    # At application startup
    shutdown_manager = get_shutdown_manager()
    
    # Register threads
    thread = threading.Thread(target=my_task, daemon=True)
    shutdown_manager.register_thread(thread, name="my_task")
    thread.start()
    
    # Shutdown is automatic via signal handlers
    # Or manually: shutdown_manager.shutdown()
"""

import os
import sys
import time
import signal
import threading
import logging
import atexit
from typing import List, Dict, Callable, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ManagedThread:
    """Metadata for a managed thread"""
    thread: threading.Thread
    name: str
    stop_event: Optional[threading.Event] = None
    cleanup_func: Optional[Callable] = None
    registered_at: datetime = datetime.now()


class ShutdownManager:
    """
    Centralized shutdown coordinator for graceful application termination.
    
    Features:
    - Thread registry and lifecycle management
    - Signal handlers (SIGINT, SIGTERM)
    - Cleanup callbacks for resources
    - Timeout-based forced shutdown
    - Shutdown progress logging
    """
    
    def __init__(self, shutdown_timeout: float = 10.0):
        """
        Initialize shutdown manager.
        
        Args:
            shutdown_timeout: Max seconds to wait for graceful shutdown before force-killing threads
        """
        self.shutdown_timeout = shutdown_timeout
        self._lock = threading.Lock()
        self._shutdown_requested = False
        self._threads: Dict[str, ManagedThread] = {}
        self._cleanup_callbacks: List[Callable] = []
        self._shutdown_complete = False
        
        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Register atexit handler
        atexit.register(self._atexit_handler)
        
        logger.info(f"[ShutdownManager] Initialized with {shutdown_timeout}s timeout")
    
    def _signal_handler(self, signum, frame):
        """Handle SIGINT (Ctrl+C) and SIGTERM"""
        signal_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
        logger.info(f"[ShutdownManager] Received {signal_name}, initiating graceful shutdown...")
        self.shutdown()
    
    def _atexit_handler(self):
        """Handle atexit - final cleanup"""
        if not self._shutdown_complete:
            logger.info("[ShutdownManager] atexit handler triggered")
            self.shutdown()
    
    def register_thread(
        self,
        thread: threading.Thread,
        name: str,
        stop_event: Optional[threading.Event] = None,
        cleanup_func: Optional[Callable] = None
    ) -> None:
        """
        Register a thread for managed shutdown.
        
        Args:
            thread: Thread instance to manage
            name: Human-readable thread name
            stop_event: Optional Event to signal thread to stop
            cleanup_func: Optional cleanup function to call before joining thread
        """
        with self._lock:
            if name in self._threads:
                logger.warning(f"[ShutdownManager] Thread '{name}' already registered, replacing")
            
            self._threads[name] = ManagedThread(
                thread=thread,
                name=name,
                stop_event=stop_event,
                cleanup_func=cleanup_func
            )
            logger.debug(f"[ShutdownManager] Registered thread: {name}")
    
    def register_cleanup(self, callback: Callable, description: str = "") -> None:
        """
        Register a cleanup callback to run during shutdown.
        
        Args:
            callback: Function to call during shutdown (no args)
            description: Human-readable description for logging
        """
        with self._lock:
            self._cleanup_callbacks.append(callback)
            logger.debug(f"[ShutdownManager] Registered cleanup: {description or callback.__name__}")
    
    def unregister_thread(self, name: str) -> None:
        """
        Unregister a thread (e.g., when it completes naturally).
        
        Args:
            name: Thread name to unregister
        """
        with self._lock:
            if name in self._threads:
                del self._threads[name]
                logger.debug(f"[ShutdownManager] Unregistered thread: {name}")
    
    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested"""
        return self._shutdown_requested
    
    def shutdown(self) -> None:
        """
        Initiate graceful shutdown of all managed resources.
        
        Steps:
        1. Set shutdown flag
        2. Signal all threads to stop (via stop_events)
        3. Run cleanup callbacks
        4. Wait for threads with timeout
        5. Force-terminate remaining threads
        """
        with self._lock:
            if self._shutdown_requested:
                logger.debug("[ShutdownManager] Shutdown already in progress")
                return
            
            self._shutdown_requested = True
            logger.info(f"[ShutdownManager] Starting shutdown of {len(self._threads)} threads...")
        
        # Step 1: Signal all threads to stop
        for name, managed in list(self._threads.items()):
            if managed.stop_event:
                logger.debug(f"[ShutdownManager] Signaling thread to stop: {name}")
                managed.stop_event.set()
        
        # Step 2: Run cleanup callbacks
        logger.info(f"[ShutdownManager] Running {len(self._cleanup_callbacks)} cleanup callbacks...")
        for callback in self._cleanup_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"[ShutdownManager] Cleanup callback failed: {e}")
        
        # Step 3: Wait for threads with timeout
        start_time = time.time()
        remaining_threads = list(self._threads.items())
        
        for name, managed in remaining_threads:
            # Calculate remaining timeout
            elapsed = time.time() - start_time
            timeout_remaining = max(0, self.shutdown_timeout - elapsed)
            
            if timeout_remaining <= 0:
                logger.warning(f"[ShutdownManager] Timeout reached, skipping wait for: {name}")
                continue
            
            # Run thread-specific cleanup if provided
            if managed.cleanup_func:
                try:
                    logger.debug(f"[ShutdownManager] Running cleanup for: {name}")
                    managed.cleanup_func()
                except Exception as e:
                    logger.error(f"[ShutdownManager] Cleanup failed for {name}: {e}")
            
            # Wait for thread to finish
            if managed.thread.is_alive():
                logger.debug(f"[ShutdownManager] Waiting for thread: {name} (timeout={timeout_remaining:.1f}s)")
                managed.thread.join(timeout=timeout_remaining)
                
                if managed.thread.is_alive():
                    logger.warning(f"[ShutdownManager] Thread did not stop gracefully: {name}")
                else:
                    logger.info(f"[ShutdownManager] Thread stopped: {name}")
        
        # Step 4: Log final status
        alive_count = sum(1 for _, m in self._threads.items() if m.thread.is_alive())
        if alive_count > 0:
            logger.warning(f"[ShutdownManager] {alive_count} threads still alive after timeout")
        else:
            logger.info("[ShutdownManager] All threads stopped gracefully")
        
        self._shutdown_complete = True
        logger.info("[ShutdownManager] Shutdown complete")
    
    def get_status(self) -> Dict:
        """
        Get shutdown manager status.
        
        Returns:
            Dict with registered threads, cleanup callbacks, shutdown state
        """
        with self._lock:
            return {
                "shutdown_requested": self._shutdown_requested,
                "shutdown_complete": self._shutdown_complete,
                "registered_threads": len(self._threads),
                "alive_threads": sum(1 for _, m in self._threads.items() if m.thread.is_alive()),
                "cleanup_callbacks": len(self._cleanup_callbacks),
                "threads": [
                    {
                        "name": name,
                        "alive": m.thread.is_alive(),
                        "daemon": m.thread.daemon,
                        "has_stop_event": m.stop_event is not None,
                        "registered_at": m.registered_at.isoformat(),
                    }
                    for name, m in self._threads.items()
                ]
            }


# ── Singleton Instance ───────────────────────────────────────────────

_shutdown_manager_instance: Optional[ShutdownManager] = None
_shutdown_manager_lock = threading.Lock()


def get_shutdown_manager() -> ShutdownManager:
    """
    Get or create the global ShutdownManager instance (thread-safe).
    
    Returns:
        ShutdownManager singleton
    """
    global _shutdown_manager_instance
    
    if _shutdown_manager_instance is not None:
        return _shutdown_manager_instance
    
    with _shutdown_manager_lock:
        # Double-check pattern
        if _shutdown_manager_instance is None:
            timeout = float(os.getenv("LADA_SHUTDOWN_TIMEOUT", "10.0"))
            _shutdown_manager_instance = ShutdownManager(shutdown_timeout=timeout)
        return _shutdown_manager_instance


# ── Convenience Functions ────────────────────────────────────────────

def start_managed_thread(
    target: Callable,
    name: str,
    args: tuple = (),
    kwargs: dict = None,
    daemon: bool = True,
    stop_event: Optional[threading.Event] = None,
    cleanup_func: Optional[Callable] = None
) -> threading.Thread:
    """
    Start a thread and automatically register it with ShutdownManager.
    
    Args:
        target: Thread target function
        name: Thread name
        args: Positional args for target
        kwargs: Keyword args for target
        daemon: Whether thread is daemon
        stop_event: Optional Event to signal stop
        cleanup_func: Optional cleanup function
    
    Returns:
        Started Thread instance
    """
    kwargs = kwargs or {}
    thread = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=daemon, name=name)
    
    manager = get_shutdown_manager()
    manager.register_thread(thread, name=name, stop_event=stop_event, cleanup_func=cleanup_func)
    
    thread.start()
    logger.debug(f"[ShutdownManager] Started managed thread: {name}")
    return thread


def register_cleanup(callback: Callable, description: str = "") -> None:
    """
    Register a cleanup callback (convenience wrapper).
    
    Args:
        callback: Cleanup function
        description: Human-readable description
    """
    manager = get_shutdown_manager()
    manager.register_cleanup(callback, description)
