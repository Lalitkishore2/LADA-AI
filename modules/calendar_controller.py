"""
LADA v9.0 - Google Calendar Full Control
Complete Google Calendar control for JARVIS-level scheduling.

Features:
- Create, read, update, delete events
- Search events by date range or query
- Manage multiple calendars
- Handle recurring events
- Quick event creation from natural language
- Meeting scheduling with attendees
- Reminders and notifications
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re

logger = logging.getLogger(__name__)

# Try to import Google API libraries
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_API_OK = True
except ImportError:
    GOOGLE_API_OK = False
    logger.warning("[!] Google API libraries not available")


# Calendar API scopes
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.events',
]


@dataclass
class CalendarEvent:
    """Represents a calendar event"""
    id: str
    summary: str
    start: datetime
    end: datetime
    description: str = ""
    location: str = ""
    attendees: List[str] = field(default_factory=list)
    calendar_id: str = "primary"
    is_all_day: bool = False
    recurrence: List[str] = field(default_factory=list)
    reminders: List[Dict] = field(default_factory=list)
    status: str = "confirmed"
    html_link: str = ""
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'summary': self.summary,
            'start': self.start.isoformat() if self.start else None,
            'end': self.end.isoformat() if self.end else None,
            'description': self.description,
            'location': self.location,
            'attendees': self.attendees,
            'is_all_day': self.is_all_day,
            'status': self.status,
            'link': self.html_link
        }


class CalendarController:
    """
    Complete Google Calendar control via Calendar API.
    Enables JARVIS-level scheduling and event management.
    """
    
    def __init__(self, credentials_path: str = "config/credentials.json",
                 token_path: str = "config/calendar_token.json"):
        """
        Initialize Calendar controller.
        Authentication is deferred until first use to avoid blocking startup.
        
        Args:
            credentials_path: Path to OAuth2 credentials JSON
            token_path: Path to store/load token
        """
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self.service = None
        self._auth_attempted = False
        
        # Don't authenticate on init - defer until first use
        if not GOOGLE_API_OK:
            logger.warning("[!] Google API not available - Calendar features disabled")
        
        logger.info("[OK] Calendar Controller initialized (auth deferred)")
    
    def _ensure_authenticated(self) -> bool:
        """
        Ensure we're authenticated before making API calls.
        Only attempts authentication once, and only if credentials exist.
        """
        if self.service is not None:
            return True
        
        if self._auth_attempted:
            return False
        
        if not GOOGLE_API_OK:
            return False
        
        # Check if credentials file exists before attempting OAuth
        if not self.credentials_path.exists():
            logger.warning(f"[!] Calendar credentials not found: {self.credentials_path}")
            logger.info("[!] To enable Calendar: Add credentials.json from Google Cloud Console")
            self._auth_attempted = True
            return False
        
        # Check if we have a valid token already (no browser needed)
        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
                if creds and creds.valid:
                    self.service = build('calendar', 'v3', credentials=creds)
                    logger.info("[OK] Calendar authenticated")
                    return True
                elif creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    with open(self.token_path, 'w') as token:
                        token.write(creds.to_json())
                    self.service = build('calendar', 'v3', credentials=creds)
                    logger.info("[OK] Calendar token refreshed")
                    return True
            except Exception as e:
                logger.warning(f"[!] Calendar token invalid: {e}")
        
        # No valid token - require manual authentication via settings
        logger.info("[!] Calendar requires authentication - use Settings to connect")
        self._auth_attempted = True
        return False
    
    def authenticate_interactive(self) -> bool:
        """
        Perform interactive OAuth authentication (opens browser).
        Call this from Settings when user explicitly wants to connect Calendar.
        """
        if not GOOGLE_API_OK:
            return False
        
        if not self.credentials_path.exists():
            logger.error(f"[X] Credentials file not found: {self.credentials_path}")
            return False
        
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_path), SCOPES
            )
            creds = flow.run_local_server(port=0)
            
            # Save token
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_path, 'w') as token:
                token.write(creds.to_json())
            
            # Build service
            self.service = build('calendar', 'v3', credentials=creds)
            self._auth_attempted = False  # Reset so future calls work
            
            logger.info("[OK] Calendar authenticated")
            return True
        
        except Exception as e:
            logger.error(f"[X] Calendar authentication failed: {e}")
            return False
    
    def _authenticate(self) -> bool:
        """Legacy method - now just calls _ensure_authenticated"""
        return self._ensure_authenticated()
    
    def is_authenticated(self) -> bool:
        """Check if Calendar is authenticated"""
        return self.service is not None
    
    # ==================== CREATE EVENTS ====================
    
    def create_event(self, summary: str, start: datetime, end: datetime,
                     description: str = "",
                     location: str = "",
                     attendees: List[str] = None,
                     reminders: List[int] = None,
                     calendar_id: str = "primary") -> Dict[str, Any]:
        """
        Create a new calendar event.
        
        Args:
            summary: Event title
            start: Start datetime
            end: End datetime
            description: Event description
            location: Event location
            attendees: List of attendee emails
            reminders: List of reminder minutes before event
            calendar_id: Calendar to add event to
        
        Returns:
            Dict with success status
        """
        if not self.service:
            return {'success': False, 'error': 'Calendar not authenticated'}
        
        try:
            event = {
                'summary': summary,
                'description': description,
                'location': location,
                'start': {
                    'dateTime': start.isoformat(),
                    'timeZone': 'Asia/Kolkata',  # Default timezone
                },
                'end': {
                    'dateTime': end.isoformat(),
                    'timeZone': 'Asia/Kolkata',
                },
            }
            
            # Add attendees
            if attendees:
                event['attendees'] = [{'email': email} for email in attendees]
            
            # Add reminders
            if reminders:
                event['reminders'] = {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': m} for m in reminders
                    ]
                }
            
            result = self.service.events().insert(
                calendarId=calendar_id,
                body=event,
                sendUpdates='all' if attendees else 'none'
            ).execute()
            
            logger.info(f"[OK] Event created: {summary}")
            return {
                'success': True,
                'event_id': result['id'],
                'summary': summary,
                'start': start.isoformat(),
                'end': end.isoformat(),
                'link': result.get('htmlLink', ''),
                'message': f"Event created: {summary}"
            }
        
        except HttpError as e:
            logger.error(f"[X] Failed to create event: {e}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"[X] Failed to create event: {e}")
            return {'success': False, 'error': str(e)}
    
    def create_all_day_event(self, summary: str, date: datetime,
                              description: str = "",
                              calendar_id: str = "primary") -> Dict[str, Any]:
        """
        Create an all-day event.
        
        Args:
            summary: Event title
            date: Date of the event
            description: Event description
            calendar_id: Calendar to add event to
        
        Returns:
            Dict with success status
        """
        if not self.service:
            return {'success': False, 'error': 'Calendar not authenticated'}
        
        try:
            event = {
                'summary': summary,
                'description': description,
                'start': {
                    'date': date.strftime('%Y-%m-%d'),
                },
                'end': {
                    'date': (date + timedelta(days=1)).strftime('%Y-%m-%d'),
                },
            }
            
            result = self.service.events().insert(
                calendarId=calendar_id,
                body=event
            ).execute()
            
            return {
                'success': True,
                'event_id': result['id'],
                'summary': summary,
                'date': date.strftime('%Y-%m-%d'),
                'message': f"All-day event created: {summary}"
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def quick_add(self, text: str, calendar_id: str = "primary") -> Dict[str, Any]:
        """
        Create event from natural language text.
        Uses Google's natural language parsing.
        
        Args:
            text: Natural language event description
                  (e.g., "Meeting with John tomorrow at 3pm")
            calendar_id: Calendar to add event to
        
        Returns:
            Dict with success status
        """
        if not self.service:
            return {'success': False, 'error': 'Calendar not authenticated'}
        
        try:
            result = self.service.events().quickAdd(
                calendarId=calendar_id,
                text=text
            ).execute()
            
            return {
                'success': True,
                'event_id': result['id'],
                'summary': result.get('summary', text),
                'start': result.get('start', {}).get('dateTime', result.get('start', {}).get('date')),
                'link': result.get('htmlLink', ''),
                'message': f"Event created from: {text}"
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def create_meeting(self, summary: str, start: datetime, 
                       duration_minutes: int = 60,
                       attendees: List[str] = None,
                       description: str = "",
                       location: str = "") -> Dict[str, Any]:
        """
        Create a meeting with attendees.
        
        Args:
            summary: Meeting title
            start: Start datetime
            duration_minutes: Meeting duration in minutes
            attendees: List of attendee emails
            description: Meeting description
            location: Meeting location
        
        Returns:
            Dict with success status
        """
        end = start + timedelta(minutes=duration_minutes)
        
        return self.create_event(
            summary=summary,
            start=start,
            end=end,
            description=description,
            location=location,
            attendees=attendees or [],
            reminders=[30, 10]  # 30 and 10 minutes before
        )
    
    # ==================== READ EVENTS ====================
    
    def get_upcoming_events(self, max_results: int = 10,
                            calendar_id: str = "primary") -> Dict[str, Any]:
        """
        Get upcoming events.
        
        Args:
            max_results: Maximum events to return
            calendar_id: Calendar to query
        
        Returns:
            Dict with events
        """
        if not self.service:
            return {'success': False, 'error': 'Calendar not authenticated'}
        
        try:
            now = datetime.utcnow().isoformat() + 'Z'
            
            result = self.service.events().list(
                calendarId=calendar_id,
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = []
            for event in result.get('items', []):
                events.append(self._parse_event(event))
            
            return {
                'success': True,
                'events': [e.to_dict() for e in events],
                'count': len(events)
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_today_events(self, calendar_id: str = "primary") -> Dict[str, Any]:
        """Get today's events"""
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        
        return self.get_events_in_range(today_start, today_end, calendar_id)
    
    def get_tomorrow_events(self, calendar_id: str = "primary") -> Dict[str, Any]:
        """Get tomorrow's events"""
        tomorrow_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        tomorrow_end = tomorrow_start + timedelta(days=1)
        
        return self.get_events_in_range(tomorrow_start, tomorrow_end, calendar_id)
    
    def get_week_events(self, calendar_id: str = "primary") -> Dict[str, Any]:
        """Get this week's events"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = today + timedelta(days=7)
        
        return self.get_events_in_range(today, week_end, calendar_id)
    
    def get_events_in_range(self, start: datetime, end: datetime,
                            calendar_id: str = "primary") -> Dict[str, Any]:
        """
        Get events in a date range.
        
        Args:
            start: Start datetime
            end: End datetime
            calendar_id: Calendar to query
        
        Returns:
            Dict with events
        """
        if not self.service:
            return {'success': False, 'error': 'Calendar not authenticated'}
        
        try:
            result = self.service.events().list(
                calendarId=calendar_id,
                timeMin=start.isoformat() + 'Z' if start.tzinfo is None else start.isoformat(),
                timeMax=end.isoformat() + 'Z' if end.tzinfo is None else end.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = []
            for event in result.get('items', []):
                events.append(self._parse_event(event))
            
            return {
                'success': True,
                'events': [e.to_dict() for e in events],
                'count': len(events),
                'range': {
                    'start': start.isoformat(),
                    'end': end.isoformat()
                }
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def search_events(self, query: str, max_results: int = 10,
                      calendar_id: str = "primary") -> Dict[str, Any]:
        """
        Search events by text.
        
        Args:
            query: Search query
            max_results: Maximum results
            calendar_id: Calendar to search
        
        Returns:
            Dict with matching events
        """
        if not self.service:
            return {'success': False, 'error': 'Calendar not authenticated'}
        
        try:
            result = self.service.events().list(
                calendarId=calendar_id,
                q=query,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = []
            for event in result.get('items', []):
                events.append(self._parse_event(event))
            
            return {
                'success': True,
                'query': query,
                'events': [e.to_dict() for e in events],
                'count': len(events)
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_event(self, event_id: str, calendar_id: str = "primary") -> Dict[str, Any]:
        """
        Get a specific event.
        
        Args:
            event_id: Event ID
            calendar_id: Calendar ID
        
        Returns:
            Dict with event details
        """
        if not self.service:
            return {'success': False, 'error': 'Calendar not authenticated'}
        
        try:
            event = self.service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            
            return {
                'success': True,
                'event': self._parse_event(event).to_dict()
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _parse_event(self, event: Dict) -> CalendarEvent:
        """Parse API event to CalendarEvent"""
        start = event.get('start', {})
        end = event.get('end', {})
        
        # Handle all-day vs timed events
        is_all_day = 'date' in start
        
        if is_all_day:
            start_dt = datetime.strptime(start['date'], '%Y-%m-%d')
            end_dt = datetime.strptime(end['date'], '%Y-%m-%d')
        else:
            start_str = start.get('dateTime', '')
            end_str = end.get('dateTime', '')
            try:
                start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
            except:
                start_dt = datetime.now()
                end_dt = datetime.now()
        
        attendees = [a.get('email', '') for a in event.get('attendees', [])]
        
        return CalendarEvent(
            id=event['id'],
            summary=event.get('summary', '(No Title)'),
            start=start_dt,
            end=end_dt,
            description=event.get('description', ''),
            location=event.get('location', ''),
            attendees=attendees,
            is_all_day=is_all_day,
            recurrence=event.get('recurrence', []),
            status=event.get('status', 'confirmed'),
            html_link=event.get('htmlLink', '')
        )
    
    # ==================== UPDATE EVENTS ====================
    
    def update_event(self, event_id: str, 
                     summary: str = None,
                     start: datetime = None,
                     end: datetime = None,
                     description: str = None,
                     location: str = None,
                     calendar_id: str = "primary") -> Dict[str, Any]:
        """
        Update an existing event.
        
        Args:
            event_id: Event ID to update
            summary: New title (None to keep)
            start: New start time (None to keep)
            end: New end time (None to keep)
            description: New description (None to keep)
            location: New location (None to keep)
            calendar_id: Calendar ID
        
        Returns:
            Dict with success status
        """
        if not self.service:
            return {'success': False, 'error': 'Calendar not authenticated'}
        
        try:
            # Get existing event
            event = self.service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            
            # Update fields
            if summary is not None:
                event['summary'] = summary
            if description is not None:
                event['description'] = description
            if location is not None:
                event['location'] = location
            if start is not None:
                event['start'] = {'dateTime': start.isoformat(), 'timeZone': 'Asia/Kolkata'}
            if end is not None:
                event['end'] = {'dateTime': end.isoformat(), 'timeZone': 'Asia/Kolkata'}
            
            result = self.service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event
            ).execute()
            
            return {
                'success': True,
                'event_id': event_id,
                'summary': result.get('summary'),
                'message': 'Event updated'
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def reschedule_event(self, event_id: str, new_start: datetime,
                         new_end: datetime = None,
                         calendar_id: str = "primary") -> Dict[str, Any]:
        """
        Reschedule an event to a new time.
        
        Args:
            event_id: Event ID
            new_start: New start time
            new_end: New end time (None = keep same duration)
            calendar_id: Calendar ID
        
        Returns:
            Dict with success status
        """
        if not self.service:
            return {'success': False, 'error': 'Calendar not authenticated'}
        
        try:
            # Get existing event to calculate duration
            event = self.service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            
            # Calculate original duration
            old_start = event.get('start', {}).get('dateTime')
            old_end = event.get('end', {}).get('dateTime')
            
            if old_start and old_end:
                old_start_dt = datetime.fromisoformat(old_start.replace('Z', '+00:00'))
                old_end_dt = datetime.fromisoformat(old_end.replace('Z', '+00:00'))
                duration = old_end_dt - old_start_dt
            else:
                duration = timedelta(hours=1)
            
            # Calculate new end if not provided
            if new_end is None:
                new_end = new_start + duration
            
            return self.update_event(
                event_id=event_id,
                start=new_start,
                end=new_end,
                calendar_id=calendar_id
            )
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== DELETE EVENTS ====================
    
    def delete_event(self, event_id: str, 
                     calendar_id: str = "primary") -> Dict[str, Any]:
        """
        Delete an event.
        
        Args:
            event_id: Event ID to delete
            calendar_id: Calendar ID
        
        Returns:
            Dict with success status
        """
        if not self.service:
            return {'success': False, 'error': 'Calendar not authenticated'}
        
        try:
            self.service.events().delete(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            
            return {
                'success': True,
                'event_id': event_id,
                'message': 'Event deleted'
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def cancel_event(self, event_id: str,
                     calendar_id: str = "primary") -> Dict[str, Any]:
        """
        Cancel an event (marks as cancelled, sends notifications).
        
        Args:
            event_id: Event ID
            calendar_id: Calendar ID
        
        Returns:
            Dict with success status
        """
        if not self.service:
            return {'success': False, 'error': 'Calendar not authenticated'}
        
        try:
            event = self.service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            
            event['status'] = 'cancelled'
            
            self.service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event,
                sendUpdates='all'
            ).execute()
            
            return {
                'success': True,
                'event_id': event_id,
                'message': 'Event cancelled'
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== CALENDAR MANAGEMENT ====================
    
    def list_calendars(self) -> Dict[str, Any]:
        """List all calendars"""
        if not self.service:
            return {'success': False, 'error': 'Calendar not authenticated'}
        
        try:
            result = self.service.calendarList().list().execute()
            
            calendars = []
            for cal in result.get('items', []):
                calendars.append({
                    'id': cal['id'],
                    'summary': cal.get('summary', ''),
                    'primary': cal.get('primary', False),
                    'color': cal.get('backgroundColor', '')
                })
            
            return {
                'success': True,
                'calendars': calendars,
                'count': len(calendars)
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_free_busy(self, start: datetime, end: datetime,
                      calendar_ids: List[str] = None) -> Dict[str, Any]:
        """
        Get free/busy information.
        
        Args:
            start: Start of time range
            end: End of time range
            calendar_ids: Calendars to check (None for primary)
        
        Returns:
            Dict with busy times
        """
        if not self.service:
            return {'success': False, 'error': 'Calendar not authenticated'}
        
        try:
            if calendar_ids is None:
                calendar_ids = ['primary']
            
            body = {
                'timeMin': start.isoformat() + 'Z',
                'timeMax': end.isoformat() + 'Z',
                'items': [{'id': cal_id} for cal_id in calendar_ids]
            }
            
            result = self.service.freebusy().query(body=body).execute()
            
            busy_times = {}
            for cal_id, data in result.get('calendars', {}).items():
                busy_times[cal_id] = [
                    {
                        'start': b['start'],
                        'end': b['end']
                    }
                    for b in data.get('busy', [])
                ]
            
            return {
                'success': True,
                'busy_times': busy_times,
                'range': {
                    'start': start.isoformat(),
                    'end': end.isoformat()
                }
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== NATURAL LANGUAGE HELPERS ====================
    
    def parse_time_expression(self, text: str) -> Optional[datetime]:
        """
        Parse natural language time expressions.
        
        Args:
            text: Time expression like "tomorrow at 3pm", "next Monday"
        
        Returns:
            datetime or None if parsing fails
        """
        text = text.lower().strip()
        now = datetime.now()
        
        # Today/Tomorrow
        if 'today' in text:
            base_date = now
        elif 'tomorrow' in text:
            base_date = now + timedelta(days=1)
        else:
            base_date = now
        
        # Extract time
        time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', text)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or 0)
            ampm = time_match.group(3)
            
            if ampm == 'pm' and hour < 12:
                hour += 12
            elif ampm == 'am' and hour == 12:
                hour = 0
            
            return base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        return None
    
    def get_next_available_slot(self, duration_minutes: int = 60,
                                start_hour: int = 9,
                                end_hour: int = 17) -> Dict[str, Any]:
        """
        Find next available time slot.
        
        Args:
            duration_minutes: Required duration
            start_hour: Start of working hours
            end_hour: End of working hours
        
        Returns:
            Dict with available slot
        """
        if not self.service:
            return {'success': False, 'error': 'Calendar not authenticated'}
        
        try:
            # Check next 7 days
            today = datetime.now().replace(hour=start_hour, minute=0, second=0, microsecond=0)
            week_end = today + timedelta(days=7)
            
            # Get busy times
            free_busy = self.get_free_busy(today, week_end)
            if not free_busy['success']:
                return free_busy
            
            busy_times = free_busy['busy_times'].get('primary', [])
            
            # Find first available slot
            current = today
            if current.hour < start_hour:
                current = current.replace(hour=start_hour)
            elif current.hour >= end_hour:
                current = (current + timedelta(days=1)).replace(hour=start_hour)
            
            while current < week_end:
                slot_end = current + timedelta(minutes=duration_minutes)
                
                # Check if slot is within working hours
                if slot_end.hour > end_hour:
                    current = (current + timedelta(days=1)).replace(hour=start_hour)
                    continue
                
                # Check if slot conflicts with busy times
                is_free = True
                for busy in busy_times:
                    busy_start = datetime.fromisoformat(busy['start'].replace('Z', '+00:00'))
                    busy_end = datetime.fromisoformat(busy['end'].replace('Z', '+00:00'))
                    
                    if current < busy_end and slot_end > busy_start:
                        is_free = False
                        current = busy_end.replace(tzinfo=None)
                        break
                
                if is_free:
                    return {
                        'success': True,
                        'slot': {
                            'start': current.isoformat(),
                            'end': slot_end.isoformat(),
                            'duration_minutes': duration_minutes
                        },
                        'message': f"Next available: {current.strftime('%A %I:%M %p')}"
                    }
                
                current += timedelta(minutes=30)
            
            return {
                'success': False,
                'error': 'No available slot found in the next 7 days'
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}


# Factory function for workflow engine integration
def create_calendar_controller(credentials_path: str = "config/credentials.json") -> CalendarController:
    """Create and return a CalendarController instance"""
    return CalendarController(credentials_path)


if __name__ == '__main__':
    # Test the Calendar controller
    logging.basicConfig(level=logging.INFO)
    cal = CalendarController()
    
    print("\n=== Testing Calendar Controller ===")
    
    if cal.is_authenticated():
        # List calendars
        calendars = cal.list_calendars()
        if calendars['success']:
            print(f"Calendars: {calendars['count']}")
            for c in calendars['calendars'][:3]:
                print(f"  • {c['summary']} {'(primary)' if c['primary'] else ''}")
        
        # Get today's events
        today = cal.get_today_events()
        if today['success']:
            print(f"\nToday's events: {today['count']}")
            for e in today['events'][:5]:
                print(f"  • {e['summary']} at {e['start']}")
        
        # Get upcoming events
        upcoming = cal.get_upcoming_events(5)
        if upcoming['success']:
            print(f"\nUpcoming events: {upcoming['count']}")
            for e in upcoming['events']:
                print(f"  • {e['summary']}: {e['start']}")
    else:
        print("[!] Calendar not authenticated")
        print("    Place credentials.json in config/ folder")
    
    print("\n[OK] Calendar Controller tests complete!")
    print("\nTry commands like:")
    print("  cal.create_event('Meeting', start, end)")
    print("  cal.quick_add('Lunch with John tomorrow at noon')")
    print("  cal.get_week_events()")
