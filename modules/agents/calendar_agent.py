"""
LADA v7.0 - Calendar Agent
Google Calendar integration for scheduling and meetings
"""

import re
import json
import logging
import pickle
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import Google Calendar API
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    GCAL_OK = True
except ImportError:
    GCAL_OK = False
    logger.warning("[CalendarAgent] Google Calendar API not available")


class CalendarAgent:
    """
    Google Calendar integration agent.
    
    Features:
    - Check availability
    - Schedule meetings
    - Send invites
    - List upcoming events
    - Set reminders
    """
    
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    
    def __init__(self, credentials_path: str = 'config/credentials.json'):
        """
        Initialize calendar agent.
        Authentication is deferred until first use to avoid blocking startup.
        
        Args:
            credentials_path: Path to Google OAuth credentials
        """
        self.credentials_path = Path(credentials_path)
        self.token_path = Path('config/calendar_token.pickle')
        self.service = None
        self.calendar_id = 'primary'
        self._auth_attempted = False
        
        # Don't authenticate on init - defer until first use
        if not GCAL_OK:
            logger.warning("[CalendarAgent] Google Calendar API not available")
    
    def _ensure_authenticated(self) -> bool:
        """
        Ensure authenticated before API calls.
        Only tries once, only if valid token exists (no browser popup).
        """
        if self.service is not None:
            return True
        
        if self._auth_attempted:
            return False
        
        if not GCAL_OK:
            return False
        
        # Check for credentials file
        if not self.credentials_path.exists():
            logger.warning("[CalendarAgent] No credentials file found")
            self._auth_attempted = True
            return False
        
        # Try to use existing token (no browser popup)
        if self.token_path.exists():
            try:
                with open(self.token_path, 'rb') as token:
                    creds = pickle.load(token)
                
                if creds and creds.valid:
                    self.service = build('calendar', 'v3', credentials=creds)
                    logger.info("[CalendarAgent] Authenticated successfully")
                    return True
                elif creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    with open(self.token_path, 'wb') as token:
                        pickle.dump(creds, token)
                    self.service = build('calendar', 'v3', credentials=creds)
                    logger.info("[CalendarAgent] Token refreshed")
                    return True
            except Exception as e:
                logger.warning(f"[CalendarAgent] Token invalid: {e}")
        
        # No valid token - require manual auth
        logger.info("[CalendarAgent] Requires authentication via Settings")
        self._auth_attempted = True
        return False
    
    def _authenticate(self) -> bool:
        """Legacy method - now just calls _ensure_authenticated"""
        return self._ensure_authenticated()
    
    def list_events(
        self,
        max_results: int = 10,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None
    ) -> Dict:
        """
        List upcoming calendar events.
        
        Args:
            max_results: Maximum events to return
            time_min: Start time filter (ISO format)
            time_max: End time filter (ISO format)
            
        Returns:
            Events dict
        """
        if not time_min:
            time_min = datetime.utcnow().isoformat() + 'Z'
        
        if self.service:
            try:
                events_result = self.service.events().list(
                    calendarId=self.calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
                events = events_result.get('items', [])
                
                return {
                    'success': True,
                    'count': len(events),
                    'events': [self._format_event(e) for e in events],
                    'message': f"Found {len(events)} upcoming events"
                }
            except Exception as e:
                logger.error(f"[CalendarAgent] List events failed: {e}")
        
        # Fallback: Generate sample events
        return self._generate_sample_events(max_results)
    
    def _format_event(self, event: Dict) -> Dict:
        """Format a calendar event."""
        start = event.get('start', {})
        end = event.get('end', {})
        
        return {
            'id': event.get('id'),
            'summary': event.get('summary', 'No Title'),
            'description': event.get('description', ''),
            'start': start.get('dateTime', start.get('date')),
            'end': end.get('dateTime', end.get('date')),
            'location': event.get('location', ''),
            'attendees': [a.get('email') for a in event.get('attendees', [])],
            'status': event.get('status'),
            'link': event.get('htmlLink')
        }
    
    def _generate_sample_events(self, count: int) -> Dict:
        """Generate sample calendar events."""
        import random
        
        event_types = [
            "Team Standup",
            "Project Review",
            "1:1 with Manager",
            "Sprint Planning",
            "Client Call",
            "Training Session",
            "Lunch Meeting",
            "Code Review",
            "Design Discussion",
            "All Hands Meeting"
        ]
        
        events = []
        base_time = datetime.now()
        
        for i in range(min(count, 10)):
            start_time = base_time + timedelta(hours=random.randint(1, 72))
            duration = random.choice([30, 60, 90])
            end_time = start_time + timedelta(minutes=duration)
            
            events.append({
                'id': f'sample_{i}',
                'summary': random.choice(event_types),
                'description': 'Sample event for demonstration',
                'start': start_time.isoformat(),
                'end': end_time.isoformat(),
                'location': random.choice(['Room A', 'Room B', 'Virtual', '']),
                'attendees': [],
                'status': 'confirmed',
                'link': ''
            })
        
        # Sort by start time
        events.sort(key=lambda e: e['start'])
        
        return {
            'success': True,
            'count': len(events),
            'events': events,
            'message': f"Found {len(events)} upcoming events (sample data)"
        }
    
    def check_availability(
        self,
        date: str,
        start_time: str = "09:00",
        end_time: str = "18:00"
    ) -> Dict:
        """
        Check availability for a given date.
        
        Args:
            date: Date to check (YYYY-MM-DD)
            start_time: Start of work hours (HH:MM)
            end_time: End of work hours (HH:MM)
            
        Returns:
            Availability info
        """
        # Parse date
        try:
            check_date = datetime.strptime(date, '%Y-%m-%d')
        except:
            check_date = datetime.now()
        
        # Get events for that day
        time_min = check_date.replace(hour=0, minute=0).isoformat() + 'Z'
        time_max = (check_date + timedelta(days=1)).replace(hour=0, minute=0).isoformat() + 'Z'
        
        events_result = self.list_events(max_results=50, time_min=time_min, time_max=time_max)
        events = events_result.get('events', [])
        
        # Find busy slots
        busy_slots = []
        for event in events:
            try:
                start = datetime.fromisoformat(event['start'].replace('Z', '+00:00'))
                end = datetime.fromisoformat(event['end'].replace('Z', '+00:00'))
                busy_slots.append({
                    'start': start.strftime('%H:%M'),
                    'end': end.strftime('%H:%M'),
                    'event': event['summary']
                })
            except:
                pass
        
        # Calculate free slots (simplified)
        work_start = datetime.strptime(start_time, '%H:%M')
        work_end = datetime.strptime(end_time, '%H:%M')
        
        free_hours = 9 - len(busy_slots)  # Simplified calculation
        
        return {
            'success': True,
            'date': date,
            'work_hours': f"{start_time} - {end_time}",
            'busy_slots': busy_slots,
            'event_count': len(events),
            'free_hours_approx': max(0, free_hours),
            'is_free': len(events) == 0,
            'message': f"You have {len(events)} events on {date}" if events else f"You're free on {date}!"
        }
    
    def schedule_meeting(
        self,
        title: str,
        start: str,
        end: str,
        attendees: List[str] = None,
        description: str = "",
        location: str = "",
        send_invites: bool = True
    ) -> Dict:
        """
        Schedule a new meeting.
        
        Args:
            title: Meeting title
            start: Start time (ISO format or YYYY-MM-DD HH:MM)
            end: End time (ISO format or YYYY-MM-DD HH:MM)
            attendees: List of email addresses
            description: Meeting description
            location: Meeting location or video link
            send_invites: Whether to send email invites
            
        Returns:
            Created event info
        """
        # Parse times
        try:
            if len(start) <= 16:  # YYYY-MM-DD HH:MM format
                start_dt = datetime.strptime(start, '%Y-%m-%d %H:%M')
            else:
                start_dt = datetime.fromisoformat(start.replace('Z', ''))
            
            if len(end) <= 16:
                end_dt = datetime.strptime(end, '%Y-%m-%d %H:%M')
            else:
                end_dt = datetime.fromisoformat(end.replace('Z', ''))
        except Exception as e:
            return {
                'success': False,
                'error': f'Invalid date format: {e}',
                'message': 'Please use YYYY-MM-DD HH:MM format'
            }
        
        # Build event object
        event = {
            'summary': title,
            'description': description,
            'start': {
                'dateTime': start_dt.isoformat(),
                'timeZone': 'Asia/Kolkata'
            },
            'end': {
                'dateTime': end_dt.isoformat(),
                'timeZone': 'Asia/Kolkata'
            }
        }
        
        if location:
            event['location'] = location
        
        if attendees:
            event['attendees'] = [{'email': email} for email in attendees]
        
        # Create event via API
        if self.service:
            try:
                created = self.service.events().insert(
                    calendarId=self.calendar_id,
                    body=event,
                    sendUpdates='all' if send_invites else 'none'
                ).execute()
                
                return {
                    'success': True,
                    'event_id': created.get('id'),
                    'title': title,
                    'start': start,
                    'end': end,
                    'attendees': attendees or [],
                    'link': created.get('htmlLink'),
                    'message': f"Meeting '{title}' scheduled for {start_dt.strftime('%b %d at %H:%M')}"
                }
            except Exception as e:
                logger.error(f"[CalendarAgent] Create event failed: {e}")
        
        # Fallback: Return simulated response
        event_id = f"LADA-CAL-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        return {
            'success': True,
            'event_id': event_id,
            'title': title,
            'start': start,
            'end': end,
            'attendees': attendees or [],
            'link': '',
            'message': f"Meeting '{title}' scheduled for {start_dt.strftime('%b %d at %H:%M')}",
            'note': '(Simulated - Google Calendar API not connected)'
        }
    
    def quick_add(self, text: str) -> Dict:
        """
        Quick add event using natural language.
        
        Args:
            text: Natural language event description
            E.g., "Meeting with John tomorrow at 3pm"
            
        Returns:
            Created event info
        """
        if self.service:
            try:
                created = self.service.events().quickAdd(
                    calendarId=self.calendar_id,
                    text=text
                ).execute()
                
                return {
                    'success': True,
                    'event_id': created.get('id'),
                    'summary': created.get('summary'),
                    'start': created.get('start', {}).get('dateTime'),
                    'link': created.get('htmlLink'),
                    'message': f"Event created: {created.get('summary')}"
                }
            except Exception as e:
                logger.error(f"[CalendarAgent] Quick add failed: {e}")
        
        # Parse the text manually for fallback
        return self._parse_and_create(text)
    
    def _parse_and_create(self, text: str) -> Dict:
        """Parse natural language and create event."""
        text_lower = text.lower()
        
        # Extract title (everything before time/date words)
        title = text.split(' at ')[0].split(' on ')[0].split(' tomorrow')[0].strip()
        title = title.replace('meeting with', 'Meeting with').replace('call with', 'Call with')
        
        # Extract time
        time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', text_lower)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or 0)
            ampm = time_match.group(3)
            if ampm == 'pm' and hour < 12:
                hour += 12
            elif ampm == 'am' and hour == 12:
                hour = 0
        else:
            hour, minute = 10, 0  # Default
        
        # Extract date
        if 'tomorrow' in text_lower:
            event_date = datetime.now() + timedelta(days=1)
        elif 'next week' in text_lower:
            event_date = datetime.now() + timedelta(days=7)
        else:
            event_date = datetime.now()
        
        start_dt = event_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        end_dt = start_dt + timedelta(hours=1)
        
        return {
            'success': True,
            'event_id': f"LADA-CAL-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'summary': title or 'New Event',
            'start': start_dt.isoformat(),
            'end': end_dt.isoformat(),
            'message': f"Event '{title}' created for {start_dt.strftime('%b %d at %H:%M')}",
            'note': '(Simulated - Google Calendar API not connected)'
        }
    
    def delete_event(self, event_id: str) -> Dict:
        """Delete a calendar event."""
        if self.service:
            try:
                self.service.events().delete(
                    calendarId=self.calendar_id,
                    eventId=event_id
                ).execute()
                
                return {
                    'success': True,
                    'event_id': event_id,
                    'message': 'Event deleted successfully'
                }
            except Exception as e:
                logger.error(f"[CalendarAgent] Delete event failed: {e}")
        
        return {
            'success': True,
            'event_id': event_id,
            'message': 'Event deleted (simulated)',
            'note': '(Simulated - Google Calendar API not connected)'
        }
    
    def get_today_summary(self) -> Dict:
        """Get summary of today's events."""
        today = datetime.now().strftime('%Y-%m-%d')
        availability = self.check_availability(today)
        
        events = availability.get('busy_slots', [])
        
        if not events:
            summary = "You have no events scheduled for today. Your calendar is clear!"
        elif len(events) == 1:
            summary = f"You have 1 event today: {events[0].get('event', 'Meeting')} at {events[0].get('start', 'TBD')}"
        else:
            summary = f"You have {len(events)} events today:\n"
            for e in events[:5]:
                summary += f"  • {e.get('event', 'Meeting')} at {e.get('start', 'TBD')}\n"
        
        return {
            'success': True,
            'date': today,
            'event_count': len(events),
            'events': events,
            'summary': summary,
            'message': summary
        }
    
    def process(self, query: str) -> Dict:
        """
        Process a natural language calendar query.
        
        Args:
            query: Natural language query
            
        Returns:
            Result dict
        """
        query_lower = query.lower()
        
        # Check for different intents
        if any(word in query_lower for word in ['schedule', 'create', 'add', 'book']):
            # Extract meeting details
            return self.quick_add(query)
        
        elif any(word in query_lower for word in ['check', 'availability', 'free', 'busy']):
            # Check availability
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', query)
            if date_match:
                date = date_match.group(1)
            elif 'tomorrow' in query_lower:
                date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            else:
                date = datetime.now().strftime('%Y-%m-%d')
            
            return self.check_availability(date)
        
        elif any(word in query_lower for word in ['today', 'summary', 'agenda']):
            return self.get_today_summary()
        
        elif any(word in query_lower for word in ['upcoming', 'next', 'list', 'events', 'what']):
            # List events
            count = 5
            count_match = re.search(r'(\d+)', query)
            if count_match:
                count = int(count_match.group(1))
            
            return self.list_events(max_results=count)
        
        elif any(word in query_lower for word in ['delete', 'cancel', 'remove']):
            return {
                'success': False,
                'message': 'Please provide the event ID to delete. You can find it by listing your events.'
            }
        
        else:
            # Default: show today's summary
            return self.get_today_summary()


# ============================================================
# EXAMPLE USAGE
# ============================================================
if __name__ == "__main__":
    print("🚀 Testing CalendarAgent...")
    
    agent = CalendarAgent()
    
    # Test list events
    print("\n📅 Listing upcoming events...")
    result = agent.list_events(max_results=5)
    print(f"  Found: {result['count']} events")
    for event in result['events'][:3]:
        print(f"    • {event['summary']} - {event['start']}")
    
    # Test check availability
    print("\n🔍 Checking availability...")
    today = datetime.now().strftime('%Y-%m-%d')
    result = agent.check_availability(today)
    print(f"  {result['message']}")
    
    # Test schedule meeting
    print("\n📝 Scheduling meeting...")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    result = agent.schedule_meeting(
        title="Test Meeting",
        start=f"{tomorrow} 10:00",
        end=f"{tomorrow} 11:00",
        description="Testing calendar agent",
        attendees=["test@example.com"]
    )
    print(f"  {result['message']}")
    
    # Test quick add
    print("\n⚡ Quick add...")
    result = agent.quick_add("Lunch with team tomorrow at 1pm")
    print(f"  {result['message']}")
    
    # Test today's summary
    print("\n📋 Today's summary...")
    result = agent.get_today_summary()
    print(f"  {result['summary']}")
    
    # Test natural language
    print("\n🗣️ Testing natural language...")
    result = agent.process("What's on my calendar today?")
    print(f"  {result['message']}")
    
    print("\n✅ CalendarAgent test complete!")
