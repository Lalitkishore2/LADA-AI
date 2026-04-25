"""
LADA v9.0 - Calendar Agent Tests
Comprehensive tests for CalendarAgent - Target: 80%+ coverage
"""

import pytest
from unittest.mock import MagicMock, patch, mock_open
from datetime import datetime, timedelta
import pickle
import sys

# Store original modules
_original_modules = {}

@pytest.fixture(autouse=True)
def mock_google_modules():
    """Mock Google API modules before importing CalendarAgent."""
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
    
    # Cleanup is optional since we're just adding mocks


class TestCalendarAgentInit:
    """Test CalendarAgent initialization."""
    
    def test_init_default_path(self):
        """Test initialization with default credentials path."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        
        assert 'credentials.json' in str(agent.credentials_path)
        assert 'calendar_token' in str(agent.token_path)
        assert agent.service is None
        assert agent.calendar_id == 'primary'
        assert agent._auth_attempted is False
    
    def test_init_custom_path(self):
        """Test initialization with custom credentials path."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent(credentials_path='custom/path.json')
        
        assert 'custom' in str(agent.credentials_path)


class TestEnsureAuthenticated:
    """Test _ensure_authenticated method."""
    
    def test_already_authenticated(self):
        """Test when service already exists."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        agent.service = MagicMock()
        
        result = agent._ensure_authenticated()
        assert result is True
    
    def test_auth_already_attempted(self):
        """Test when auth was already attempted and failed."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        agent._auth_attempted = True
        
        result = agent._ensure_authenticated()
        assert result is False
    
    def test_no_credentials_file(self):
        """Test when credentials file doesn't exist."""
        from modules.agents.calendar_agent import CalendarAgent
        from pathlib import Path
        
        agent = CalendarAgent()
        
        # Use a non-existent path directly
        agent.credentials_path = Path('/nonexistent/path/that/does/not/exist.json')
        
        result = agent._ensure_authenticated()
        
        # Should return False when credentials don't exist
        assert result is False


class TestListEvents:
    """Test list_events method."""
    
    def test_list_events_with_service(self):
        """Test listing events with valid service."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        agent.service = MagicMock()
        
        mock_events = {
            'items': [
                {
                    'id': 'event1',
                    'summary': 'Test Meeting',
                    'start': {'dateTime': '2026-01-03T10:00:00'},
                    'end': {'dateTime': '2026-01-03T11:00:00'},
                    'description': 'Test description',
                    'location': 'Room A',
                    'attendees': [{'email': 'test@example.com'}],
                    'status': 'confirmed',
                    'htmlLink': 'https://calendar.google.com/event1'
                }
            ]
        }
        agent.service.events().list().execute.return_value = mock_events
        
        result = agent.list_events(max_results=5)
        
        assert result['success'] is True
        assert result['count'] == 1
        assert len(result['events']) == 1
        assert result['events'][0]['summary'] == 'Test Meeting'
    
    def test_list_events_api_exception(self):
        """Test list events when API throws exception."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        agent.service = MagicMock()
        agent.service.events().list().execute.side_effect = Exception("API Error")
        
        result = agent.list_events()
        
        assert result['success'] is True
        assert 'sample data' in result.get('message', '')
    
    def test_list_events_no_service_fallback(self):
        """Test list events without service (fallback to samples)."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        agent.service = None
        
        result = agent.list_events(max_results=5)
        
        assert result['success'] is True
        assert result['count'] > 0
        assert 'sample data' in result.get('message', '')
    
    def test_list_events_with_time_filters(self):
        """Test list events with time_min and time_max."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        agent.service = None
        
        result = agent.list_events(
            max_results=5,
            time_min='2026-01-01T00:00:00Z',
            time_max='2026-01-31T23:59:59Z'
        )
        
        assert result['success'] is True


class TestFormatEvent:
    """Test _format_event method."""
    
    def test_format_complete_event(self):
        """Test formatting a complete event."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        
        event = {
            'id': 'event123',
            'summary': 'Team Meeting',
            'description': 'Weekly sync',
            'start': {'dateTime': '2026-01-03T14:00:00'},
            'end': {'dateTime': '2026-01-03T15:00:00'},
            'location': 'Conference Room',
            'attendees': [
                {'email': 'alice@example.com'},
                {'email': 'bob@example.com'}
            ],
            'status': 'confirmed',
            'htmlLink': 'https://calendar.google.com/event123'
        }
        
        formatted = agent._format_event(event)
        
        assert formatted['id'] == 'event123'
        assert formatted['summary'] == 'Team Meeting'
        assert formatted['description'] == 'Weekly sync'
        assert formatted['location'] == 'Conference Room'
        assert len(formatted['attendees']) == 2
        assert formatted['status'] == 'confirmed'
    
    def test_format_event_with_date_only(self):
        """Test formatting all-day event (date instead of dateTime)."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        
        event = {
            'id': 'allday1',
            'summary': 'Holiday',
            'start': {'date': '2026-01-03'},
            'end': {'date': '2026-01-04'}
        }
        
        formatted = agent._format_event(event)
        
        assert formatted['start'] == '2026-01-03'
        assert formatted['end'] == '2026-01-04'
    
    def test_format_minimal_event(self):
        """Test formatting event with minimal data."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        
        event = {'id': 'min1'}
        
        formatted = agent._format_event(event)
        
        assert formatted['id'] == 'min1'
        assert formatted['summary'] == 'No Title'
        assert formatted['description'] == ''


class TestGenerateSampleEvents:
    """Test _generate_sample_events method."""
    
    def test_generate_sample_events_count(self):
        """Test generating specific number of sample events."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        
        result = agent._generate_sample_events(3)
        
        assert result['success'] is True
        assert result['count'] == 3
        assert len(result['events']) == 3
    
    def test_generate_sample_events_max_limit(self):
        """Test that sample events are capped at 10."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        
        result = agent._generate_sample_events(20)
        
        assert result['count'] <= 10
    
    def test_sample_events_have_required_fields(self):
        """Test that sample events have all required fields."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        
        result = agent._generate_sample_events(1)
        event = result['events'][0]
        
        assert 'id' in event
        assert 'summary' in event
        assert 'start' in event
        assert 'end' in event
        assert 'status' in event


class TestCheckAvailability:
    """Test check_availability method."""
    
    def test_check_availability_valid_date(self):
        """Test checking availability for a valid date."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        agent.service = None
        
        result = agent.check_availability('2026-01-03')
        
        assert result['success'] is True
        assert result['date'] == '2026-01-03'
        assert 'busy_slots' in result
        assert 'work_hours' in result
    
    def test_check_availability_invalid_date(self):
        """Test checking availability with invalid date format."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        
        result = agent.check_availability('invalid-date')
        
        assert result['success'] is True
        assert 'date' in result
    
    def test_check_availability_custom_hours(self):
        """Test availability with custom work hours."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        
        result = agent.check_availability(
            '2026-01-03',
            start_time='10:00',
            end_time='17:00'
        )
        
        assert result['success'] is True
        assert result['work_hours'] == '10:00 - 17:00'


class TestScheduleMeeting:
    """Test schedule_meeting method."""
    
    def test_schedule_meeting_with_service(self):
        """Test scheduling meeting with valid service."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        agent.service = MagicMock()
        
        mock_created = {
            'id': 'new_event_123',
            'htmlLink': 'https://calendar.google.com/new_event_123'
        }
        agent.service.events().insert().execute.return_value = mock_created
        
        result = agent.schedule_meeting(
            title='Team Sync',
            start='2026-01-04 10:00',
            end='2026-01-04 11:00',
            description='Weekly team meeting',
            attendees=['alice@example.com']
        )
        
        assert result['success'] is True
        assert result['event_id'] == 'new_event_123'
        assert result['title'] == 'Team Sync'
    
    def test_schedule_meeting_invalid_date_format(self):
        """Test scheduling with invalid date format."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        
        result = agent.schedule_meeting(
            title='Test',
            start='not-a-date',
            end='also-not-a-date'
        )
        
        assert result['success'] is False
        assert 'error' in result
    
    def test_schedule_meeting_iso_format(self):
        """Test scheduling with ISO format dates."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        agent.service = None
        
        result = agent.schedule_meeting(
            title='ISO Meeting',
            start='2026-01-04T10:00:00',
            end='2026-01-04T11:00:00'
        )
        
        assert result['success'] is True
        assert 'Simulated' in result.get('note', '')
    
    def test_schedule_meeting_with_location(self):
        """Test scheduling meeting with location."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        agent.service = None
        
        result = agent.schedule_meeting(
            title='Office Meeting',
            start='2026-01-04 14:00',
            end='2026-01-04 15:00',
            location='Conference Room B'
        )
        
        assert result['success'] is True
    
    def test_schedule_meeting_api_failure(self):
        """Test schedule when API fails."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        agent.service = MagicMock()
        agent.service.events().insert().execute.side_effect = Exception("API Error")
        
        result = agent.schedule_meeting(
            title='Test Meeting',
            start='2026-01-04 10:00',
            end='2026-01-04 11:00'
        )
        
        assert result['success'] is True
        assert 'Simulated' in result.get('note', '')


class TestQuickAdd:
    """Test quick_add method."""
    
    def test_quick_add_with_service(self):
        """Test quick add with valid service."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        agent.service = MagicMock()
        
        mock_created = {
            'id': 'quick_event_1',
            'summary': 'Lunch with John',
            'start': {'dateTime': '2026-01-04T13:00:00'},
            'htmlLink': 'https://calendar.google.com/quick_event_1'
        }
        agent.service.events().quickAdd().execute.return_value = mock_created
        
        result = agent.quick_add('Lunch with John tomorrow at 1pm')
        
        assert result['success'] is True
        assert result['event_id'] == 'quick_event_1'
    
    def test_quick_add_api_exception(self):
        """Test quick add when API fails."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        agent.service = MagicMock()
        agent.service.events().quickAdd().execute.side_effect = Exception("API Error")
        
        result = agent.quick_add('Meeting tomorrow at 3pm')
        
        assert result['success'] is True
    
    def test_quick_add_no_service(self):
        """Test quick add without service (fallback parsing)."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        agent.service = None
        
        result = agent.quick_add('Call with team tomorrow at 2pm')
        
        assert result['success'] is True
        assert 'Simulated' in result.get('note', '')


class TestDeleteEvent:
    """Test delete_event method."""
    
    def test_delete_event_with_service(self):
        """Test deleting event with valid service."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        agent.service = MagicMock()
        
        result = agent.delete_event('event_to_delete')
        
        assert result['success'] is True
        assert result['event_id'] == 'event_to_delete'
    
    def test_delete_event_no_service(self):
        """Test delete without service (simulated)."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        agent.service = None
        
        result = agent.delete_event('event_456')
        
        assert result['success'] is True
        assert 'Simulated' in result.get('note', '')


class TestGetTodaySummary:
    """Test get_today_summary method."""
    
    def test_today_summary_with_events(self):
        """Test summary with events."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        agent.service = None
        
        result = agent.get_today_summary()
        
        assert result['success'] is True
        assert 'summary' in result or 'message' in result


class TestProcess:
    """Test process method (natural language processing)."""
    
    def test_process_schedule_intent(self):
        """Test processing schedule/create intent."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        
        result = agent.process('schedule a meeting tomorrow at 3pm')
        
        assert 'success' in result
    
    def test_process_availability_intent(self):
        """Test processing availability check intent."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        
        result = agent.process('check my availability for 2026-01-05')
        
        assert result['success'] is True
    
    def test_process_today_intent(self):
        """Test processing today/agenda intent."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        
        result = agent.process("what's on my agenda today")
        
        assert result['success'] is True
    
    def test_process_list_intent(self):
        """Test processing list/upcoming intent."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        
        result = agent.process('show me upcoming events')
        
        assert result['success'] is True


class TestLegacyAuthenticate:
    """Test legacy _authenticate method."""
    
    def test_authenticate_calls_ensure(self):
        """Test that _authenticate calls _ensure_authenticated."""
        from modules.agents.calendar_agent import CalendarAgent
        agent = CalendarAgent()
        
        with patch.object(agent, '_ensure_authenticated', return_value=True) as mock_ensure:
            result = agent._authenticate()
            mock_ensure.assert_called_once()
            assert result is True
