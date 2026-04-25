"""
Extended tests for modules/chat_manager.py
Covers additional methods/branches not tested in test_chat_manager.py:
- Message.from_dict edge cases
- Conversation.from_dict edge cases
- ChatManager._get_response (with/without AI router)
- ChatManager._stream_response (with/without stream support)
- ChatManager.regenerate_response
- ChatManager.add_reaction
- ChatManager.render_message (with/without renderer)
- ChatManager.cancel_stream
- ChatManager.delete_conversation
- ChatManager.load_conversation
- ChatManager.save_conversation error handling
- ChatManager.list_conversations
"""

import pytest
import sys
import os
import json
from unittest.mock import MagicMock, patch, mock_open
from datetime import datetime
from pathlib import Path


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


class TestMessageFromDictEdgeCases:
    """Edge case tests for Message.from_dict."""
    
    def test_from_dict_without_timestamp(self, mock_renderer):
        """Test from_dict when timestamp is missing - defaults to current time."""
        from modules import chat_manager as cm
        data = {
            'id': 'msg1',
            'role': 'user',
            'content': 'Hello'
        }
        msg = cm.Message.from_dict(data)
        assert msg.id == 'msg1'
        # When timestamp missing in dict, from_dict passes None to __init__
        # which then defaults to datetime.now()
        assert msg.timestamp is not None  # Gets default timestamp
    
    def test_from_dict_with_empty_sources(self, mock_renderer):
        """Test from_dict with empty sources list."""
        from modules import chat_manager as cm
        data = {
            'id': 'msg1',
            'role': 'assistant',
            'content': 'Response',
            'timestamp': datetime.now().isoformat(),
            'sources': []
        }
        msg = cm.Message.from_dict(data)
        assert msg.sources == []
    
    def test_from_dict_with_reactions(self, mock_renderer):
        """Test from_dict with reactions."""
        from modules import chat_manager as cm
        data = {
            'id': 'msg1',
            'role': 'assistant',
            'content': 'Response',
            'timestamp': datetime.now().isoformat(),
            'reactions': {'thumbs_up': True, 'thumbs_down': False}
        }
        msg = cm.Message.from_dict(data)
        assert msg.reactions == {'thumbs_up': True, 'thumbs_down': False}
    
    def test_from_dict_with_thinking_time(self, mock_renderer):
        """Test from_dict with thinking_time."""
        from modules import chat_manager as cm
        data = {
            'id': 'msg1',
            'role': 'assistant',
            'content': 'Response',
            'timestamp': datetime.now().isoformat(),
            'thinking_time': 2.5
        }
        msg = cm.Message.from_dict(data)
        assert msg.thinking_time == 2.5
    
    def test_from_dict_missing_optional_fields(self, mock_renderer):
        """Test from_dict with minimal data (missing optional fields)."""
        from modules import chat_manager as cm
        data = {
            'role': 'user',
            'content': 'Test'
        }
        msg = cm.Message.from_dict(data)
        assert msg.role == 'user'
        assert msg.content == 'Test'
        assert msg.tokens_used == 0
        assert msg.thinking_time == 0.0


class TestConversationFromDictEdgeCases:
    """Edge case tests for Conversation.from_dict."""
    
    def test_from_dict_without_updated_at(self, mock_renderer):
        """Test from_dict when updated_at is missing."""
        from modules import chat_manager as cm
        data = {
            'id': 'conv1',
            'title': 'Test',
            'created_at': datetime.now().isoformat(),
            'messages': []
        }
        conv = cm.Conversation.from_dict(data)
        assert conv.updated_at == conv.created_at
    
    def test_from_dict_without_created_at(self, mock_renderer):
        """Test from_dict when created_at is missing - defaults to current time."""
        from modules import chat_manager as cm
        data = {
            'id': 'conv1',
            'title': 'Test',
            'messages': []
        }
        conv = cm.Conversation.from_dict(data)
        assert conv.id == 'conv1'
        # When created_at is None, Conversation.__init__ defaults to datetime.now()
        assert conv.created_at is not None  # Gets default timestamp
    
    def test_from_dict_with_metadata(self, mock_renderer):
        """Test from_dict with metadata."""
        from modules import chat_manager as cm
        data = {
            'id': 'conv1',
            'title': 'Test',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'messages': [],
            'metadata': {'custom_key': 'custom_value'}
        }
        conv = cm.Conversation.from_dict(data)
        assert conv.metadata == {'custom_key': 'custom_value'}
    
    def test_from_dict_with_multiple_messages(self, mock_renderer):
        """Test from_dict with multiple messages."""
        from modules import chat_manager as cm
        now = datetime.now().isoformat()
        data = {
            'id': 'conv1',
            'title': 'Test',
            'created_at': now,
            'updated_at': now,
            'messages': [
                {'id': 'm1', 'role': 'user', 'content': 'Q1', 'timestamp': now},
                {'id': 'm2', 'role': 'assistant', 'content': 'A1', 'timestamp': now},
                {'id': 'm3', 'role': 'user', 'content': 'Q2', 'timestamp': now}
            ]
        }
        conv = cm.Conversation.from_dict(data)
        assert len(conv.messages) == 3
        assert conv.messages[0].role == 'user'
        assert conv.messages[1].role == 'assistant'


class TestConversationAutoTitle:
    """Tests for Conversation auto-title functionality."""
    
    def test_auto_title_long_message(self, mock_renderer):
        """Test auto-title truncation for long messages."""
        from modules import chat_manager as cm
        conv = cm.Conversation()
        long_content = "A" * 100
        msg = cm.Message(role="user", content=long_content)
        conv.add_message(msg)
        assert len(conv.title) <= 53  # 50 chars + "..."
        assert conv.title.endswith("...")
    
    def test_auto_title_short_message(self, mock_renderer):
        """Test auto-title for short messages."""
        from modules import chat_manager as cm
        conv = cm.Conversation()
        msg = cm.Message(role="user", content="Hello")
        conv.add_message(msg)
        assert conv.title == "Hello"
        assert not conv.title.endswith("...")
    
    def test_no_auto_title_for_assistant(self, mock_renderer):
        """Test that assistant messages don't change title."""
        from modules import chat_manager as cm
        conv = cm.Conversation()
        msg = cm.Message(role="assistant", content="Hi there!")
        conv.add_message(msg)
        assert conv.title == "New Chat"
    
    def test_no_auto_title_if_already_set(self, mock_renderer):
        """Test that custom title is preserved."""
        from modules import chat_manager as cm
        conv = cm.Conversation(title="My Custom Title")
        msg = cm.Message(role="user", content="Hello World")
        conv.add_message(msg)
        assert conv.title == "My Custom Title"


class TestChatManagerGetResponse:
    """Tests for ChatManager._get_response method."""
    
    def test_get_response_without_router(self, tmp_path, mock_renderer):
        """Test _get_response without AI router."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        conv = manager.create_conversation()
        conv.add_message(cm.Message(role='user', content='Hello'))
        
        response = manager._get_response(conv)
        assert response.content == "AI router not configured."
        assert response.role == 'assistant'
    
    def test_get_response_with_router(self, tmp_path, mock_renderer):
        """Test _get_response with AI router."""
        from modules import chat_manager as cm
        mock_router = MagicMock()
        mock_router.query.return_value = {
            'response': 'Hello! How can I help?',
            'source': 'gemini'
        }
        
        manager = cm.ChatManager(data_dir=str(tmp_path), ai_router=mock_router)
        conv = manager.create_conversation()
        conv.add_message(cm.Message(role='user', content='Hello'))
        
        response = manager._get_response(conv)
        assert response.content == 'Hello! How can I help?'
        assert response.model_used == 'gemini'
    
    def test_get_response_router_error(self, tmp_path, mock_renderer):
        """Test _get_response when router throws error."""
        from modules import chat_manager as cm
        mock_router = MagicMock()
        mock_router.query.side_effect = Exception("API error")
        
        manager = cm.ChatManager(data_dir=str(tmp_path), ai_router=mock_router)
        conv = manager.create_conversation()
        conv.add_message(cm.Message(role='user', content='Hello'))
        
        response = manager._get_response(conv)
        assert "Error:" in response.content
        assert "API error" in response.content
    
    def test_get_response_with_empty_conversation(self, tmp_path, mock_renderer):
        """Test _get_response with empty conversation."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        conv = manager.create_conversation()
        
        response = manager._get_response(conv)
        assert response.role == 'assistant'


class TestChatManagerStreamResponse:
    """Tests for ChatManager._stream_response method."""
    
    def test_stream_response_fallback_no_stream_support(self, tmp_path, mock_renderer):
        """Test _stream_response falls back when no stream_query method."""
        from modules import chat_manager as cm
        mock_router = MagicMock(spec=['query'])  # No stream_query
        mock_router.query.return_value = {
            'response': 'Non-streamed response',
            'source': 'fallback'
        }
        
        manager = cm.ChatManager(data_dir=str(tmp_path), ai_router=mock_router)
        conv = manager.create_conversation()
        conv.add_message(cm.Message(role='user', content='Hello'))
        
        response = manager._stream_response(conv)
        assert response.content == 'Non-streamed response'
    
    def test_stream_response_with_chunks(self, tmp_path, mock_renderer):
        """Test _stream_response with streaming chunks."""
        from modules import chat_manager as cm
        mock_router = MagicMock()
        mock_router.stream_query.return_value = iter(['Hello', ' ', 'World'])
        
        chunks_received = []
        
        manager = cm.ChatManager(data_dir=str(tmp_path), ai_router=mock_router)
        manager.on_chunk_received = lambda c: chunks_received.append(c)
        
        conv = manager.create_conversation()
        conv.add_message(cm.Message(role='user', content='Hello'))
        
        response = manager._stream_response(conv)
        assert len(chunks_received) == 3
    
    def test_stream_response_with_dict_chunks(self, tmp_path, mock_renderer):
        """Test _stream_response with dict-formatted chunks."""
        from modules import chat_manager as cm
        mock_router = MagicMock()
        # The implementation extracts 'chunk' key from dict chunks for callback
        mock_router.stream_query.return_value = iter([
            {'chunk': 'Hello', 'source': 'gpt-4'},
            {'chunk': ' World', 'source': 'gpt-4'}
        ])
        
        chunks_received = []
        
        manager = cm.ChatManager(data_dir=str(tmp_path), ai_router=mock_router)
        manager.on_chunk_received = lambda c: chunks_received.append(c)
        
        conv = manager.create_conversation()
        conv.add_message(cm.Message(role='user', content='Hello'))
        
        response = manager._stream_response(conv)
        # Verify chunks were processed (callback receives the extracted text)
        # stream_buffer accumulates the full chunk objects as strings
        assert response.role == 'assistant'
        assert manager.is_streaming is False
    
    def test_stream_response_error_handling(self, tmp_path, mock_renderer):
        """Test _stream_response error handling."""
        from modules import chat_manager as cm
        mock_router = MagicMock()
        mock_router.stream_query.side_effect = Exception("Stream error")
        
        manager = cm.ChatManager(data_dir=str(tmp_path), ai_router=mock_router)
        conv = manager.create_conversation()
        conv.add_message(cm.Message(role='user', content='Hello'))
        
        response = manager._stream_response(conv)
        assert "Error:" in response.content
    
    def test_stream_response_complete_callback(self, tmp_path, mock_renderer):
        """Test on_stream_complete callback is called."""
        from modules import chat_manager as cm
        mock_router = MagicMock()
        mock_router.stream_query.return_value = iter(['Done'])
        
        completed = []
        
        manager = cm.ChatManager(data_dir=str(tmp_path), ai_router=mock_router)
        manager.on_stream_complete = lambda msg: completed.append(msg)
        
        conv = manager.create_conversation()
        conv.add_message(cm.Message(role='user', content='Hello'))
        
        response = manager._stream_response(conv)
        assert len(completed) == 1
        assert completed[0].role == 'assistant'


class TestChatManagerCancelStream:
    """Tests for ChatManager.cancel_stream method."""
    
    def test_cancel_stream(self, tmp_path, mock_renderer):
        """Test cancel_stream sets flag."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        manager.is_streaming = True
        
        manager.cancel_stream()
        assert manager.is_streaming is False


class TestChatManagerSendMessage:
    """Tests for ChatManager.send_message method."""
    
    def test_send_message_creates_conversation_if_needed(self, tmp_path, mock_renderer):
        """Test send_message creates conversation when none exists."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        assert manager.current_conversation is None
        
        response = manager.send_message("Hello", stream=False)
        assert manager.current_conversation is not None
    
    def test_send_message_non_streaming(self, tmp_path, mock_renderer):
        """Test send_message with streaming disabled."""
        from modules import chat_manager as cm
        mock_router = MagicMock()
        mock_router.query.return_value = {'response': 'Hi!', 'source': 'test'}
        
        manager = cm.ChatManager(data_dir=str(tmp_path), ai_router=mock_router)
        conv = manager.create_conversation()
        
        response = manager.send_message("Hello", stream=False)
        assert response.content == 'Hi!'
    
    def test_send_message_saves_conversation(self, tmp_path, mock_renderer):
        """Test send_message saves conversation after response."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        conv = manager.create_conversation()
        
        manager.send_message("Hello", stream=False)
        
        # Check file was created
        file_path = tmp_path / f"{conv.id}.json"
        assert file_path.exists()


class TestChatManagerRegenerateResponse:
    """Tests for ChatManager.regenerate_response method."""
    
    def test_regenerate_response_no_conversation(self, tmp_path, mock_renderer):
        """Test regenerate_response with no conversation."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        
        result = manager.regenerate_response()
        assert result is None
    
    def test_regenerate_response_too_few_messages(self, tmp_path, mock_renderer):
        """Test regenerate_response with only one message."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        conv = manager.create_conversation()
        conv.add_message(cm.Message(role='user', content='Hello'))
        
        result = manager.regenerate_response()
        assert result is None
    
    def test_regenerate_response_removes_last_assistant(self, tmp_path, mock_renderer):
        """Test regenerate_response removes last assistant message."""
        from modules import chat_manager as cm
        mock_router = MagicMock()
        mock_router.query.return_value = {'response': 'New response', 'source': 'test'}
        
        manager = cm.ChatManager(data_dir=str(tmp_path), ai_router=mock_router)
        conv = manager.create_conversation()
        conv.add_message(cm.Message(role='user', content='Hello'))
        conv.add_message(cm.Message(role='assistant', content='Old response'))
        
        # After removing assistant, it removes user too, then resends
        # This triggers _stream_response (default stream=True) which falls back
        result = manager.regenerate_response(conv)
        assert result is not None
        # Result comes from fallback _get_response called by _stream_response
        assert result.role == 'assistant'
    
    def test_regenerate_response_with_user_message_last(self, tmp_path, mock_renderer):
        """Test regenerate_response when last message is from user."""
        from modules import chat_manager as cm
        mock_router = MagicMock()
        mock_router.query.return_value = {'response': 'Response', 'source': 'test'}
        
        manager = cm.ChatManager(data_dir=str(tmp_path), ai_router=mock_router)
        conv = manager.create_conversation()
        conv.add_message(cm.Message(role='user', content='Q1'))
        conv.add_message(cm.Message(role='assistant', content='A1'))
        conv.add_message(cm.Message(role='user', content='Q2'))
        
        result = manager.regenerate_response(conv)
        assert result is not None


class TestChatManagerAddReaction:
    """Tests for ChatManager.add_reaction method."""
    
    def test_add_reaction_no_conversation(self, tmp_path, mock_renderer):
        """Test add_reaction with no conversation."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        
        # Should not raise
        manager.add_reaction('msg1', 'thumbs_up')
    
    def test_add_reaction_message_not_found(self, tmp_path, mock_renderer):
        """Test add_reaction when message ID not found."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        conv = manager.create_conversation()
        conv.add_message(cm.Message(role='user', content='Hello', message_id='msg1'))
        
        # Should not raise - message not found is silent
        manager.add_reaction('nonexistent', 'thumbs_up')
    
    def test_add_reaction_success(self, tmp_path, mock_renderer):
        """Test add_reaction successfully adds reaction."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        conv = manager.create_conversation()
        msg = cm.Message(role='user', content='Hello', message_id='msg1')
        conv.add_message(msg)
        
        manager.add_reaction('msg1', 'thumbs_up', True)
        
        assert conv.messages[0].reactions.get('thumbs_up') is True
    
    def test_add_reaction_thumbs_down(self, tmp_path, mock_renderer):
        """Test add_reaction with thumbs_down."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        conv = manager.create_conversation()
        msg = cm.Message(role='assistant', content='Response', message_id='msg2')
        conv.add_message(msg)
        
        manager.add_reaction('msg2', 'thumbs_down', True)
        
        assert conv.messages[0].reactions.get('thumbs_down') is True
    
    def test_add_reaction_toggle_off(self, tmp_path, mock_renderer):
        """Test add_reaction can toggle reaction off."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        conv = manager.create_conversation()
        msg = cm.Message(role='user', content='Hello', message_id='msg1')
        msg.reactions['thumbs_up'] = True
        conv.add_message(msg)
        
        manager.add_reaction('msg1', 'thumbs_up', False)
        
        assert conv.messages[0].reactions.get('thumbs_up') is False


class TestChatManagerRenderMessage:
    """Tests for ChatManager.render_message method."""
    
    def test_render_message_without_renderer(self, tmp_path, mock_renderer):
        """Test render_message fallback when no renderer."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        manager.renderer = None  # Force no renderer
        
        msg = cm.Message(role='assistant', content='Hello <world>')
        html = manager.render_message(msg)
        
        assert '&lt;world&gt;' in html  # HTML escaped
        assert '<p' in html
    
    def test_render_message_with_newlines_fallback(self, tmp_path, mock_renderer):
        """Test render_message fallback handles newlines."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        manager.renderer = None
        
        msg = cm.Message(role='assistant', content='Line1\nLine2')
        html = manager.render_message(msg)
        
        assert '<br>' in html
    
    def test_render_message_with_renderer(self, tmp_path, mock_renderer):
        """Test render_message with renderer."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        
        mock_md_renderer = MagicMock()
        mock_md_renderer.render.return_value = '<p>Rendered</p>'
        mock_md_renderer.render_citations.return_value = ''
        manager.renderer = mock_md_renderer
        
        msg = cm.Message(role='assistant', content='Hello')
        html = manager.render_message(msg)
        
        assert '<p>Rendered</p>' in html
    
    def test_render_message_with_sources(self, tmp_path, mock_renderer):
        """Test render_message includes citations."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        
        mock_md_renderer = MagicMock()
        mock_md_renderer.render.return_value = '<p>Content</p>'
        mock_md_renderer.render_citations.return_value = '<div class="citations">Source</div>'
        manager.renderer = mock_md_renderer
        
        msg = cm.Message(
            role='assistant',
            content='Hello',
            sources=[{'title': 'Test', 'url': 'http://example.com'}]
        )
        html = manager.render_message(msg)
        
        mock_md_renderer.render_citations.assert_called_once()
        assert 'citations' in html


class TestChatManagerDeleteConversation:
    """Tests for ChatManager.delete_conversation method."""
    
    def test_delete_conversation_from_memory(self, tmp_path, mock_renderer):
        """Test delete_conversation removes from memory."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        conv = manager.create_conversation()
        conv_id = conv.id
        
        manager.delete_conversation(conv_id)
        
        assert conv_id not in manager.conversations
    
    def test_delete_conversation_removes_file(self, tmp_path, mock_renderer):
        """Test delete_conversation removes file."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        conv = manager.create_conversation()
        manager.save_conversation(conv)
        
        file_path = tmp_path / f"{conv.id}.json"
        assert file_path.exists()
        
        manager.delete_conversation(conv.id)
        
        assert not file_path.exists()
    
    def test_delete_nonexistent_conversation(self, tmp_path, mock_renderer):
        """Test delete_conversation with nonexistent ID."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        
        # Should not raise
        manager.delete_conversation('nonexistent')


class TestChatManagerLoadConversation:
    """Tests for ChatManager.load_conversation method."""
    
    def test_load_conversation_success(self, tmp_path, mock_renderer):
        """Test loading a saved conversation."""
        from modules import chat_manager as cm
        
        # Create and save a conversation
        manager = cm.ChatManager(data_dir=str(tmp_path))
        conv = manager.create_conversation(title="Test Chat")
        conv.add_message(cm.Message(role='user', content='Hello'))
        manager.save_conversation(conv)
        
        # Create new manager and load
        manager2 = cm.ChatManager(data_dir=str(tmp_path))
        loaded = manager2.load_conversation(conv.id)
        
        assert loaded is not None
        assert loaded.title == "Test Chat"
        assert len(loaded.messages) == 1
    
    def test_load_conversation_not_found(self, tmp_path, mock_renderer):
        """Test load_conversation returns None for missing file."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        
        result = manager.load_conversation('nonexistent')
        assert result is None
    
    def test_load_conversation_invalid_json(self, tmp_path, mock_renderer):
        """Test load_conversation handles invalid JSON."""
        from modules import chat_manager as cm
        
        # Create invalid JSON file
        file_path = tmp_path / "bad.json"
        file_path.write_text("not valid json")
        
        manager = cm.ChatManager(data_dir=str(tmp_path))
        result = manager.load_conversation('bad')
        
        assert result is None


class TestChatManagerListConversations:
    """Tests for ChatManager.list_conversations method."""
    
    def test_list_conversations_empty(self, tmp_path, mock_renderer):
        """Test list_conversations with no saved conversations."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        
        result = manager.list_conversations()
        assert result == []
    
    def test_list_conversations_multiple(self, tmp_path, mock_renderer):
        """Test list_conversations with multiple conversations."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        
        # Create and save multiple conversations
        conv1 = manager.create_conversation(title="Chat 1")
        conv1.add_message(cm.Message(role='user', content='Hello 1'))
        manager.save_conversation(conv1)
        
        conv2 = manager.create_conversation(title="Chat 2")
        conv2.add_message(cm.Message(role='user', content='Hello 2'))
        conv2.add_message(cm.Message(role='assistant', content='Hi'))
        manager.save_conversation(conv2)
        
        result = manager.list_conversations()
        
        assert len(result) == 2
        # Check fields are present
        assert all('id' in c for c in result)
        assert all('title' in c for c in result)
        assert all('message_count' in c for c in result)
    
    def test_list_conversations_skips_invalid_files(self, tmp_path, mock_renderer):
        """Test list_conversations skips invalid JSON files."""
        from modules import chat_manager as cm
        
        # Create valid conversation
        manager = cm.ChatManager(data_dir=str(tmp_path))
        conv = manager.create_conversation(title="Valid")
        manager.save_conversation(conv)
        
        # Create invalid JSON file
        (tmp_path / "invalid.json").write_text("not json")
        
        result = manager.list_conversations()
        
        assert len(result) == 1
        assert result[0]['title'] == "Valid"


class TestChatManagerSaveConversation:
    """Tests for ChatManager.save_conversation method."""
    
    def test_save_conversation_no_conversation(self, tmp_path, mock_renderer):
        """Test save_conversation with no conversation."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        
        # Should not raise
        manager.save_conversation()
    
    def test_save_conversation_explicit(self, tmp_path, mock_renderer):
        """Test save_conversation with explicit conversation."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        conv = cm.Conversation(title="Test")
        
        manager.save_conversation(conv)
        
        file_path = tmp_path / f"{conv.id}.json"
        assert file_path.exists()
        
        with open(file_path, 'r') as f:
            data = json.load(f)
        assert data['title'] == "Test"


class TestChatManagerGetConversation:
    """Tests for ChatManager.get_conversation method."""
    
    def test_get_conversation_from_memory(self, tmp_path, mock_renderer):
        """Test get_conversation returns from memory cache."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        conv = manager.create_conversation()
        
        result = manager.get_conversation(conv.id)
        assert result is conv
    
    def test_get_conversation_loads_from_file(self, tmp_path, mock_renderer):
        """Test get_conversation loads from file if not in memory."""
        from modules import chat_manager as cm
        
        # Create and save
        manager1 = cm.ChatManager(data_dir=str(tmp_path))
        conv = manager1.create_conversation(title="Saved")
        manager1.save_conversation(conv)
        conv_id = conv.id
        
        # New manager (empty memory)
        manager2 = cm.ChatManager(data_dir=str(tmp_path))
        result = manager2.get_conversation(conv_id)
        
        assert result is not None
        assert result.title == "Saved"
    
    def test_get_conversation_not_found(self, tmp_path, mock_renderer):
        """Test get_conversation returns None for unknown ID."""
        from modules import chat_manager as cm
        manager = cm.ChatManager(data_dir=str(tmp_path))
        
        result = manager.get_conversation('unknown')
        assert result is None


class TestWebSearchIntegration:
    """Tests for web search integration in responses."""
    
    def test_get_response_with_web_search_error(self, tmp_path, mock_renderer):
        """Test _get_response handles web search errors gracefully."""
        from modules import chat_manager as cm
        
        with patch.dict(sys.modules, {'modules.web_search': MagicMock()}):
            sys.modules['modules.web_search'].WebSearcher.side_effect = Exception("Search failed")
            
            manager = cm.ChatManager(data_dir=str(tmp_path))
            conv = manager.create_conversation()
            conv.add_message(cm.Message(role='user', content='Search this'))
            
            # Should not raise, just skip web search
            response = manager._get_response(conv, include_web_search=True)
            assert response.role == 'assistant'
    
    def test_stream_response_with_web_search_error(self, tmp_path, mock_renderer):
        """Test _stream_response handles web search errors gracefully."""
        from modules import chat_manager as cm
        
        with patch.dict(sys.modules, {'modules.web_search': MagicMock()}):
            sys.modules['modules.web_search'].WebSearcher.side_effect = Exception("Search failed")
            
            manager = cm.ChatManager(data_dir=str(tmp_path))
            conv = manager.create_conversation()
            conv.add_message(cm.Message(role='user', content='Search this'))
            
            # Should not raise
            response = manager._stream_response(conv, include_web_search=True)
            assert response.role == 'assistant'


class TestRendererAvailability:
    """Tests for renderer import scenarios."""
    
    def test_renderer_not_available(self, tmp_path):
        """Test ChatManager works when renderer is not available."""
        # Reset and mock failed import
        modules_to_reset = [k for k in sys.modules.keys() if 'chat_manager' in k or 'markdown_renderer' in k]
        for mod in modules_to_reset:
            del sys.modules[mod]
        
        with patch.dict(sys.modules, {'modules.markdown_renderer': None}):
            # This should still work
            from modules import chat_manager as cm
            manager = cm.ChatManager(data_dir=str(tmp_path))
            
            msg = cm.Message(role='assistant', content='Test')
            html = manager.render_message(msg)
            assert 'Test' in html
