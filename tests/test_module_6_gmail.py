import pytest
from unittest.mock import MagicMock, patch
import sys

# Inject mocks into module namespace
import modules.gmail_controller
modules.gmail_controller.build = MagicMock()
modules.gmail_controller.Credentials = MagicMock()
modules.gmail_controller.GOOGLE_API_OK = True

from modules.gmail_controller import GmailController

class TestGmailController:
    
    @pytest.fixture
    def controller(self):
        # Reset mocks
        modules.gmail_controller.build.reset_mock()
        modules.gmail_controller.Credentials.reset_mock()
        
        controller = GmailController()
        controller.service = modules.gmail_controller.build.return_value
        controller.user_email = "test@example.com"
        return controller

    def test_send_email(self, controller):
        """Test sending email"""
        # Mock service response
        controller.service.users().messages().send().execute.return_value = {
            "id": "msg123",
            "threadId": "thread123"
        }
        
        result = controller.send_email(
            to="recipient@example.com",
            subject="Test",
            body="Hello"
        )
        
        assert result["success"] is True
        assert result["message_id"] == "msg123"
        controller.service.users().messages().send.assert_called()

    def test_get_inbox(self, controller):
        """Test getting inbox"""
        # Mock list response
        controller.service.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg1"}, {"id": "msg2"}]
        }
        
        # Mock get details response
        mock_msg = {
            "id": "msg1",
            "threadId": "t1",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "me@example.com"},
                    {"name": "Date", "value": "Mon, 01 Jan 2024 10:00:00 +0000"}
                ]
            },
            "snippet": "Test snippet"
        }
        controller.service.users().messages().get().execute.return_value = mock_msg
        
        result = controller.get_inbox(max_results=2)
        
        assert result["success"] is True
        assert result["count"] == 2
        assert len(result["messages"]) == 2

    def test_search_emails(self, controller):
        """Test searching emails"""
        controller.service.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg1"}]
        }
        controller.service.users().messages().get().execute.return_value = {
            "id": "msg1",
            "threadId": "t1",
            "payload": {"headers": []}
        }
        
        result = controller.search_emails("subject:test")
        
        assert result["success"] is True
        assert result["query"] == "subject:test"
        controller.service.users().messages().list.assert_called_with(
            userId="me", q="subject:test", maxResults=10
        )

    def test_get_email(self, controller):
        """Test getting specific email"""
        mock_msg = {
            "id": "msg1",
            "threadId": "t1",
            "payload": {
                "headers": [{"name": "Subject", "value": "Test"}],
                "body": {"data": "SGVsbG8="} # Base64 "Hello"
            }
        }
        controller.service.users().messages().get().execute.return_value = mock_msg
        
        result = controller.get_email("msg1")
        
        assert result["success"] is True
        assert result["email"]["subject"] == "Test"
        assert result["email"]["body"] == "Hello"

    def test_mark_as_read(self, controller):
        """Test marking email as read"""
        controller.service.users().messages().modify().execute.return_value = {
            "id": "msg1",
            "labelIds": []
        }
        
        result = controller.mark_as_read("msg1")
        
        assert result["success"] is True
        controller.service.users().messages().modify.assert_called_with(
            userId="me", id="msg1", body={"removeLabelIds": ["UNREAD"]}
        )

    def test_trash_email(self, controller):
        """Test trashing email"""
        controller.service.users().messages().trash().execute.return_value = {
            "id": "msg1"
        }
        
        result = controller.trash_email("msg1")
        
        assert result["success"] is True
        controller.service.users().messages().trash.assert_called_with(
            userId="me", id="msg1"
        )
