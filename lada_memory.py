"""
LADA v7.0 - Memory System
Persistent conversation storage, user preferences, and context learning

Features:
- Long-term memory across sessions
- User preference learning
- Conversation history storage
- Context retention for better responses
- Auto-save and recovery
"""

import os
import json
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class ConversationMessage:
    """Single message in a conversation"""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    language: str = 'en'
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UserPreferences:
    """User preferences learned over time"""
    preferred_language: str = 'en'
    voice_speed: int = 160
    voice_volume: float = 0.9
    topics_of_interest: List[str] = field(default_factory=list)
    response_style: str = 'balanced'  # 'concise', 'balanced', 'detailed'
    custom_settings: Dict[str, Any] = field(default_factory=dict)


class MemorySystem:
    """
    LADA Memory System - Remembers everything!
    
    Features:
    - Conversation storage (per day files)
    - Long-term memory (facts, preferences)
    - User preference learning
    - Context retention for multi-turn conversations
    - Auto-save with configurable interval
    """
    
    def __init__(self, data_dir: str = None):
        """
        Initialize the memory system
        
        Args:
            data_dir: Directory to store memory files
        """
        self.data_dir = Path(data_dir or os.getenv('DATA_DIR', './data'))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories
        self.conversations_dir = self.data_dir / 'conversations'
        self.conversations_dir.mkdir(exist_ok=True)
        
        # File paths
        self.memory_file = self.data_dir / 'lada_memory.json'
        self.preferences_file = self.data_dir / 'preferences.json'
        self.backup_file = self.data_dir / 'lada_memory_backup.json'
        
        # In-memory storage
        self.current_conversation: List[ConversationMessage] = []
        self.long_term_memory: Dict[str, Any] = {}
        self.user_preferences = UserPreferences()
        self.context_cache: Dict[str, Any] = {}
        
        # Statistics
        self.stats = {
            'total_messages': 0,
            'total_conversations': 0,
            'topics_discussed': defaultdict(int),
            'languages_used': defaultdict(int)
        }
        
        # Auto-save settings
        self.autosave_interval = int(os.getenv('MEMORY_AUTOSAVE_INTERVAL', '300'))
        self._autosave_thread: Optional[threading.Thread] = None
        self._stop_autosave = threading.Event()
        
        # Load existing data
        self._load_memory()
        self._load_preferences()

        # Named session tracking (per-topic persistence)
        self.current_session_name: Optional[str] = None
        self._sessions_dir = self.data_dir / 'sessions'
        self._sessions_dir.mkdir(exist_ok=True)

        # Start auto-save
        self._start_autosave()
        
        logger.info(f"✅ MemorySystem initialized (Data dir: {self.data_dir})")
    
    def remember(self, role: str, content: str, language: str = 'en', metadata: Dict = None) -> None:
        """
        Remember a message from the conversation
        
        Args:
            role: 'user' or 'assistant'
            content: Message content
            language: Language code ('en', 'ta')
            metadata: Additional metadata
        """
        if not content or len(content.strip()) == 0:
            return
        
        message = ConversationMessage(
            role=role,
            content=content.strip(),
            language=language,
            metadata=metadata or {}
        )
        
        self.current_conversation.append(message)
        self.stats['total_messages'] += 1
        self.stats['languages_used'][language] += 1
        
        # Extract and remember important information
        if role == 'user':
            self._extract_preferences(content, language)
        
        logger.debug(f"Remembered {role} message ({language})")
    
    def recall(self, query: str = None, limit: int = 10) -> List[ConversationMessage]:
        """
        Recall recent or relevant messages
        
        Args:
            query: Optional search query
            limit: Maximum messages to return
            
        Returns:
            List of matching messages
        """
        if not query:
            # Return recent messages
            return self.current_conversation[-limit:]
        
        # Simple keyword search
        query_lower = query.lower()
        matching = [
            msg for msg in self.current_conversation
            if query_lower in msg.content.lower()
        ]
        
        return matching[-limit:]
    
    def get_context(self, num_messages: int = 6) -> str:
        """
        Get recent conversation context as string
        
        Args:
            num_messages: Number of recent messages to include
            
        Returns:
            Formatted context string
        """
        recent = self.current_conversation[-num_messages:]
        
        if not recent:
            return ""
        
        context_parts = []
        for msg in recent:
            role = "User" if msg.role == "user" else "LADA"
            context_parts.append(f"{role}: {msg.content}")
        
        return "\n".join(context_parts)
    
    def store_fact(self, key: str, value: Any, category: str = 'general') -> None:
        """
        Store a fact in long-term memory
        
        Args:
            key: Fact identifier
            value: Fact value
            category: Category for organization
        """
        if category not in self.long_term_memory:
            self.long_term_memory[category] = {}
        
        self.long_term_memory[category][key] = {
            'value': value,
            'stored_at': datetime.now().isoformat(),
            'access_count': 0
        }
        
        logger.debug(f"Stored fact: {category}/{key}")
    
    def recall_fact(self, key: str, category: str = 'general') -> Optional[Any]:
        """
        Recall a fact from long-term memory
        
        Args:
            key: Fact identifier
            category: Category to search
            
        Returns:
            Fact value or None
        """
        if category not in self.long_term_memory:
            return None
        
        fact = self.long_term_memory[category].get(key)
        
        if fact:
            fact['access_count'] = fact.get('access_count', 0) + 1
            return fact['value']
        
        return None
    
    def learn_preference(self, key: str, value: Any) -> None:
        """
        Learn a user preference
        
        Args:
            key: Preference key
            value: Preference value
        """
        if hasattr(self.user_preferences, key):
            setattr(self.user_preferences, key, value)
        else:
            self.user_preferences.custom_settings[key] = value
        
        logger.info(f"Learned preference: {key} = {value}")
    
    def get_preference(self, key: str, default: Any = None) -> Any:
        """
        Get a user preference
        
        Args:
            key: Preference key
            default: Default value
            
        Returns:
            Preference value
        """
        if hasattr(self.user_preferences, key):
            return getattr(self.user_preferences, key)
        
        return self.user_preferences.custom_settings.get(key, default)
    
    def _extract_preferences(self, text: str, language: str) -> None:
        """Extract preferences from user input"""
        text_lower = text.lower()
        
        # Update preferred language based on usage
        self.stats['languages_used'][language] += 1
        
        # Determine most used language
        lang_counts = self.stats['languages_used']
        if lang_counts:
            most_used = max(lang_counts, key=lang_counts.get)
            self.user_preferences.preferred_language = most_used
    
    def save_conversation(self) -> None:
        """Save current conversation to daily file"""
        if not self.current_conversation:
            return
        
        today = datetime.now().strftime('%Y-%m-%d')
        conv_file = self.conversations_dir / f'{today}.json'
        
        # Load existing or create new
        existing = []
        if conv_file.exists():
            try:
                with open(conv_file, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except:
                existing = []
        
        # Add current conversation
        session = {
            'session_id': datetime.now().strftime('%Y%m%d_%H%M%S'),
            'messages': [asdict(msg) for msg in self.current_conversation],
            'stats': {
                'message_count': len(self.current_conversation),
                'started_at': self.current_conversation[0].timestamp if self.current_conversation else None
            }
        }
        
        existing.append(session)
        
        # Save
        with open(conv_file, 'w', encoding='utf-8') as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved conversation to {conv_file}")

    # ── Named Session (Per-Topic Persistent Conversations) ──────────────

    def start_named_session(self, name: str) -> bool:
        """
        Switch to a named topic session.

        Saves the current session first, then loads the named session if it
        already exists, or starts fresh if it doesn't.

        Returns:
            True if an existing session was loaded, False if new session started.
        """
        name = name.strip()
        if not name:
            return False

        # Save whatever is in the current session before switching
        if self.current_conversation:
            if self.current_session_name:
                self.save_named_session()
            else:
                self.save_conversation()

        self.current_session_name = name
        session_path = self._sessions_dir / f"{name}.json"

        if session_path.exists():
            try:
                with open(session_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.current_conversation = [
                    ConversationMessage(**msg) for msg in data.get('messages', [])
                ]
                logger.info(f"[Memory] Loaded named session '{name}' "
                            f"({len(self.current_conversation)} messages)")
                return True
            except Exception as e:
                logger.warning(f"[Memory] Could not load session '{name}': {e}")
        # New session
        self.current_conversation = []
        logger.info(f"[Memory] Started new named session '{name}'")
        return False

    def save_named_session(self) -> None:
        """Save the current conversation to its named session file."""
        name = self.current_session_name
        if not name or not self.current_conversation:
            return
        session_path = self._sessions_dir / f"{name}.json"
        try:
            data = {
                'session_name': name,
                'updated_at': datetime.now().isoformat(),
                'messages': [asdict(msg) for msg in self.current_conversation],
            }
            with open(session_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f"[Memory] Saved named session '{name}'")
        except Exception as e:
            logger.warning(f"[Memory] Could not save session '{name}': {e}")

    def list_named_sessions(self) -> List[str]:
        """Return sorted list of saved named session names."""
        return sorted(p.stem for p in self._sessions_dir.glob('*.json'))

    def delete_named_session(self, name: str) -> bool:
        """Delete a named session file. Returns True if deleted."""
        session_path = self._sessions_dir / f"{name}.json"
        if session_path.exists():
            try:
                session_path.unlink()
                if self.current_session_name == name:
                    self.current_session_name = None
                return True
            except Exception as e:
                logger.warning(f"[Memory] Could not delete session '{name}': {e}")
        return False

    def _load_memory(self) -> None:
        """Load long-term memory from file"""
        try:
            if self.memory_file.exists():
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.long_term_memory = data.get('memory', {})
                    self.stats = data.get('stats', self.stats)
                    logger.info("Loaded long-term memory")
        except Exception as e:
            logger.warning(f"Could not load memory: {e}")
            # Try backup
            if self.backup_file.exists():
                try:
                    with open(self.backup_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self.long_term_memory = data.get('memory', {})
                        logger.info("Loaded from backup")
                except:
                    pass
    
    def _save_memory(self) -> None:
        """Save long-term memory to file"""
        try:
            # Backup existing file first
            if self.memory_file.exists():
                import shutil
                shutil.copy(self.memory_file, self.backup_file)
            
            data = {
                'memory': self.long_term_memory,
                'stats': dict(self.stats),
                'saved_at': datetime.now().isoformat()
            }
            
            # Convert defaultdict to dict for JSON
            data['stats']['topics_discussed'] = dict(self.stats['topics_discussed'])
            data['stats']['languages_used'] = dict(self.stats['languages_used'])
            
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug("Saved long-term memory")
            
        except Exception as e:
            logger.error(f"Could not save memory: {e}")
    
    def _load_preferences(self) -> None:
        """Load user preferences from file"""
        try:
            if self.preferences_file.exists():
                with open(self.preferences_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.user_preferences = UserPreferences(**data)
                    logger.info("Loaded user preferences")
        except Exception as e:
            logger.warning(f"Could not load preferences: {e}")
    
    def _save_preferences(self) -> None:
        """Save user preferences to file"""
        try:
            with open(self.preferences_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(self.user_preferences), f, indent=2)
            logger.debug("Saved user preferences")
        except Exception as e:
            logger.error(f"Could not save preferences: {e}")
    
    def _start_autosave(self) -> None:
        """Start auto-save background thread"""
        def autosave_worker():
            while not self._stop_autosave.wait(timeout=self.autosave_interval):
                self.save_all()
        
        self._autosave_thread = threading.Thread(target=autosave_worker, daemon=True)
        self._autosave_thread.start()
        logger.debug(f"Auto-save started (interval: {self.autosave_interval}s)")
    
    def save_all(self) -> None:
        """Save all memory components"""
        self._save_memory()
        self._save_preferences()
        self.save_conversation()
    
    def clear_current_conversation(self) -> None:
        """Clear current conversation (after saving)"""
        self.save_conversation()
        self.current_conversation = []
        self.stats['total_conversations'] += 1
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get memory statistics"""
        return {
            'total_messages': self.stats['total_messages'],
            'total_conversations': self.stats['total_conversations'],
            'current_conversation_length': len(self.current_conversation),
            'long_term_facts': sum(len(v) for v in self.long_term_memory.values()),
            'preferred_language': self.user_preferences.preferred_language,
            'languages_used': dict(self.stats['languages_used'])
        }
    
    # ============================================================
    # Backward-compatible API (matches modules/memory_system.py)
    # Used by lada_jarvis_core.py
    # ============================================================

    def remember(self, key_or_role: str, value_or_content=None, **kwargs):
        """Backward-compatible remember method.

        Supports both old API: remember(key, value)
        and new API: remember(role, content, language=, metadata=)
        """
        if value_or_content is None:
            return
        # If called with role/content pattern (new API), delegate to parent
        if key_or_role in ('user', 'assistant', 'system'):
            language = kwargs.get('language', 'en')
            metadata = kwargs.get('metadata', None)
            msg = ConversationMessage(
                role=key_or_role,
                content=str(value_or_content),
                language=language,
                metadata=metadata or {},
            )
            self.current_conversation.append(msg)
            self.stats['total_messages'] += 1
            return
        # Old API: remember(key, value), store as a fact
        self.store_fact(key_or_role, value_or_content, category='command_history')

    def learn_response(self, query: str, response: str):
        """Learn a query→response pattern for fast recall."""
        key = f"learned:{query.lower().strip()}"
        self.store_fact(key, {
            'response': response,
            'learned_at': datetime.now().isoformat(),
        }, category='learned_responses')

    def get_learned(self, query: str) -> Optional[str]:
        """Get a previously learned response for a query."""
        key = f"learned:{query.lower().strip()}"
        entry = self.recall_fact(key, category='learned_responses')
        if entry and isinstance(entry, dict):
            return entry.get('response')
        return None

    def get_routine(self, routine_name: str) -> Optional[List[str]]:
        """Get a stored routine's commands."""
        entry = self.recall_fact(f"routine:{routine_name}", category='routines')
        if entry and isinstance(entry, dict):
            return entry.get('commands')
        return None

    def create_routine(self, routine_name: str, commands: List[str]):
        """Create/update a named routine."""
        self.store_fact(f"routine:{routine_name}", {
            'commands': commands,
            'created_at': datetime.now().isoformat(),
        }, category='routines')

    def shutdown(self) -> None:
        """Clean shutdown - save everything"""
        logger.info("Memory system shutting down...")
        self._stop_autosave.set()
        self.save_all()
        logger.info("Memory saved successfully")


class HabitTracker:
    """
    Tracks user habits and usage patterns
    Learns from user behavior to provide better assistance
    """
    
    def __init__(self, data_dir: str = None):
        """Initialize habit tracker"""
        self.data_dir = Path(data_dir or './data')
        self.habits_file = self.data_dir / 'habits.json'
        
        # Usage tracking
        self.command_frequency = defaultdict(int)
        self.time_patterns = defaultdict(list)  # hour -> list of commands
        self.daily_usage = defaultdict(int)  # date -> count
        self.query_history = []
        self.interaction_log = []
        
        self._load_habits()
    
    def track_command(self, command: str, timestamp: datetime = None):
        """
        Track command usage
        
        Args:
            command: Command executed
            timestamp: When command was executed (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # Update frequency
        self.command_frequency[command.lower()] += 1
        
        # Track time pattern
        hour = timestamp.hour
        self.time_patterns[hour].append(command)
        
        # Track daily usage
        date_str = timestamp.strftime('%Y-%m-%d')
        self.daily_usage[date_str] += 1
        
        # Add to interaction log
        self.interaction_log.append({
            'timestamp': timestamp.isoformat(),
            'command': command,
            'hour': hour,
            'day_of_week': timestamp.weekday()
        })
        
        # Keep only last 1000 interactions
        self.interaction_log = self.interaction_log[-1000:]
    
    def track_query(self, query: str):
        """Track user query"""
        self.query_history.append({
            'query': query.lower(),
            'timestamp': datetime.now().isoformat()
        })
        self.query_history = self.query_history[-500:]
    
    def log_interaction(self, timestamp: datetime = None, command: str = None):
        """Log a general interaction"""
        if timestamp is None:
            timestamp = datetime.now()
        
        if command:
            self.track_command(command, timestamp)
    
    def get_command_stats(self) -> Dict[str, int]:
        """Get command usage statistics"""
        return dict(self.command_frequency)
    
    def get_frequent_queries(self, top_n: int = 10) -> List[str]:
        """
        Get most frequent queries
        
        Args:
            top_n: Number of top queries to return
        
        Returns:
            List of most frequent queries
        """
        query_counts = defaultdict(int)
        for item in self.query_history:
            query_counts[item['query']] += 1
        
        sorted_queries = sorted(
            query_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        return [q for q, _ in sorted_queries[:top_n]]
    
    def get_usage_patterns(self) -> Dict[str, Any]:
        """
        Analyze usage patterns
        
        Returns:
            Dict with pattern analysis
        """
        if not self.interaction_log:
            return {}
        
        # Peak usage hours
        hour_counts = defaultdict(int)
        for interaction in self.interaction_log:
            hour_counts[interaction['hour']] += 1
        
        peak_hour = max(hour_counts.items(), key=lambda x: x[1])[0]
        
        # Day of week patterns
        day_counts = defaultdict(int)
        for interaction in self.interaction_log:
            day_counts[interaction['day_of_week']] += 1
        
        # Average daily usage
        if self.daily_usage:
            avg_daily = sum(self.daily_usage.values()) / len(self.daily_usage)
        else:
            avg_daily = 0
        
        return {
            'peak_hour': peak_hour,
            'peak_hour_friendly': self._hour_to_friendly(peak_hour),
            'usage_by_hour': dict(hour_counts),
            'usage_by_day': dict(day_counts),
            'average_daily_interactions': avg_daily,
            'total_interactions': len(self.interaction_log)
        }
    
    def detect_routines(self) -> List[Dict[str, Any]]:
        """
        Detect daily routines
        
        Returns:
            List of detected routines
        """
        routines = []
        
        # Group commands by hour
        hour_commands = defaultdict(list)
        for interaction in self.interaction_log:
            hour = interaction['hour']
            command = interaction['command']
            hour_commands[hour].append(command)
        
        # Find patterns
        for hour, commands in hour_commands.items():
            if len(commands) >= 5:  # At least 5 occurrences
                # Count command frequency at this hour
                cmd_counts = defaultdict(int)
                for cmd in commands:
                    cmd_counts[cmd] += 1
                
                # Find most common command
                if cmd_counts:
                    most_common = max(cmd_counts.items(), key=lambda x: x[1])
                    command, count = most_common
                    
                    if count >= 3:  # At least 3 times
                        routines.append({
                            'time': f"{hour:02d}:00",
                            'time_friendly': self._hour_to_friendly(hour),
                            'command': command,
                            'frequency': count,
                            'confidence': count / len(commands)
                        })
        
        return sorted(routines, key=lambda x: x['confidence'], reverse=True)
    
    def suggest_next_action(self) -> Optional[str]:
        """
        Suggest next action based on patterns
        
        Returns:
            Suggested command or None
        """
        current_hour = datetime.now().hour
        
        # Check if there's a routine at this hour
        routines = self.detect_routines()
        for routine in routines:
            routine_hour = int(routine['time'].split(':')[0])
            if routine_hour == current_hour and routine['confidence'] > 0.5:
                return routine['command']
        
        return None
    
    def _hour_to_friendly(self, hour: int) -> str:
        """Convert 24h hour to friendly name"""
        if 5 <= hour < 12:
            return "Morning"
        elif 12 <= hour < 17:
            return "Afternoon"
        elif 17 <= hour < 21:
            return "Evening"
        else:
            return "Night"
    
    def _load_habits(self):
        """Load saved habits"""
        try:
            if self.habits_file.exists():
                with open(self.habits_file) as f:
                    data = json.load(f)
                
                self.command_frequency = defaultdict(int, data.get('command_frequency', {}))
                self.time_patterns = defaultdict(list, data.get('time_patterns', {}))
                self.daily_usage = defaultdict(int, data.get('daily_usage', {}))
                self.query_history = data.get('query_history', [])
                self.interaction_log = data.get('interaction_log', [])
                
        except Exception as e:
            logger.error(f"Error loading habits: {e}")
    
    def save_habits(self):
        """Save habits to file"""
        try:
            data = {
                'command_frequency': dict(self.command_frequency),
                'time_patterns': {str(k): v for k, v in self.time_patterns.items()},
                'daily_usage': dict(self.daily_usage),
                'query_history': self.query_history,
                'interaction_log': self.interaction_log,
                'last_updated': datetime.now().isoformat()
            }
            
            with open(self.habits_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving habits: {e}")


# Quick test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    memory = MemorySystem()
    
    # Test remembering
    memory.remember('user', 'Hello! My name is Kumar.', 'en')
    memory.remember('assistant', 'Hello Kumar! Nice to meet you.', 'en')
    memory.remember('user', 'வணக்கம்! எப்படி இருக்கீங்க?', 'ta')
    memory.remember('assistant', 'வணக்கம்! நான் நலம், நன்றி!', 'ta')
    
    # Test recall
    print("\n📜 Recent messages:")
    for msg in memory.recall(limit=5):
        print(f"  [{msg.role}] {msg.content}")
    
    # Test context
    print("\n📝 Context:")
    print(memory.get_context())
    
    # Test stats
    print("\n📊 Statistics:")
    stats = memory.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Save
    memory.save_all()
    print("\n✅ Memory test complete!")


# Backward compatibility alias
ConversationMemory = MemorySystem


# ============================================================================
# MARKDOWN MEMORY STACK (OpenClaw-style git-backable memory)
# ============================================================================

class MarkdownMemoryStack:
    """
    Git-backable Markdown memory system (OpenClaw pattern).
    
    Structure:
    - memory/MEMORY.md: Long-term curated memory (facts, preferences)
    - memory/YYYY-MM-DD.md: Append-only daily logs
    - memory/.git: Optional git history for versioning
    
    The markdown files are human-readable and can be version-controlled.
    They complement the JSON storage for semantic search and structured queries.
    """
    
    def __init__(self, workspace_dir: str = None):
        self.workspace = Path(workspace_dir or os.getenv('LADA_WORKSPACE', './memory'))
        self.workspace.mkdir(parents=True, exist_ok=True)
        
        self.memory_file = self.workspace / 'MEMORY.md'
        self._ensure_memory_file()
        
        logger.info(f"[MarkdownMemory] Initialized at {self.workspace}")
    
    def _ensure_memory_file(self):
        """Create MEMORY.md if it doesn't exist."""
        if not self.memory_file.exists():
            header = """# LADA Long-Term Memory

This file contains curated facts and preferences learned over time.
It is loaded into private sessions to maintain context.

---

## User Profile

- **Name**: Unknown
- **Preferred Language**: English

## Key Facts

(Add important facts here)

## Preferences

(Add user preferences here)

## Projects

(Track ongoing projects)

---
*Last updated: {date}*
""".format(date=datetime.now().strftime('%Y-%m-%d %H:%M'))
            self.memory_file.write_text(header, encoding='utf-8')
    
    def get_daily_log_path(self, date: datetime = None) -> Path:
        """Get path to daily log file."""
        if date is None:
            date = datetime.now()
        return self.workspace / f"{date.strftime('%Y-%m-%d')}.md"
    
    def append_to_daily_log(self, content: str, category: str = "interaction"):
        """Append an entry to today's daily log."""
        log_path = self.get_daily_log_path()
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        # Create file with header if it doesn't exist
        if not log_path.exists():
            header = f"""# Daily Log - {datetime.now().strftime('%Y-%m-%d')}

Session started at {timestamp}

---

"""
            log_path.write_text(header, encoding='utf-8')
        
        # Append entry
        entry = f"\n### [{timestamp}] {category.upper()}\n\n{content}\n"
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(entry)
    
    def log_conversation(self, role: str, content: str):
        """Log a conversation turn to daily log."""
        prefix = "👤 **User**:" if role == "user" else "🤖 **LADA**:"
        self.append_to_daily_log(f"{prefix} {content}", category="chat")
    
    def log_action(self, action: str, result: str = None):
        """Log an action/command to daily log."""
        entry = f"**Action**: `{action}`"
        if result:
            entry += f"\n**Result**: {result}"
        self.append_to_daily_log(entry, category="action")
    
    def log_insight(self, insight: str):
        """Log an AI-generated insight to daily log."""
        self.append_to_daily_log(f"💡 {insight}", category="insight")
    
    def write_to_memory(self, section: str, content: str):
        """
        Write/update a section in MEMORY.md.
        
        Sections are identified by ## headers.
        """
        current = self.memory_file.read_text(encoding='utf-8')
        
        # Find section
        section_header = f"## {section}"
        if section_header in current:
            # Update existing section - find start and end
            lines = current.split('\n')
            new_lines = []
            in_section = False
            section_written = False
            
            for line in lines:
                if line.strip().startswith('## '):
                    if line.strip() == section_header:
                        in_section = True
                        new_lines.append(line)
                        new_lines.append('')
                        new_lines.append(content)
                        new_lines.append('')
                        section_written = True
                        continue
                    else:
                        in_section = False
                
                if not in_section:
                    new_lines.append(line)
            
            if section_written:
                current = '\n'.join(new_lines)
        else:
            # Add new section before the footer
            footer_marker = "---\n*Last updated:"
            if footer_marker in current:
                current = current.replace(
                    footer_marker,
                    f"## {section}\n\n{content}\n\n{footer_marker}"
                )
            else:
                current += f"\n\n## {section}\n\n{content}\n"
        
        # Update last modified
        current = current.rsplit('*Last updated:', 1)[0]
        current += f"*Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n"
        
        self.memory_file.write_text(current, encoding='utf-8')
        logger.debug(f"[MarkdownMemory] Updated section: {section}")
    
    def read_memory(self) -> str:
        """Read full MEMORY.md content."""
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding='utf-8')
        return ""
    
    def read_daily_log(self, date: datetime = None) -> str:
        """Read a specific day's log."""
        log_path = self.get_daily_log_path(date)
        if log_path.exists():
            return log_path.read_text(encoding='utf-8')
        return ""
    
    def get_recent_logs(self, days: int = 7) -> List[Tuple[str, str]]:
        """Get recent daily logs."""
        logs = []
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            log_path = self.get_daily_log_path(date)
            if log_path.exists():
                logs.append((
                    date.strftime('%Y-%m-%d'),
                    log_path.read_text(encoding='utf-8')
                ))
        return logs
    
    def flush_critical_notes(self, notes: List[str]):
        """
        Pre-compaction flush: Write critical notes to daily log before context is trimmed.
        
        This is called by ContextManager right before auto-compaction.
        """
        if not notes:
            return
        
        content = "**Pre-Compaction Memory Flush**\n\nThe following important notes were extracted before context compaction:\n\n"
        for note in notes:
            content += f"- {note}\n"
        
        self.append_to_daily_log(content, category="memory-flush")
        logger.info(f"[MarkdownMemory] Flushed {len(notes)} critical notes before compaction")
    
    def consolidate_to_memory(self, facts: Dict[str, str]):
        """
        Consolidate learned facts into MEMORY.md.
        
        Called during idle consolidation (KAIROS Auto-Dream).
        """
        if not facts:
            return
        
        for section, content in facts.items():
            self.write_to_memory(section, content)
        
        logger.info(f"[MarkdownMemory] Consolidated {len(facts)} fact sections to MEMORY.md")


# Add timedelta import for get_recent_logs
from datetime import timedelta


# Module-level singleton for markdown memory
_md_memory: Optional[MarkdownMemoryStack] = None


def get_markdown_memory() -> MarkdownMemoryStack:
    """Get or create the global markdown memory stack."""
    global _md_memory
    if _md_memory is None:
        _md_memory = MarkdownMemoryStack()
    return _md_memory
