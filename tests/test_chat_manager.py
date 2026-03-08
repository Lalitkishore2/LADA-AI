"""
Tests for modules/chat_manager.py
Covers: Message, Conversation, ChatManager classes
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch, mock_open
from datetime import datetime
from pathlib import Path


# Reset module cache to ensure clean imports
@pytest.fixture(autouse=True)
def reset_modules():
    """Reset module cache before each test."""
    modules_to_reset = [k for k in sys.modules.keys() if 'chat_manager' in k or 'markdown_renderer' in k]
    for mod in modules_to_reset:
        del sys.modules[mod]
    yield


@pytest.fixture
def mock_renderer():
    """Mock the MarkdownRenderer."""
    with patch.dict(sys.modules, {'modules.markdown_renderer': MagicMock()}):
        yield


class TestMessage:
    """Tests for Message class."""
    
    def test_message_init_basic(self, mock_renderer):
        """Test basic message initialization."""
        from modules import chat_manager as cm
        msg = cm.Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.id is not None
        assert msg.timestamp is not None
    
    def test_message_init_with_id(self, mock_renderer):
        """Test message with custom ID."""
        from modules import chat_manager as cm
        msg = cm.Message(role="assistant", content="Hi", message_id="custom123")
        assert msg.id == "custom123"
    
    def test_message_init_with_metadata(self, mock_renderer):
        """Test message with all metadata."""
        from modules import chat_manager as cm
        ts = datetime.now()
        sources = [{"url": "http://example.com", "title": "Example"}]
        msg = cm.Message(
            role="assistant",
            content="Response",
            timestamp=ts,
            model_used="gemini",
            sources=sources,
            tokens_used=100,
            thinking_time=0.5
        )
        assert msg.model_used == "gemini"
        assert msg.sources == sources
        assert msg.tokens_used == 100
        assert msg.thinking_time == 0.5
    
    def test_message_to_dict(self, mock_renderer):
        """Test message serialization."""
        from modules import chat_manager as cm
        msg = cm.Message(role="user", content="Test", tokens_used=50)
        d = msg.to_dict()
        assert d['role'] == "user"
        assert d['content'] == "Test"
        assert 'id' in d
        assert 'timestamp' in d
        assert d['tokens_used'] == 50
    
    def test_message_from_dict(self, mock_renderer):
        """Test message deserialization."""
        from modules import chat_manager as cm
        data = {
            'id': 'msg1',
            'role': 'assistant',
            'content': 'Hi there',
            'timestamp': datetime.now().isoformat(),
            'model_used': 'gpt-4',
            'sources': [],
            'reactions': {'thumbs_up': True},
            'tokens_used': 25
        }
        msg = cm.Message.from_dict(data)
        assert msg.id == 'msg1'
        assert msg.role == 'assistant'
        assert msg.content == 'Hi there'
    
    def test_message_streaming_flag(self, mock_renderer):
        """Test streaming flag."""
        from modules import chat_manager as cm
        msg = cm.Message(role="assistant", content="", is_streaming=True)
        assert msg.is_streaming is True


class TestConversation:
    """Tests for Conversation class."""
    
    def test_conversation_init_default(self, mock_renderer):
        """Test default conversation initialization."""
        from modules import chat_manager as cm
        conv = cm.Conversation()
        assert conv.id is not None
        assert conv.title == "New Chat"
        assert len(conv.messages) == 0
    
    def test_conversation_init_with_title(self, mock_renderer):
        """Test conversation with custom title."""
        from modules import chat_manager as cm
        conv = cm.Conversation(title="My Chat")
        assert conv.title == "My Chat"
    
    def test_conversation_add_message(self, mock_renderer):
        """Test adding message to conversation."""
        from modules import chat_manager as cm
        conv = cm.Conversation()
        msg = cm.Message(role="user", content="Hello")
        conv.add_message(msg)
        assert len(conv.messages) == 1
        assert conv.messages[0].content == "Hello"
    
    def test_conversation_auto_title(self, mock_renderer):
        """Test auto-title from first user message."""
        from modules import chat_manager as cm
        conv = cm.Conversation()
        msg = cm.Message(role="user", content="How do I install Python?")
        conv.add_message(msg)
        # Title should be set from first user message
        assert "Python" in conv.title or "install" in conv.title.lower()
    
    def test_conversation_get_context(self, mock_renderer):
        """Test getting conversation context."""
        from modules import chat_manager as cm
        conv = cm.Conversation()
        conv.add_message(cm.Message(role="user", content="Q1"))
        conv.add_message(cm.Message(role="assistant", content="A1"))
        context = conv.get_context()
        assert len(context) == 2
        assert context[0]['role'] == 'user'
        assert context[1]['role'] == 'assistant'
    
    def test_conversation_get_context_max_messages(self, mock_renderer):
        """Test context limiting."""
        from modules import chat_manager as cm
        conv = cm.Conversation()
        for i in range(30):
            conv.add_message(cm.Message(role="user", content=f"Message {i}"))
        context = conv.get_context(max_messages=10)
        assert len(context) == 10
    
    def test_conversation_to_dict(self, mock_renderer):
        """Test conversation serialization."""
        from modules import chat_manager as cm
        conv = cm.Conversation(title="Test Chat")
        conv.add_message(cm.Message(role="user", content="Hello"))
        d = conv.to_dict()
        assert d['title'] == "Test Chat"
        assert 'messages' in d
        assert len(d['messages']) == 1
    
    def test_conversation_from_dict(self, mock_renderer):
        """Test conversation deserialization."""
        from modules import chat_manager as cm
        data = {
            'id': 'conv1',
            'title': 'Loaded Chat',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'messages': [
                {'id': 'm1', 'role': 'user', 'content': 'Hi', 'timestamp': datetime.now().isoformat()}
            ],
            'metadata': {}
        }
        conv = cm.Conversation.from_dict(data)
        assert conv.id == 'conv1'
        assert conv.title == 'Loaded Chat'
        assert len(conv.messages) == 1


class TestChatManager:
    """Tests for ChatManager class."""
    
    def test_init_default(self, tmp_path, mock_renderer):
        """Test default initialization."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        assert manager.data_dir == tmp_path
        assert manager.current_conversation is None
    
    def test_init_with_router(self, tmp_path, mock_renderer):
        """Test initialization with AI router."""
        from modules import chat_manager as cm
        mock_router = MagicMock()
        manager = cm.ChatManager(data_dir=str(tmp_path), ai_router=mock_router)
        assert manager.ai_router == mock_router
    
    def test_create_conversation(self, tmp_path, mock_renderer):
        """Test creating a new conversation."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        conv = manager.create_conversation(title="New Chat")
        assert conv is not None
        assert conv.title == "New Chat"
        assert manager.current_conversation == conv
    
    def test_get_conversation(self, tmp_path, mock_renderer):
        """Test getting a conversation."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        conv = manager.create_conversation()
        retrieved = manager.get_conversation(conv.id)
        assert retrieved == conv
    
    def test_streaming_state(self, tmp_path, mock_renderer):
        """Test streaming state flags."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        assert manager.is_streaming is False
        assert manager.stream_buffer == ""
    
    def test_callbacks_settable(self, tmp_path, mock_renderer):
        """Test that callbacks can be set."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        
        def on_chunk(chunk):
            pass
        
        manager.on_chunk_received = on_chunk
        assert manager.on_chunk_received == on_chunk
    
    def test_renderer_availability(self, tmp_path, mock_renderer):
        """Test renderer attribute."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        # Renderer may or may not be available
        assert hasattr(manager, 'renderer')


class TestMessageEdgeCases:
    """Edge case tests for Message class."""
    
    def test_message_empty_content(self, mock_renderer):
        """Test message with empty content."""
        from modules import chat_manager as cm
        msg = cm.Message(role="user", content="")
        assert msg.content == ""
    
    def test_message_unicode_content(self, mock_renderer):
        """Test message with unicode content."""
        from modules import chat_manager as cm
        msg = cm.Message(role="user", content="Hello 👋 世界")
        assert "👋" in msg.content
    
    def test_message_multiline_content(self, mock_renderer):
        """Test message with multiline content."""
        from modules import chat_manager as cm
        content = "Line 1\nLine 2\nLine 3"
        msg = cm.Message(role="user", content=content)
        assert "\n" in msg.content
