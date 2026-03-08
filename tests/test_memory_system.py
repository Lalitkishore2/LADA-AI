"""
Tests for modules/memory_system.py
Covers: MemorySystem class for persistent memory
"""

import pytest
import sys
import pickle
import json
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
from datetime import datetime


# Reset module cache
@pytest.fixture(autouse=True)
def reset_modules():
    """Reset module cache before each test."""
    modules_to_reset = [k for k in sys.modules.keys() if 'memory_system' in k]
    for mod in modules_to_reset:
        del sys.modules[mod]
    yield


class TestMemorySystemInit:
    """Tests for MemorySystem initialization."""
    
    def test_init_default(self, tmp_path):
        """Test default initialization."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        assert memory.data_dir == tmp_path
    
    def test_init_creates_directory(self, tmp_path):
        """Test that init creates data directory."""
        from modules import memory_system as ms
        data_path = tmp_path / "new_data"
        memory = ms.MemorySystem(data_dir=str(data_path))
        assert data_path.exists()
    
    def test_init_loads_fresh_memory(self, tmp_path):
        """Test fresh memory initialization."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        assert 'user_name' in memory.memory
        assert 'preferences' in memory.memory
        assert 'command_history' in memory.memory


class TestRemember:
    """Tests for remember functionality."""
    
    def test_remember_basic(self, tmp_path):
        """Test basic remember."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        memory.remember("test_key", "test_value")
        
        # Check it was added to history
        assert len(memory.memory['command_history']) > 0
        last_item = memory.memory['command_history'][-1]
        assert last_item['key'] == "test_key"
        assert last_item['value'] == "test_value"
    
    def test_remember_with_timestamp(self, tmp_path):
        """Test remember includes timestamp."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        memory.remember("key", "value")
        
        last_item = memory.memory['command_history'][-1]
        assert 'timestamp' in last_item
    
    def test_remember_limits_history(self, tmp_path):
        """Test history is limited to 100 items."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        
        # Add more than 100 items
        for i in range(110):
            memory.remember("key", f"value{i}")
        
        assert len(memory.memory['command_history']) <= 100


class TestRememberMessage:
    """Tests for remember_message compatibility method."""
    
    def test_remember_message(self, tmp_path):
        """Test remember_message wrapper."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        memory.remember_message("user", "Hello there")
        
        last_item = memory.memory['command_history'][-1]
        assert last_item['key'] == 'chat_message'
        assert last_item['value']['role'] == 'user'
        assert last_item['value']['content'] == 'Hello there'
    
    def test_remember_message_with_meta(self, tmp_path):
        """Test remember_message with metadata."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        memory.remember_message("assistant", "Response", meta={'model': 'gemini'})
        
        last_item = memory.memory['command_history'][-1]
        assert last_item['value']['meta']['model'] == 'gemini'


class TestRecall:
    """Tests for recall functionality."""
    
    def test_recall_single(self, tmp_path):
        """Test recalling single item."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        memory.remember("query", "What is Python?")
        
        results = memory.recall("query", limit=5)
        assert len(results) == 1
        assert results[0] == "What is Python?"
    
    def test_recall_multiple(self, tmp_path):
        """Test recalling multiple items."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        memory.remember("query", "First")
        memory.remember("query", "Second")
        memory.remember("query", "Third")
        
        results = memory.recall("query", limit=5)
        assert len(results) == 3
        # Most recent first
        assert results[0] == "Third"
    
    def test_recall_with_limit(self, tmp_path):
        """Test recall with limit."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        for i in range(10):
            memory.remember("query", f"Item {i}")
        
        results = memory.recall("query", limit=3)
        assert len(results) == 3
    
    def test_recall_nonexistent(self, tmp_path):
        """Test recalling non-existent key."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        
        results = memory.recall("nonexistent", limit=5)
        assert len(results) == 0


class TestGetLast:
    """Tests for get_last functionality."""
    
    def test_get_last_exists(self, tmp_path):
        """Test getting last value when exists."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        memory.remember("key", "first")
        memory.remember("key", "second")
        memory.remember("key", "last")
        
        result = memory.get_last("key")
        assert result == "last"
    
    def test_get_last_nonexistent(self, tmp_path):
        """Test getting last value when doesn't exist."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        
        result = memory.get_last("nonexistent")
        assert result is None


class TestSetPreference:
    """Tests for preference setting."""
    
    def test_set_preference(self, tmp_path):
        """Test setting a preference."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        memory.set_preference("theme", "dark")
        
        assert memory.memory['preferences']['theme']['value'] == "dark"
    
    def test_set_preference_with_timestamp(self, tmp_path):
        """Test preference includes timestamp."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        memory.set_preference("volume", 80)
        
        assert 'set_at' in memory.memory['preferences']['volume']
    
    def test_set_preference_overwrites(self, tmp_path):
        """Test setting preference overwrites previous."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        memory.set_preference("key", "old")
        memory.set_preference("key", "new")
        
        assert memory.memory['preferences']['key']['value'] == "new"


class TestPersistence:
    """Tests for persistence."""
    
    def test_save_creates_file(self, tmp_path):
        """Test that save creates memory file."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        memory.remember("test", "value")
        
        assert (tmp_path / 'lada_memory.pkl').exists()
    
    def test_load_existing_memory(self, tmp_path):
        """Test loading existing memory."""
        from modules import memory_system as ms
        
        # Create and save memory
        memory1 = ms.MemorySystem(data_dir=str(tmp_path))
        memory1.remember("saved_key", "saved_value")
        
        # Load in new instance
        memory2 = ms.MemorySystem(data_dir=str(tmp_path))
        results = memory2.recall("saved_key", limit=5)
        
        assert len(results) == 1
        assert results[0] == "saved_value"


class TestMemoryStructure:
    """Tests for memory structure."""
    
    def test_default_user_name(self, tmp_path):
        """Test default user name."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        assert memory.memory['user_name'] == 'Sir'
    
    def test_has_created_at(self, tmp_path):
        """Test memory has creation timestamp."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        assert 'created_at' in memory.memory
    
    def test_has_last_updated(self, tmp_path):
        """Test memory has last updated timestamp."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        assert 'last_updated' in memory.memory
    
    def test_has_routines(self, tmp_path):
        """Test memory has routines dict."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        assert 'routines' in memory.memory
        assert isinstance(memory.memory['routines'], dict)
    
    def test_has_learned_responses(self, tmp_path):
        """Test memory has learned_responses dict."""
        from modules import memory_system as ms
        memory = ms.MemorySystem(data_dir=str(tmp_path))
        assert 'learned_responses' in memory.memory
        assert isinstance(memory.memory['learned_responses'], dict)
