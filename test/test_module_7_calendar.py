import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import sys

# Inject mocks into module namespace
import modules.calendar_controller
modules.calendar_controller.build = MagicMock()
modules.calendar_controller.Credentials = MagicMock()
modules.calendar_controller.GOOGLE_API_OK = True

from modules.calendar_controller import CalendarController

class TestCalendarController:
    
    @pytest.fixture
    def controller(self):
        # Reset mocks
        modules.calendar_controller.build.reset_mock()
        modules.calendar_controller.Credentials.reset_mock()
        
        controller = CalendarController()
        controller.service = modules.calendar_controller.build.return_value
        return controller

    def test_create_event(self, controller):
        """Test creating event"""
        controller.service.events().insert().execute.return_value = {
            "id": "evt123",
            "htmlLink": "http://calendar/evt123"
        }
        
        start = datetime.now()
        end = start + timedelta(hours=1)
        
        result = controller.create_event(
            summary="Test Event",
            start=start,
            end=end,
            description="Test Description"
        )
        
        assert result["success"] is True
        assert result["event_id"] == "evt123"
        controller.service.events().insert.assert_called()

    def test_create_all_day_event(self, controller):
        """Test creating all day event"""
        controller.service.events().insert().execute.return_value = {
            "id": "evt_all_day"
        }
        
        result = controller.create_all_day_event(
            summary="All Day Test",
            date=datetime.now()
        )
        
        assert result["success"] is True
        assert result["event_id"] == "evt_all_day"

    def test_quick_add(self, controller):
        """Test quick add"""
        controller.service.events().quickAdd().execute.return_value = {
            "id": "evt_quick",
            "summary": "Lunch tomorrow"
        }
        
        result = controller.quick_add("Lunch tomorrow")
        
        assert result["success"] is True
        assert result["event_id"] == "evt_quick"

    def test_get_upcoming_events(self, controller):
        """Test getting upcoming events"""
        mock_event = {
            "id": "evt1",
            "summary": "Meeting",
            "start": {"dateTime": "2024-01-01T10:00:00Z"},
            "end": {"dateTime": "2024-01-01T11:00:00Z"}
        }
        controller.service.events().list().execute.return_value = {
            "items": [mock_event]
        }
        
        result = controller.get_upcoming_events(max_results=1)
        
        assert result["success"] is True
        assert len(result["events"]) == 1
        assert result["events"][0]["summary"] == "Meeting"

    def test_get_today_events(self, controller):
        """Test getting today events"""
        controller.service.events().list().execute.return_value = {"items": []}
        
        result = controller.get_today_events()
        
        assert result["success"] is True
        controller.service.events().list.assert_called()

    def test_search_events(self, controller):
        """Test searching events"""
        controller.service.events().list().execute.return_value = {"items": []}
        
        result = controller.search_events("Meeting")
        
        assert result["success"] is True
        assert result["query"] == "Meeting"

    def test_get_event(self, controller):
        """Test getting specific event"""
        mock_event = {
            "id": "evt1",
            "summary": "Meeting"
        }
        controller.service.events().get().execute.return_value = mock_event
        
        result = controller.get_event("evt1")
        
        assert result["success"] is True
        assert result["event"]["summary"] == "Meeting"

    def test_update_event(self, controller):
        """Test updating event"""
        controller.service.events().patch().execute.return_value = {
            "id": "evt1",
            "summary": "Updated Meeting"
        }
        
        result = controller.update_event("evt1", summary="Updated Meeting")
        
        assert result["success"] is True
        controller.service.events().patch.assert_called()

