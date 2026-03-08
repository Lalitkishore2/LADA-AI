"""
LADA v9.0 - Memory System Tests
Tests for conversation memory and habit tracking
"""

import pytest
from lada_memory import MemorySystem, HabitTracker
from datetime import datetime, timedelta
import os
import shutil

class TestMemorySystem:
    """Test memory system"""
    
    @pytest.fixture
    def memory_system(self, tmp_path):
        # Use temporary directory for tests
        return MemorySystem(data_dir=str(tmp_path))
    
    @pytest.fixture
    def mock_conversation(self):
        return [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "user", "content": "How are you?"}
        ]
    
    def test_memory_initialization(self, memory_system):
        """Test memory initializes"""
        assert memory_system is not None
        assert hasattr(memory_system, "current_conversation")
    
    def test_save_conversation(self, memory_system, mock_conversation):
        """Test saving conversation"""
        # Add messages to memory
        for msg in mock_conversation:
            memory_system.remember(msg["role"], msg["content"])
        
        # Save conversation
        memory_system.save_conversation()
        # Check if file exists
        today = datetime.now().strftime("%Y-%m-%d")
        conv_file = memory_system.conversations_dir / f"{today}.json"
        assert conv_file.exists()
    
    def test_load_conversation(self, memory_system, mock_conversation):
        """Test loading saved conversation"""
        # Add and save messages
        for msg in mock_conversation:
            memory_system.remember(msg["role"], msg["content"])
        
        # Recall recent messages
        loaded = memory_system.recall(limit=10)
        assert loaded is not None
        assert len(loaded) == 3
    
    def test_conversation_search(self, memory_system):
        """Test searching conversations"""
        # Save test conversations
        memory_system.remember("user", "Tell me about Python")
        
        # Search in recent messages
        recent = memory_system.recall(query="Python", limit=10)
        assert len(recent) > 0
        assert "Python" in recent[0].content
    
    def test_delete_conversation(self, memory_system):
        """Test clearing conversation"""
        memory_system.remember("user", "Test message")
        assert len(memory_system.current_conversation) > 0
        
        # Clear conversation
        memory_system.clear_current_conversation()
        assert len(memory_system.current_conversation) == 0


class TestUserPreferences:
    """Test user preference learning"""
    
    @pytest.fixture
    def memory_system(self, tmp_path):
        return MemorySystem(data_dir=str(tmp_path))
    
    def test_save_preference(self, memory_system):
        """Test saving user preference"""
        memory_system.learn_preference("favorite_color", "blue")
        pref = memory_system.get_preference("favorite_color")
        assert pref == "blue"
    
    def test_update_preference(self, memory_system):
        """Test updating preference"""
        memory_system.learn_preference("theme", "dark")
        memory_system.learn_preference("theme", "light")
        
        pref = memory_system.get_preference("theme")
        assert pref == "light"
    
    def test_default_preferences(self, memory_system):
        """Test default preferences"""
        defaults = memory_system.user_preferences.custom_settings
        assert isinstance(defaults, dict)


class TestHabitTracking:
    """Test habit and pattern tracking"""
    
    @pytest.fixture
    def habit_tracker(self, tmp_path):
        # HabitTracker might need data_dir too, checking init
        # Assuming it takes data_dir or uses default
        # If it inherits or uses similar init
        return HabitTracker(data_dir=str(tmp_path))
    
    def test_track_command_usage(self, habit_tracker):
        """Test tracking command usage"""
        habit_tracker.track_command("open chrome")
        stats = habit_tracker.get_command_stats()
        assert stats["open chrome"] >= 1

