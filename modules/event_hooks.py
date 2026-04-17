"""
LADA v11.0 - Event Hooks System
Extensible event-driven automation.
Hooks fire asynchronously on command/agent/message lifecycle boundaries
without modifying LADA core code.
"""

import os
import json
import logging
import threading
import importlib
import importlib.util
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Hook directories (in order of precedence)
WORKSPACE_HOOKS_DIR = Path("hooks")
MANAGED_HOOKS_DIR = Path.home() / ".lada" / "hooks"
BUNDLED_HOOKS_DIR = Path(__file__).parent / "bundled_hooks"
CONFIG_FILE = Path("config/hooks_config.json")


class EventType(Enum):
    """All event types that hooks can subscribe to."""
    # Command lifecycle
    COMMAND_NEW = "command:new"
    COMMAND_RESET = "command:reset"
    COMMAND_STOP = "command:stop"

    # Agent lifecycle
    AGENT_BOOTSTRAP = "agent:bootstrap"
    AGENT_START = "agent:start"
    AGENT_COMPLETE = "agent:complete"
    AGENT_ERROR = "agent:error"

    # Message events
    MESSAGE_RECEIVED = "message:received"
    MESSAGE_SENT = "message:sent"

    # Gateway/app lifecycle
    GATEWAY_STARTUP = "gateway:startup"
    GATEWAY_SHUTDOWN = "gateway:shutdown"

    # Session events
    SESSION_CREATED = "session:created"
    SESSION_ENDED = "session:ended"

    # Heartbeat events
    HEARTBEAT_TICK = "heartbeat:tick"
    HEARTBEAT_ALERT = "heartbeat:alert"

    # Voice events
    VOICE_WAKE = "voice:wake"
    VOICE_COMMAND = "voice:command"

    # System events
    SYSTEM_ERROR = "system:error"
    SYSTEM_WARNING = "system:warning"


@dataclass
class HookEvent:
    """Represents an event that hooks can respond to."""
    type: EventType
    action: str = ""
    timestamp: float = field(default_factory=time.time)
    session_key: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    messages: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            'type': self.type.value,
            'action': self.action,
            'timestamp': self.timestamp,
            'session_key': self.session_key,
            'context': self.context,
            'messages': list(self.messages)
        }


class HookHandler:
    """Base class for hook implementations."""

    def __init__(self, name: str, description: str = "",
                 events: List[EventType] = None, enabled: bool = True):
        self.name = name
        self.description = description
        self.events: Set[EventType] = set(events or [])
        self.enabled = enabled
        self._invocation_count = 0
        self._last_invoked = None
        self._errors = 0

    def handle(self, event: HookEvent) -> None:
        """Override this in subclasses to handle events."""
        pass

    def should_handle(self, event: HookEvent) -> bool:
        """Check if this hook should handle the given event."""
        if not self.enabled:
            return False
        if not self.events:
            return True  # No filter = handle all
        return event.type in self.events

    def get_info(self) -> Dict:
        return {
            'name': self.name,
            'description': self.description,
            'enabled': self.enabled,
            'events': [e.value for e in self.events],
            'invocations': self._invocation_count,
            'last_invoked': self._last_invoked,
            'errors': self._errors
        }


# ============ Built-in Hooks ============

class SessionMemoryHook(HookHandler):
    """Saves session context to daily memory log on command:new."""

    def __init__(self):
        super().__init__(
            name="session-memory",
            description="Saves session context to memory when starting new conversation",
            events=[EventType.COMMAND_NEW, EventType.SESSION_ENDED]
        )

    def handle(self, event: HookEvent) -> None:
        try:
            memory_dir = Path("memory")
            memory_dir.mkdir(exist_ok=True)
            today = datetime.now().strftime("%Y-%m-%d")
            log_file = memory_dir / f"{today}.md"

            timestamp = datetime.now().strftime("%H:%M:%S")
            summary = event.context.get('summary', 'Session ended')
            topic = event.context.get('topic', 'General')

            entry = f"\n## [{timestamp}] {event.type.value}\n"
            entry += f"- **Topic**: {topic}\n"
            entry += f"- **Summary**: {summary}\n"

            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(entry)

            logger.debug(f"[session-memory] Saved session context to {log_file}")
        except Exception as e:
            logger.error(f"[session-memory] Error: {e}")


class CommandLoggerHook(HookHandler):
    """Logs all command events to logs/commands.log."""

    def __init__(self):
        super().__init__(
            name="command-logger",
            description="Logs all command events for audit trail",
            events=[EventType.COMMAND_NEW, EventType.COMMAND_RESET,
                    EventType.COMMAND_STOP, EventType.VOICE_COMMAND]
        )
        self._log_dir = Path("logs")
        self._log_dir.mkdir(exist_ok=True)

    def handle(self, event: HookEvent) -> None:
        try:
            log_file = self._log_dir / "commands.log"
            timestamp = datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            command = event.context.get('command', event.action)
            source = event.context.get('source', 'unknown')

            line = f"[{timestamp}] {event.type.value} | source={source} | {command}\n"

            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(line)
        except Exception as e:
            logger.error(f"[command-logger] Error: {e}")


class BootstrapHook(HookHandler):
    """Loads BOOT.md context at gateway startup."""

    def __init__(self):
        super().__init__(
            name="boot-md",
            description="Loads BOOT.md when LADA starts up",
            events=[EventType.GATEWAY_STARTUP]
        )

    def handle(self, event: HookEvent) -> None:
        try:
            boot_file = Path("BOOT.md")
            if boot_file.exists():
                content = boot_file.read_text(encoding='utf-8')
                event.context['boot_context'] = content
                event.messages.append(f"Loaded BOOT.md ({len(content)} chars)")
                logger.info("[boot-md] BOOT.md loaded into bootstrap context")
            else:
                logger.debug("[boot-md] No BOOT.md found")
        except Exception as e:
            logger.error(f"[boot-md] Error: {e}")


class HeartbeatLoggerHook(HookHandler):
    """Logs heartbeat results."""

    def __init__(self):
        super().__init__(
            name="heartbeat-logger",
            description="Logs heartbeat tick results and alerts",
            events=[EventType.HEARTBEAT_TICK, EventType.HEARTBEAT_ALERT]
        )
        self._log_dir = Path("logs")
        self._log_dir.mkdir(exist_ok=True)

    def handle(self, event: HookEvent) -> None:
        try:
            log_file = self._log_dir / "heartbeat.log"
            timestamp = datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            result_type = event.context.get('result_type', 'unknown')
            alerts = event.context.get('alert_count', 0)
            summary = event.context.get('summary', '')

            line = f"[{timestamp}] {result_type} | alerts={alerts} | {summary[:200]}\n"

            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(line)
        except Exception as e:
            logger.error(f"[heartbeat-logger] Error: {e}")


class MessageTrackerHook(HookHandler):
    """Tracks message statistics."""

    def __init__(self):
        super().__init__(
            name="message-tracker",
            description="Tracks message counts and patterns",
            events=[EventType.MESSAGE_RECEIVED, EventType.MESSAGE_SENT]
        )
        self._stats = {'received': 0, 'sent': 0, 'by_channel': {}}

    def handle(self, event: HookEvent) -> None:
        if event.type == EventType.MESSAGE_RECEIVED:
            self._stats['received'] += 1
        elif event.type == EventType.MESSAGE_SENT:
            self._stats['sent'] += 1

        channel = event.context.get('channel', 'local')
        self._stats['by_channel'][channel] = self._stats['by_channel'].get(channel, 0) + 1

    def get_stats(self) -> Dict:
        return dict(self._stats)


# ============ Hook Manager ============

class HookManager:
    """Central manager for all event hooks. Singleton pattern."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._hooks: Dict[str, HookHandler] = {}
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="hook-")
        self._config = self._load_config()
        self._emit_lock = threading.Lock()
        self._total_events = 0
        self._total_errors = 0

        # Register built-in hooks
        self._register_builtins()

        # Discover hooks from directories
        self.discover()

        logger.info(f"[HookManager] Initialized with {len(self._hooks)} hooks")

    def _load_config(self) -> Dict:
        try:
            if CONFIG_FILE.exists():
                return json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
        except Exception as e:
            logger.warning(f"[HookManager] Could not load config: {e}")
        return {'entries': {}}

    def _save_config(self):
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(self._config, indent=2), encoding='utf-8')
        except Exception as e:
            logger.warning(f"[HookManager] Could not save config: {e}")

    def _register_builtins(self):
        """Register all built-in hooks."""
        builtins = [
            SessionMemoryHook(),
            CommandLoggerHook(),
            BootstrapHook(),
            HeartbeatLoggerHook(),
            MessageTrackerHook(),
        ]
        for hook in builtins:
            # Apply config overrides
            cfg = self._config.get('entries', {}).get(hook.name, {})
            if 'enabled' in cfg:
                hook.enabled = cfg['enabled']
            self._hooks[hook.name] = hook

    def discover(self):
        """Auto-discover hooks from directories (workspace > managed > bundled)."""
        dirs = [
            ("workspace", WORKSPACE_HOOKS_DIR),
            ("managed", MANAGED_HOOKS_DIR),
            ("bundled", BUNDLED_HOOKS_DIR),
        ]

        for source, hook_dir in dirs:
            if not hook_dir.exists():
                continue

            for item in hook_dir.iterdir():
                if not item.is_dir():
                    continue

                hook_json = item / "HOOK.json"
                handler_py = item / "handler.py"

                if not hook_json.exists() or not handler_py.exists():
                    continue

                try:
                    meta = json.loads(hook_json.read_text(encoding='utf-8'))
                    name = meta.get('name', item.name)

                    # Skip if already registered (higher precedence)
                    if name in self._hooks:
                        continue

                    # Load handler module
                    spec = importlib.util.spec_from_file_location(
                        f"hook_{name}", str(handler_py))
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)

                        # Find HookHandler subclass
                        handler_cls = None
                        for attr_name in dir(mod):
                            attr = getattr(mod, attr_name)
                            if (isinstance(attr, type) and
                                issubclass(attr, HookHandler) and
                                attr is not HookHandler):
                                handler_cls = attr
                                break

                        if handler_cls:
                            handler = handler_cls()
                            # Apply metadata
                            handler.name = name
                            handler.description = meta.get('description', handler.description)
                            event_strs = meta.get('events', [])
                            if event_strs:
                                handler.events = set()
                                for es in event_strs:
                                    try:
                                        handler.events.add(EventType(es))
                                    except ValueError:
                                        pass

                            # Apply config
                            cfg = self._config.get('entries', {}).get(name, {})
                            if 'enabled' in cfg:
                                handler.enabled = cfg['enabled']

                            self._hooks[name] = handler
                            logger.info(f"[HookManager] Discovered hook '{name}' from {source}")

                except Exception as e:
                    logger.warning(f"[HookManager] Failed to load hook from {item}: {e}")

    def register(self, handler: HookHandler):
        """Manually register a hook handler."""
        self._hooks[handler.name] = handler
        logger.info(f"[HookManager] Registered hook '{handler.name}'")

    def unregister(self, name: str):
        """Remove a hook handler."""
        if name in self._hooks:
            del self._hooks[name]
            logger.info(f"[HookManager] Unregistered hook '{name}'")

    def emit(self, event: HookEvent):
        """Fire an event to all matching handlers asynchronously (non-blocking)."""
        self._total_events += 1

        for name, hook in list(self._hooks.items()):
            if hook.should_handle(event):
                self._executor.submit(self._safe_invoke, hook, event)

    def emit_sync(self, event: HookEvent):
        """Fire an event synchronously (blocking). Use for bootstrap events."""
        self._total_events += 1

        for name, hook in list(self._hooks.items()):
            if hook.should_handle(event):
                self._safe_invoke(hook, event)

    def _safe_invoke(self, hook: HookHandler, event: HookEvent):
        """Safely invoke a hook handler, catching all errors."""
        try:
            hook.handle(event)
            hook._invocation_count += 1
            hook._last_invoked = time.time()
        except Exception as e:
            hook._errors += 1
            self._total_errors += 1
            logger.error(f"[HookManager] Hook '{hook.name}' error on {event.type.value}: {e}")

    def list_hooks(self) -> List[Dict]:
        """Show all registered hooks with status."""
        return [hook.get_info() for hook in self._hooks.values()]

    def enable(self, name: str) -> bool:
        """Enable a hook."""
        if name in self._hooks:
            self._hooks[name].enabled = True
            self._config.setdefault('entries', {})[name] = {'enabled': True}
            self._save_config()
            return True
        return False

    def disable(self, name: str) -> bool:
        """Disable a hook."""
        if name in self._hooks:
            self._hooks[name].enabled = False
            self._config.setdefault('entries', {})[name] = {'enabled': False}
            self._save_config()
            return True
        return False

    def get_hook_info(self, name: str) -> Optional[Dict]:
        """Get detailed info about a specific hook."""
        hook = self._hooks.get(name)
        if hook:
            return hook.get_info()
        return None

    def get_status(self) -> Dict:
        """Overall hook system status."""
        return {
            'total_hooks': len(self._hooks),
            'enabled_hooks': sum(1 for h in self._hooks.values() if h.enabled),
            'total_events_fired': self._total_events,
            'total_errors': self._total_errors,
            'hooks': self.list_hooks()
        }

    def shutdown(self):
        """Clean shutdown of the hook system."""
        self._executor.shutdown(wait=False)
        logger.info("[HookManager] Shut down")


# ============ Module-level helpers ============

def get_hook_manager() -> HookManager:
    """Get the singleton HookManager instance."""
    return HookManager()


def emit_event(event_type: EventType, action: str = "",
               context: Dict = None, session_key: str = "") -> HookEvent:
    """Convenience function to emit an event."""
    event = HookEvent(
        type=event_type,
        action=action,
        session_key=session_key,
        context=context or {}
    )
    get_hook_manager().emit(event)
    return event


def emit_command_event(action: str, command: str = "", source: str = "user"):
    """Emit a command lifecycle event."""
    type_map = {
        'new': EventType.COMMAND_NEW,
        'reset': EventType.COMMAND_RESET,
        'stop': EventType.COMMAND_STOP,
    }
    event_type = type_map.get(action, EventType.COMMAND_NEW)
    return emit_event(event_type, action=action, context={
        'command': command, 'source': source
    })


def emit_agent_event(action: str, task: str = "", agent_name: str = "",
                     result: str = ""):
    """Emit an agent lifecycle event."""
    type_map = {
        'bootstrap': EventType.AGENT_BOOTSTRAP,
        'start': EventType.AGENT_START,
        'complete': EventType.AGENT_COMPLETE,
        'error': EventType.AGENT_ERROR,
    }
    event_type = type_map.get(action, EventType.AGENT_START)
    return emit_event(event_type, action=action, context={
        'task': task, 'agent': agent_name, 'result': result
    })


def emit_message_event(direction: str, content: str = "",
                       channel: str = "local", sender: str = ""):
    """Emit a message event."""
    event_type = (EventType.MESSAGE_RECEIVED if direction == 'received'
                  else EventType.MESSAGE_SENT)
    return emit_event(event_type, action=direction, context={
        'content': content, 'channel': channel, 'sender': sender
    })


def emit_voice_event(action: str, command: str = ""):
    """Emit a voice event."""
    event_type = (EventType.VOICE_WAKE if action == 'wake'
                  else EventType.VOICE_COMMAND)
    return emit_event(event_type, action=action, context={'command': command})
