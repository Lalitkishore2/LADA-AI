"""
Memory System for LADA v5.0
Learns user preferences, command history, patterns
Persistent storage for learning across sessions
"""

import pickle
import json
from datetime import datetime
from pathlib import Path
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger('Memory')

class MemorySystem:
    """Persistent memory for LADA - learns and adapts"""

    def __init__(self, data_dir: str = 'data'):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)

        self.memory_file = self.data_dir / 'lada_memory.pkl'
        self.preferences_file = self.data_dir / 'preferences.json'
        self.history_file = self.data_dir / 'command_history.json'

        self.memory = self._load()
        logger.info("[OK] Memory system initialized")

    def _load(self) -> Dict:
        """Load memory from disk or create new"""
        if self.memory_file.exists():
            try:
                with open(self.memory_file, 'rb') as f:
                    memory = pickle.load(f)
                    logger.info("[OK] Memory loaded from disk")
                    return memory
            except Exception as e:
                logger.warning(f"Could not load memory: {e}, starting fresh")

        # Default memory structure
        return {
            'user_name': 'Sir',
            'preferences': {},
            'command_history': [],
            'learned_responses': {},
            'routines': {},
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat()
        }

    def _save(self):
        """Save memory to disk"""
        try:
            self.memory['last_updated'] = datetime.now().isoformat()

            with open(self.memory_file, 'wb') as f:
                pickle.dump(self.memory, f)

            logger.debug("[OK] Memory saved to disk")
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")

    def remember(self, key: str, value: Any):
        """Remember something in history"""
        self.memory['command_history'].append({
            'timestamp': datetime.now().isoformat(),
            'key': key,
            'value': value
        })

        # Keep only last 100 items to avoid bloat
        if len(self.memory['command_history']) > 100:
            self.memory['command_history'] = self.memory['command_history'][-100:]

        self._save()
        logger.debug(f"[QUERY] Remembered: {key}")

    def remember_message(self, role: str, content: str, meta: Optional[Dict[str, Any]] = None):
        """Compatibility wrapper: remember a chat message.

        Some parts of the app expect a `remember_message()` API.
        We store it in the existing command_history stream.
        """
        try:
            self.remember(
                'chat_message',
                {
                    'role': role,
                    'content': content,
                    'meta': meta or {},
                },
            )
        except Exception as e:
            logger.error(f"Failed to remember_message: {e}")

    def recall(self, key: str, limit: int = 5) -> List[Any]:
        """Recall values from history (most recent first)"""
        results = []
        for item in reversed(self.memory['command_history']):
            if item['key'] == key:
                results.append(item['value'])
                if len(results) >= limit:
                    break
        return results

    def get_last(self, key: str) -> Optional[Any]:
        """Get last occurrence of a key"""
        for item in reversed(self.memory['command_history']):
            if item['key'] == key:
                return item['value']
        return None

    def set_preference(self, key: str, value: Any):
        """Store user preference"""
        self.memory['preferences'][key] = {
            'value': value,
            'set_at': datetime.now().isoformat()
        }
        self._save()
        logger.info(f"🎯 Preference set: {key} = {value}")

    def get_preference(self, key: str, default=None) -> Any:
        """Get user preference"""
        pref = self.memory['preferences'].get(key)
        if pref:
            return pref.get('value', default)
        return default

    def learn_response(self, query: str, response: str):
        """Learn a frequently used response pattern"""
        query_key = query.lower().strip()

        self.memory['learned_responses'][query_key] = {
            'response': response,
            'count': self.memory['learned_responses'].get(query_key, {}).get('count', 0) + 1,
            'learned_at': datetime.now().isoformat()
        }

        self._save()
        logger.info(f"📚 Learned: {query[:50]}...")

    def get_learned(self, query: str) -> Optional[str]:
        """Get learned response for query"""
        query_key = query.lower().strip()
        learned = self.memory['learned_responses'].get(query_key)

        if learned:
            logger.debug(f"Recalling learned response for: {query}")
            return learned['response']

        return None

    def create_routine(self, routine_name: str, commands: List[str]):
        """Create a routine (sequence of commands)"""
        self.memory['routines'][routine_name] = {
            'commands': commands,
            'created_at': datetime.now().isoformat(),
            'executed_count': 0
        }
        self._save()
        logger.info(f"🔄 Routine created: {routine_name}")

    def get_routine(self, routine_name: str) -> Optional[List[str]]:
        """Get routine by name"""
        routine = self.memory['routines'].get(routine_name)
        if routine:
            return routine['commands']
        return None

    def execute_routine(self, routine_name: str) -> bool:
        """Mark routine as executed"""
        if routine_name in self.memory['routines']:
            self.memory['routines'][routine_name]['executed_count'] += 1
            self.memory['routines'][routine_name]['last_executed'] = datetime.now().isoformat()
            self._save()
            logger.info(f"Executed routine: {routine_name}")
            return True
        return False

    def set_name(self, name: str):
        """Set user's preferred name"""
        self.memory['user_name'] = name
        self._save()
        logger.info(f"User name set to: {name}")

    def get_name(self) -> str:
        """Get user's preferred name"""
        return self.memory['user_name']

    def get_stats(self) -> Dict:
        """Get memory statistics"""
        return {
            'user_name': self.memory['user_name'],
            'total_interactions': len(self.memory['command_history']),
            'learned_responses': len(self.memory['learned_responses']),
            'preferences': len(self.memory['preferences']),
            'routines': len(self.memory['routines']),
            'memory_created': self.memory['created_at'],
            'last_updated': self.memory['last_updated']
        }

    def export_memory(self, filename: str = 'lada_memory_export.json'):
        """Export memory to JSON for backup"""
        try:
            export_data = {
                'user_name': self.memory['user_name'],
                'preferences': self.memory['preferences'],
                'learned_responses': self.memory['learned_responses'],
                'routines': self.memory['routines'],
                'created_at': self.memory['created_at'],
                'last_updated': self.memory['last_updated']
            }

            with open(self.data_dir / filename, 'w') as f:
                json.dump(export_data, f, indent=2)

            logger.info(f"[OK] Memory exported to {filename}")
            return True
        except Exception as e:
            logger.error(f"Failed to export memory: {e}")
            return False

    def clear_history(self, keep_last: int = 10):
        """Clear old history keeping only recent"""
        if keep_last > 0:
            self.memory['command_history'] = self.memory['command_history'][-keep_last:]
        else:
            self.memory['command_history'] = []

        self._save()
        logger.info(f"History cleared, kept {min(keep_last, len(self.memory['command_history']))} items")

    def reset_all(self):
        """Reset all memory (careful!)"""
        self.memory = {
            'user_name': 'Sir',
            'preferences': {},
            'command_history': [],
            'learned_responses': {},
            'routines': {},
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat()
        }
        self._save()
        logger.warning("🚨 All memory reset!")

# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    memory = MemorySystem()

    # Learn preferences
    memory.set_preference('favorite_browser', 'chrome')
    memory.set_preference('work_hours', '9am-5pm')
    memory.set_name('Dev User')

    # Remember commands
    memory.remember('search_query', 'machine learning')
    memory.learn_response('what is machine learning', 'ML is a subset of AI...')

    # Create routine
    memory.create_routine('morning', [
        'open github',
        'open vscode',
        'start coding'
    ])

    # Recall
    print(f"Browser: {memory.get_preference('favorite_browser')}")
    print(f"Name: {memory.get_name()}")
    print(f"Routine: {memory.get_routine('morning')}")
    print(f"Stats: {memory.get_stats()}")
