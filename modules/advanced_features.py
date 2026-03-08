"""
Advanced Features for LADA v5.0
Optional modules for extended functionality
Can be imported and used as needed
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json

logger = logging.getLogger('AdvancedFeatures')

# ===== CACHING SYSTEM =====

class ResponseCache:
    """Cache AI responses to avoid duplicate queries"""

    def __init__(self, max_size: int = 100, ttl_hours: int = 24):
        self.cache = {}
        self.max_size = max_size
        self.ttl = timedelta(hours=ttl_hours)
        self.logger = logging.getLogger('Cache')

    def get(self, query: str) -> Optional[str]:
        """Get cached response"""
        query_key = query.lower().strip()

        if query_key in self.cache:
            entry = self.cache[query_key]

            # Check if expired
            if datetime.now() - entry['timestamp'] < self.ttl:
                self.logger.info(f"💾 Cache hit: {query[:50]}...")
                return entry['response']
            else:
                # Expired, remove
                del self.cache[query_key]

        return None

    def set(self, query: str, response: str) -> bool:
        """Cache response"""
        if len(self.cache) >= self.max_size:
            # Remove oldest entry
            oldest = min(self.cache, key=lambda k: self.cache[k]['timestamp'])
            del self.cache[oldest]

        query_key = query.lower().strip()
        self.cache[query_key] = {
            'response': response,
            'timestamp': datetime.now()
        }

        self.logger.debug(f"💾 Cached: {query[:50]}...")
        return True

    def clear(self):
        """Clear entire cache"""
        self.cache.clear()
        self.logger.info("💾 Cache cleared")

    def stats(self) -> Dict:
        """Cache statistics"""
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'usage_percent': len(self.cache) / self.max_size * 100
        }

# ===== CONVERSATION HISTORY =====

class ConversationManager:
    """Manage multi-turn conversations"""

    def __init__(self, max_history: int = 10):
        self.history = []
        self.max_history = max_history
        self.logger = logging.getLogger('Conversation')

    def add_turn(self, user_input: str, assistant_response: str, backend_used: str = ''):
        """Add conversation turn"""
        self.history.append({
            'timestamp': datetime.now().isoformat(),
            'user': user_input,
            'assistant': assistant_response,
            'backend': backend_used
        })

        # Keep only recent history
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

        self.logger.debug(f"[QUERY] Added turn (total: {len(self.history)})")

    def get_context(self) -> str:
        """Get conversation context for AI"""
        context = "Recent conversation:\n"

        for turn in self.history[-3:]:  # Last 3 turns
            context += f"User: {turn['user']}\n"
            context += f"Assistant: {turn['assistant']}\n\n"

        return context

    def export(self, filename: str = 'conversation.json'):
        """Export conversation to file"""
        try:
            with open(filename, 'w') as f:
                json.dump(self.history, f, indent=2)
            self.logger.info(f"💬 Conversation exported to {filename}")
            return True
        except Exception as e:
            self.logger.error(f"Export failed: {e}")
            return False

    def clear(self):
        """Clear history"""
        self.history = []
        self.logger.info("💬 Conversation cleared")

# ===== CUSTOM COMMAND SYSTEM =====

class CustomCommandRegistry:
    """Register and manage custom commands"""

    def __init__(self):
        self.commands = {}
        self.logger = logging.getLogger('Commands')

    def register(self, name: str, keywords: List[str], handler, description: str = ''):
        """Register custom command"""
        self.commands[name] = {
            'keywords': keywords,
            'handler': handler,
            'description': description
        }
        self.logger.info(f"[OK] Command registered: {name}")

    def find_command(self, user_input: str) -> Optional[tuple]:
        """Find matching command"""
        input_lower = user_input.lower()

        for cmd_name, cmd_data in self.commands.items():
            for keyword in cmd_data['keywords']:
                if keyword.lower() in input_lower:
                    return cmd_name, cmd_data['handler']

        return None

    def execute(self, user_input: str) -> Optional[str]:
        """Execute matching command if found"""
        result = self.find_command(user_input)

        if result:
            cmd_name, handler = result
            try:
                response = handler(user_input)
                self.logger.info(f"[OK] Command executed: {cmd_name}")
                return response
            except Exception as e:
                self.logger.error(f"Command error: {e}")
                return f"Error executing {cmd_name}: {e}"

        return None

    def list_commands(self) -> List[Dict]:
        """List all available commands"""
        return [
            {
                'name': name,
                'keywords': data['keywords'],
                'description': data['description']
            }
            for name, data in self.commands.items()
        ]

# ===== PERFORMANCE MONITORING =====

class PerformanceMonitor:
    """Monitor system and JARVIS performance"""

    def __init__(self):
        self.metrics = {
            'total_queries': 0,
            'total_time': 0,
            'backend_usage': {},
            'errors': 0,
            'start_time': datetime.now()
        }
        self.logger = logging.getLogger('Performance')

    def log_query(self, backend_used: str, latency: float, success: bool = True):
        """Log query metrics"""
        self.metrics['total_queries'] += 1
        self.metrics['total_time'] += latency

        if backend_used not in self.metrics['backend_usage']:
            self.metrics['backend_usage'][backend_used] = {
                'count': 0,
                'total_time': 0
            }

        self.metrics['backend_usage'][backend_used]['count'] += 1
        self.metrics['backend_usage'][backend_used]['total_time'] += latency

        if not success:
            self.metrics['errors'] += 1

    def get_stats(self) -> Dict:
        """Get performance statistics"""
        uptime = datetime.now() - self.metrics['start_time']

        stats = {
            'uptime': str(uptime).split('.')[0],
            'total_queries': self.metrics['total_queries'],
            'average_latency': (self.metrics['total_time'] / self.metrics['total_queries']
                              if self.metrics['total_queries'] > 0 else 0),
            'error_rate': (self.metrics['errors'] / self.metrics['total_queries'] * 100
                         if self.metrics['total_queries'] > 0 else 0),
            'backend_stats': {}
        }

        for backend, data in self.metrics['backend_usage'].items():
            stats['backend_stats'][backend] = {
                'count': data['count'],
                'usage_percent': data['count'] / self.metrics['total_queries'] * 100,
                'average_latency': data['total_time'] / data['count'] if data['count'] > 0 else 0
            }

        return stats

    def print_report(self):
        """Print performance report"""
        stats = self.get_stats()

        print("\n" + "="*70)
        print("[STATS] PERFORMANCE REPORT")
        print("="*70)
        print(f"Uptime: {stats['uptime']}")
        print(f"Total Queries: {stats['total_queries']}")
        print(f"Average Latency: {stats['average_latency']:.2f}s")
        print(f"Error Rate: {stats['error_rate']:.1f}%")
        print("\nBackend Usage:")

        for backend, data in stats['backend_stats'].items():
            print(f"  {backend}: {data['count']} queries ({data['usage_percent']:.1f}%)")
            print(f"    Avg Latency: {data['average_latency']:.2f}s")

        print("="*70 + "\n")

# ===== EXAMPLE: Building with JARVIS =====

def example_advanced_integration():
    """Example of using advanced features with JARVIS"""

    # Initialize components
    cache = ResponseCache(max_size=50, ttl_hours=24)
    history = ConversationManager(max_history=10)
    commands = CustomCommandRegistry()
    monitor = PerformanceMonitor()

    # Register custom commands
    def handle_weather(input_str):
        return "Getting weather... (not implemented)"

    def handle_reminder(input_str):
        return "Setting reminder... (not implemented)"

    commands.register(
        'weather',
        ['weather', 'rain', 'temperature', 'forecast'],
        handle_weather,
        'Get weather information'
    )

    commands.register(
        'reminder',
        ['remind', 'reminder', 'alert', 'notification'],
        handle_reminder,
        'Set a reminder'
    )

    # Example query
    user_input = "What's the weather today?"

    # Try cache first
    cached = cache.get(user_input)
    if cached:
        response = cached
        backend = 'Cache'
    else:
        # Try custom commands
        cmd_response = commands.execute(user_input)
        if cmd_response:
            response = cmd_response
            backend = 'CustomCommand'
        else:
            # Would normally go to router here
            response = "Weather: Sunny, 25°C"
            backend = 'Colab'
            cache.set(user_input, response)

    # Log conversation
    history.add_turn(user_input, response, backend)

    # Monitor performance
    monitor.log_query(backend, 0.5, success=True)

    print(f"Response: {response}")
    print(f"Backend: {backend}")

    # Print stats
    monitor.print_report()
    history.export('conversation_example.json')

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    example_advanced_integration()
