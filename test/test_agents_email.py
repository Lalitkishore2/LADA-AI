"""
LADA v9.0 - Email Agent Tests
Comprehensive tests for EmailAgent - Target: 80%+ coverage
"""

import pytest
from unittest.mock import MagicMock, patch, mock_open
import base64
import sys


@pytest.fixture(autouse=True)
def mock_google_modules():
    """Mock Google API modules before importing EmailAgent."""
    modules_to_mock = [
        'google.oauth2.credentials',
        'google_auth_oauthlib.flow',
        'google.auth.transport.requests',
        'googleapiclient.discovery',
        'googleapiclient'
    ]
    
    for mod in modules_to_mock:
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()
    
    yield


class TestEmailAgentInit:
    """Test EmailAgent initialization."""
    
    def test_init_default(self):
        """Test default initialization."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        
        assert agent.service is None
        assert agent._auth_attempted is False
        assert agent.initialized is False
    
    def test_init_custom_path(self):
        """Test initialization with custom credentials."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent(credentials_path='custom/creds.json')
        
        assert 'custom' in str(agent.credentials_path)


class TestEmailEnsureAuthenticated:
    """Test _ensure_authenticated for EmailAgent."""
    
    def test_already_authenticated(self):
        """Test when already authenticated."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = True
        
        result = agent._ensure_authenticated()
        assert result is True
    
    def test_auth_already_attempted(self):
        """Test when auth already attempted."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent._auth_attempted = True
        
        result = agent._ensure_authenticated()
        assert result is False
    
    def test_no_credentials(self):
        """Test when no credentials file."""
        from modules.agents.email_agent import EmailAgent
        from pathlib import Path
        
        agent = EmailAgent()
        
        # Use a non-existent path directly
        agent.credentials_path = Path('/nonexistent/path/that/does/not/exist.json')
        
        result = agent._ensure_authenticated()
        
        # Should return False when credentials don't exist
        assert result is False


class TestDraftEmail:
    """Test draft_email method."""
    
    def test_draft_email_success(self):
        """Test successful email draft creation."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = True
        agent.service = MagicMock()
        
        mock_draft = {'id': 'draft123'}
        agent.service.users().drafts().create().execute.return_value = mock_draft
        
        result = agent.draft_email(
            to='test@example.com',
            subject='Test Subject',
            body='Test body content'
        )
        
        assert result['success'] is True
        assert result['draft_id'] == 'draft123'
    
    def test_draft_email_not_initialized(self):
        """Test draft when not initialized."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = False
        
        result = agent.draft_email(
            to='test@example.com',
            subject='Test',
            body='Body'
        )
        
        # Returns a local draft when not initialized
        assert result['success'] is True
        assert 'local_draft' in result.get('type', '') or 'Draft' in result.get('message', '')
    
    def test_draft_email_with_cc_bcc(self):
        """Test draft with CC and BCC."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = True
        agent.service = MagicMock()
        
        mock_draft = {'id': 'draft456'}
        agent.service.users().drafts().create().execute.return_value = mock_draft
        
        result = agent.draft_email(
            to='main@example.com',
            subject='Test',
            body='Body',
            cc='cc@example.com',
            bcc='bcc@example.com'
        )
        
        assert result['success'] is True
    
    def test_draft_email_html(self):
        """Test draft with HTML body."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = True
        agent.service = MagicMock()
        
        mock_draft = {'id': 'draft789'}
        agent.service.users().drafts().create().execute.return_value = mock_draft
        
        result = agent.draft_email(
            to='test@example.com',
            subject='HTML Email',
            body='<h1>Hello</h1>',
            html=True
        )
        
        assert result['success'] is True
    
    def test_draft_email_api_exception(self):
        """Test draft when API throws exception."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = True
        agent.service = MagicMock()
        agent.service.users().drafts().create().execute.side_effect = Exception("API Error")
        
        result = agent.draft_email(
            to='test@example.com',
            subject='Test',
            body='Body'
        )
        
        assert result['success'] is True  # Falls back


class TestSendEmail:
    """Test send_email method."""
    
    def test_send_email_success(self):
        """Test successful email send."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = True
        agent.service = MagicMock()
        
        mock_response = {'id': 'msg123', 'labelIds': ['SENT']}
        agent.service.users().messages().send().execute.return_value = mock_response
        
        result = agent.send_email(
            to='test@example.com',
            subject='Test Subject',
            body='Test body content'
        )
        
        assert result['success'] is True
        assert result['message_id'] == 'msg123'
    
    def test_send_email_not_initialized(self):
        """Test send email when not initialized."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = False
        
        result = agent.send_email(
            to='test@example.com',
            subject='Test',
            body='Body'
        )
        
        assert result['success'] is False
        assert 'error' in result or 'fallback' in result
    
    def test_send_email_api_exception(self):
        """Test send when API throws exception."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = True
        agent.service = MagicMock()
        agent.service.users().messages().send().execute.side_effect = Exception("Send failed")
        
        result = agent.send_email(
            to='test@example.com',
            subject='Test',
            body='Body'
        )
        
        assert result['success'] is False
        assert 'error' in result


class TestCheckInbox:
    """Test check_inbox method."""
    
    def test_check_inbox_success(self):
        """Test checking inbox successfully."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = True
        agent.service = MagicMock()
        
        mock_list = {'messages': [{'id': 'msg1'}, {'id': 'msg2'}]}
        agent.service.users().messages().list().execute.return_value = mock_list
        
        mock_msg = {
            'id': 'msg1',
            'snippet': 'Test snippet',
            'labelIds': ['INBOX'],
            'payload': {
                'headers': [
                    {'name': 'From', 'value': 'sender@example.com'},
                    {'name': 'Subject', 'value': 'Test Subject'},
                    {'name': 'Date', 'value': '2026-01-03'}
                ]
            }
        }
        agent.service.users().messages().get().execute.return_value = mock_msg
        
        result = agent.check_inbox(max_results=5)
        
        assert result['success'] is True
        assert result['count'] == 2
    
    def test_check_inbox_unread_only(self):
        """Test checking only unread emails."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = True
        agent.service = MagicMock()
        
        mock_list = {'messages': [{'id': 'msg1'}]}
        agent.service.users().messages().list().execute.return_value = mock_list
        
        mock_msg = {
            'id': 'msg1',
            'snippet': 'Unread',
            'labelIds': ['INBOX', 'UNREAD'],
            'payload': {'headers': []}
        }
        agent.service.users().messages().get().execute.return_value = mock_msg
        
        result = agent.check_inbox(max_results=5, unread_only=True)
        
        assert result['success'] is True
    
    def test_check_inbox_with_query(self):
        """Test inbox with search query."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = True
        agent.service = MagicMock()
        
        mock_list = {'messages': []}
        agent.service.users().messages().list().execute.return_value = mock_list
        
        result = agent.check_inbox(query='from:boss@company.com')
        
        assert result['success'] is True
    
    def test_check_inbox_not_initialized(self):
        """Test inbox when not initialized."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = False
        
        result = agent.check_inbox()
        
        # Fallback returns success: False with explanation
        assert result['success'] is False
        assert 'Gmail API' in result['message']
    
    def test_check_inbox_api_exception(self):
        """Test inbox when API throws exception."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = True
        agent.service = MagicMock()
        agent.service.users().messages().list().execute.side_effect = Exception("API Error")
        
        result = agent.check_inbox()
        
        # Fallback returns success: False with explanation  
        assert result['success'] is False


class TestReplyToEmail:
    """Test reply_to_email method."""
    
    def test_reply_not_initialized(self):
        """Test reply when not initialized."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = False
        
        result = agent.reply_to_email(
            message_id='msg123',
            body='Thanks for your email!'
        )
        
        assert result['success'] is False
        assert 'error' in result


class TestCheckInboxViaQuery:
    """Test check_inbox with query parameter (as search)."""
    
    def test_check_inbox_with_search_query_success(self):
        """Test searching emails via check_inbox query param."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = True
        agent.service = MagicMock()
        
        mock_list = {'messages': [{'id': 'msg1'}]}
        agent.service.users().messages().list().execute.return_value = mock_list
        
        mock_msg = {
            'id': 'msg1',
            'snippet': 'Search result',
            'payload': {'headers': []}
        }
        agent.service.users().messages().get().execute.return_value = mock_msg
        
        result = agent.check_inbox(query='project update')
        
        assert result['success'] is True
    
    def test_check_inbox_query_not_initialized(self):
        """Test search query when not initialized."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = False
        
        result = agent.check_inbox(query='test query')
        
        # Falls back to error message
        assert result['success'] is False


class TestGenerateFallbackInbox:
    """Test _generate_fallback_inbox method."""
    
    def test_generate_fallback_inbox(self):
        """Test generating fallback inbox data."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        
        result = agent._generate_fallback_inbox()
        
        # Fallback returns success: False with explanation
        assert result['success'] is False
        assert 'Gmail API' in result['message']


class TestGenerateFallbackDraft:
    """Test _generate_fallback_draft method."""
    
    def test_generate_fallback_draft(self):
        """Test generating fallback draft."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        
        result = agent._generate_fallback_draft(
            to='test@example.com',
            subject='Test',
            body='Body',
            cc='cc@example.com',
            bcc=None
        )
        
        assert result['success'] is True
        assert result['to'] == 'test@example.com'
        assert result['subject'] == 'Test'


class TestProcess:
    """Test process method for EmailAgent."""
    
    def test_process_send_intent(self):
        """Test processing send intent."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = False
        
        result = agent.process('send email to john@example.com about meeting')
        
        assert 'success' in result
    
    def test_process_check_intent(self):
        """Test processing check/read intent."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = False
        
        result = agent.process('check my inbox')
        
        # When not initialized, check_inbox returns fallback with success: False
        assert result['success'] is False
    
    def test_process_search_intent(self):
        """Test processing search intent."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = False
        
        result = agent.process('search for emails about budget')
        
        # Search triggers check_inbox with query, falls back to success: False
        assert 'success' in result
    
    def test_process_draft_intent(self):
        """Test processing draft intent."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        agent.initialized = False
        
        result = agent.process('draft email to boss@company.com about update')
        
        assert 'success' in result


class TestLegacyAuthenticate:
    """Test legacy _authenticate method."""
    
    def test_authenticate_calls_ensure(self):
        """Test that _authenticate calls _ensure_authenticated."""
        from modules.agents.email_agent import EmailAgent
        agent = EmailAgent()
        
        with patch.object(agent, '_ensure_authenticated', return_value=True) as mock_ensure:
            result = agent._authenticate()
            mock_ensure.assert_called_once()
            assert result is True
