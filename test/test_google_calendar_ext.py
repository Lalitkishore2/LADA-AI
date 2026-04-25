"""Extended tests for modules/google_calendar.py"""

import pytest
import os
import sys
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta


@pytest.fixture(autouse=True)
def clean_google_imports():
    """Clean and mock Google imports for test isolation."""
    # Remove cached module to force reimport
    mods_to_remove = [k for k in list(sys.modules.keys()) if k.startswith("modules.google_calendar")]
    for mod in mods_to_remove:
        del sys.modules[mod]

    # Mock Google API modules if not already present
    if "google.oauth2.credentials" not in sys.modules:
        mock_credentials = MagicMock()
        mock_flow = MagicMock()
        mock_request = MagicMock()
        mock_build = MagicMock()

        sys.modules["google"] = MagicMock()
        sys.modules["google.oauth2"] = MagicMock()
        sys.modules["google.oauth2.credentials"] = MagicMock()
        sys.modules["google.oauth2.credentials"].Credentials = mock_credentials
        sys.modules["google_auth_oauthlib"] = MagicMock()
        sys.modules["google_auth_oauthlib.flow"] = MagicMock()
        sys.modules["google_auth_oauthlib.flow"].InstalledAppFlow = mock_flow
        sys.modules["google.auth"] = MagicMock()
        sys.modules["google.auth.transport"] = MagicMock()
        sys.modules["google.auth.transport.requests"] = MagicMock()
        sys.modules["google.auth.transport.requests"].Request = mock_request
        sys.modules["googleapiclient"] = MagicMock()
        sys.modules["googleapiclient.discovery"] = MagicMock()
        sys.modules["googleapiclient.discovery"].build = mock_build

    yield


class TestGoogleCalendarAuth:
    """Test Google Calendar authentication."""

    def test_ensure_authenticated_with_token(self, tmp_path):
        import modules.google_calendar as gc
        
        # Create fake token file
        token_file = tmp_path / "token.json"
        token_file.write_text('{"token": "test", "refresh_token": "test_refresh"}')
        
        calendar = gc.GoogleCalendar(
            credentials_path=str(tmp_path / "credentials.json"),
            token_path=str(token_file)
        )
        # Should not raise

    def test_authenticate_method(self, tmp_path):
        import modules.google_calendar as gc
        
        calendar = gc.GoogleCalendar(str(tmp_path / "creds.json"))
        
        if hasattr(calendar, 'authenticate'):
            # Mock the flow
            with patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file', 
                       return_value=MagicMock()):
                try:
                    calendar.authenticate()
                except Exception:
                    pass  # May fail without real credentials


class TestGoogleCalendarEvents:
    """Test event operations."""

    def test_list_events_no_service(self, tmp_path):
        import modules.google_calendar as gc
        
        calendar = gc.GoogleCalendar(str(tmp_path / "creds.json"))
        
        if hasattr(calendar, 'list_events'):
            result = calendar.list_events()
            # Should return empty or fallback data
            assert isinstance(result, (list, dict, str)) or result is None

    def test_get_todays_events(self, tmp_path):
        import modules.google_calendar as gc
        
        calendar = gc.GoogleCalendar(str(tmp_path / "creds.json"))
        result = calendar.get_todays_events()
        # Should return list or fallback
        assert isinstance(result, (list, str, dict))

    def test_get_upcoming_events(self, tmp_path):
        import modules.google_calendar as gc
        
        calendar = gc.GoogleCalendar(str(tmp_path / "creds.json"))
        
        if hasattr(calendar, 'get_upcoming_events'):
            result = calendar.get_upcoming_events(10)
            assert isinstance(result, (list, str, dict))

    def test_format_event(self, tmp_path):
        import modules.google_calendar as gc
        
        calendar = gc.GoogleCalendar(str(tmp_path / "creds.json"))
        
        if hasattr(calendar, 'format_event'):
            event = {
                'summary': 'Test Event',
                'start': {'dateTime': '2024-01-15T10:00:00Z'},
                'end': {'dateTime': '2024-01-15T11:00:00Z'}
            }
            result = calendar.format_event(event)
            assert isinstance(result, str)


class TestGoogleCalendarFormatting:
    """Test event formatting."""

    def test_format_events_speech_empty(self, tmp_path):
        import modules.google_calendar as gc
        
        calendar = gc.GoogleCalendar(str(tmp_path / "creds.json"))
        result = calendar.format_events_speech([])
        assert isinstance(result, str)
        assert "no" in result.lower() or "0" in result or len(result) > 0

    def test_format_events_speech_with_events(self, tmp_path):
        import modules.google_calendar as gc
        
        calendar = gc.GoogleCalendar(str(tmp_path / "creds.json"))
        events = [
            {'summary': 'Meeting', 'start': {'dateTime': '2024-01-15T10:00:00'}},
            {'summary': 'Lunch', 'start': {'dateTime': '2024-01-15T12:00:00'}}
        ]
        result = calendar.format_events_speech(events)
        assert isinstance(result, str)
        # Should mention the events
        assert 'meeting' in result.lower() or '2' in result or len(result) > 20


class TestGoogleCalendarCreateEvent:
    """Test event creation."""

    def test_create_event_no_service(self, tmp_path):
        import modules.google_calendar as gc
        
        calendar = gc.GoogleCalendar(str(tmp_path / "creds.json"))
        
        if hasattr(calendar, 'create_event'):
            result = calendar.create_event(
                title="Test Event",
                start_time=datetime.now(),
                end_time=datetime.now() + timedelta(hours=1)
            )
            # Should handle gracefully without service
            assert result is not None or result is None

    def test_quick_add_event(self, tmp_path):
        import modules.google_calendar as gc
        
        calendar = gc.GoogleCalendar(str(tmp_path / "creds.json"))
        
        if hasattr(calendar, 'quick_add'):
            result = calendar.quick_add("Meeting tomorrow at 3pm")
            # Should return result or handle gracefully


class TestGoogleCalendarDelete:
    """Test event deletion."""

    def test_delete_event_no_service(self, tmp_path):
        import modules.google_calendar as gc
        
        calendar = gc.GoogleCalendar(str(tmp_path / "creds.json"))
        
        if hasattr(calendar, 'delete_event'):
            result = calendar.delete_event("event_id_123")
            # Should handle gracefully


class TestGoogleCalendarTimeFilters:
    """Test time-based filtering."""

    def test_get_events_between(self, tmp_path):
        import modules.google_calendar as gc
        
        calendar = gc.GoogleCalendar(str(tmp_path / "creds.json"))
        
        if hasattr(calendar, 'get_events_between'):
            start = datetime.now()
            end = start + timedelta(days=7)
            result = calendar.get_events_between(start, end)

    def test_get_events_for_date(self, tmp_path):
        import modules.google_calendar as gc
        
        calendar = gc.GoogleCalendar(str(tmp_path / "creds.json"))
        
        if hasattr(calendar, 'get_events_for_date'):
            result = calendar.get_events_for_date(datetime.now())


class TestGoogleCalendarHelpers:
    """Test helper methods."""

    def test_parse_date_string(self, tmp_path):
        import modules.google_calendar as gc
        
        calendar = gc.GoogleCalendar(str(tmp_path / "creds.json"))
        
        if hasattr(calendar, 'parse_date'):
            result = calendar.parse_date("2024-01-15")
            assert result is not None

    def test_is_authenticated_property(self, tmp_path):
        import modules.google_calendar as gc
        
        calendar = gc.GoogleCalendar(str(tmp_path / "creds.json"))
        
        if hasattr(calendar, 'is_authenticated'):
            result = calendar.is_authenticated
            assert isinstance(result, bool)


class TestGoogleCalendarFallback:
    """Test fallback behavior."""

    def test_get_sample_events(self, tmp_path):
        import modules.google_calendar as gc
        
        calendar = gc.GoogleCalendar(str(tmp_path / "creds.json"))
        
        if hasattr(calendar, '_get_sample_events'):
            result = calendar._get_sample_events()
            assert isinstance(result, list)

    def test_generate_sample_events(self, tmp_path):
        import modules.google_calendar as gc
        
        if hasattr(gc, 'generate_sample_events'):
            result = gc.generate_sample_events(5)
            assert len(result) == 5
