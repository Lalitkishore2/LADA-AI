"""
LADA v7.0 - Google Calendar Integration
View and add calendar events via voice

SECURITY: Uses JSON token storage instead of pickle to prevent code execution vulnerabilities.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Google API imports
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False
    logger.warning("Google API not available - pip install google-api-python-client google-auth-oauthlib")


class GoogleCalendar:
    """
    Google Calendar integration for LADA
    
    Setup:
    1. Go to https://console.cloud.google.com/
    2. Create project, enable Calendar API
    3. Create OAuth 2.0 credentials (Desktop app)
    4. Download credentials.json to C:\JarvisAI\config\
    """
    
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    
    def __init__(self, credentials_path: str = 'config/credentials.json', 
                 token_path: str = 'config/calendar_token.json'):
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self.service = None
        self.creds = None
        self.initialized = False
        self._auth_attempted = False
        
        # Don't authenticate on init - defer until first use to avoid blocking startup
        if not GOOGLE_API_AVAILABLE:
            logger.warning("[!] Google API not available - Calendar features disabled")
    
    def _ensure_authenticated(self) -> bool:
        """
        Ensure we're authenticated before making API calls.
        Only attempts once, and only if valid token exists (no browser popup).
        """
        if self.initialized:
            return True
        
        if self._auth_attempted:
            return False
        
        if not GOOGLE_API_AVAILABLE:
            return False
        
        # Check if credentials file exists
        if not self.credentials_path.exists():
            logger.warning(f"[!] Credentials not found: {self.credentials_path}")
            self._auth_attempted = True
            return False
        
        # Try to load existing valid token (no browser needed)
        if self.token_path.exists():
            try:
                with open(self.token_path, 'r') as token_file:
                    token_data = json.load(token_file)
                
                self.creds = Credentials.from_authorized_user_info(token_data, self.SCOPES)
                
                if self.creds and self.creds.valid:
                    self.service = build('calendar', 'v3', credentials=self.creds)
                    self.initialized = True
                    logger.info("✅ Google Calendar connected")
                    return True
                elif self.creds and self.creds.expired and self.creds.refresh_token:
                    self.creds.refresh(Request())
                    # Save refreshed token as JSON
                    with open(self.token_path, 'w') as token_file:
                        token_file.write(self.creds.to_json())
                    self.service = build('calendar', 'v3', credentials=self.creds)
                    self.initialized = True
                    logger.info("✅ Google Calendar token refreshed")
                    return True
            except Exception as e:
                logger.warning(f"[!] Calendar token invalid: {e}")
        
        # No valid token - require manual auth via settings
        logger.info("[!] Calendar requires authentication - use Settings to connect")
        self._auth_attempted = True
        return False
    
    def authenticate_interactive(self) -> bool:
        """
        Perform interactive OAuth (opens browser).
        Call this from Settings when user wants to connect.
        """
        if not GOOGLE_API_AVAILABLE:
            return False
        
        if not self.credentials_path.exists():
            logger.error(f"Credentials not found: {self.credentials_path}")
            return False
        
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(self.credentials_path), self.SCOPES
            )
            self.creds = flow.run_local_server(port=0)
            
            # Save token as JSON
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_path, 'w') as token_file:
                token_file.write(self.creds.to_json())
            
            # Build service
            self.service = build('calendar', 'v3', credentials=self.creds)
            self.initialized = True
            self._auth_attempted = False
            
            logger.info("✅ Google Calendar connected")
            return True
            
        except Exception as e:
            logger.error(f"Calendar auth failed: {e}")
            return False
    
    def _authenticate(self) -> bool:
        """Legacy method - now just calls _ensure_authenticated"""
        return self._ensure_authenticated()
    
    def get_upcoming_events(self, max_results: int = 10, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get upcoming calendar events
        
        Args:
            max_results: Maximum events to return
            days: How many days ahead to look
            
        Returns:
            List of events with start, end, summary
        """
        # Ensure authenticated before API call
        if not self._ensure_authenticated():
            return []
        
        try:
            now = datetime.utcnow().isoformat() + 'Z'
            end = (datetime.utcnow() + timedelta(days=days)).isoformat() + 'Z'
            
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=now,
                timeMax=end,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            result = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                
                result.append({
                    'id': event['id'],
                    'summary': event.get('summary', 'No title'),
                    'start': start,
                    'end': end,
                    'location': event.get('location', ''),
                    'description': event.get('description', '')
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get events: {e}")
            return []
    
    def get_todays_events(self) -> List[Dict[str, Any]]:
        """Get today's events"""
        if not self._ensure_authenticated():
            return []
        
        try:
            today_start = datetime.now().replace(hour=0, minute=0, second=0).isoformat() + 'Z'
            today_end = datetime.now().replace(hour=23, minute=59, second=59).isoformat() + 'Z'
            
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=today_start,
                timeMax=today_end,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            result = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                result.append({
                    'summary': event.get('summary', 'No title'),
                    'start': start,
                    'location': event.get('location', '')
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get today's events: {e}")
            return []
    
    def add_event(self, summary: str, start_time: datetime, 
                  end_time: datetime = None, description: str = '',
                  location: str = '') -> tuple:
        """
        Add a new calendar event
        
        Args:
            summary: Event title
            start_time: Start datetime
            end_time: End datetime (defaults to 1 hour after start)
            description: Event description
            location: Event location
            
        Returns:
            (success: bool, message: str)
        """
        if not self.initialized:
            return False, "Calendar not connected. Please set up credentials."
        
        if not start_time:
            return False, "Could not determine event time."
        
        try:
            if not end_time:
                end_time = start_time + timedelta(hours=1)
            
            event = {
                'summary': summary,
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': 'Asia/Kolkata',  # IST
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': 'Asia/Kolkata',
                },
            }
            
            if description:
                event['description'] = description
            if location:
                event['location'] = location
            
            result = self.service.events().insert(
                calendarId='primary',
                body=event
            ).execute()
            
            logger.info(f"✅ Event created: {summary}")
            return True, result.get('id')
            
        except Exception as e:
            logger.error(f"Failed to create event: {e}")
            return False, str(e)
    
    def delete_event(self, event_id: str) -> bool:
        """Delete a calendar event"""
        if not self.initialized:
            return False
        
        try:
            self.service.events().delete(
                calendarId='primary',
                eventId=event_id
            ).execute()
            logger.info(f"✅ Event deleted: {event_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete event: {e}")
            return False
    
    def format_events_speech(self, events: List[Dict[str, Any]]) -> str:
        """Format events for voice output"""
        if not events:
            return "You have no upcoming events."
        
        if len(events) == 1:
            event = events[0]
            start = self._parse_datetime(event['start'])
            time_str = start.strftime('%I:%M %p') if start else ''
            return f"You have {event['summary']} at {time_str}."
        
        lines = [f"You have {len(events)} upcoming events:"]
        for event in events[:5]:  # Limit to 5 for speech
            start = self._parse_datetime(event['start'])
            time_str = start.strftime('%I:%M %p') if start else ''
            lines.append(f"{event['summary']} at {time_str}")
        
        return " ".join(lines)
    
    def _parse_datetime(self, dt_str: str) -> Optional[datetime]:
        """Parse datetime string from Google Calendar"""
        try:
            # Try full datetime
            if 'T' in dt_str:
                return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            # Date only
            return datetime.strptime(dt_str, '%Y-%m-%d')
        except:
            return None


# Natural language parsing for adding events
def parse_event_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Parse event details from natural language
    
    Examples:
    - "meeting tomorrow at 3pm"
    - "doctor appointment on January 5th at 10am"
    - "call mom at 6pm"
    """
    import re
    
    text = text.lower()
    now = datetime.now()
    
    # Extract time
    time_pattern = r'at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?'
    time_match = re.search(time_pattern, text)
    
    hour = 9  # Default
    minute = 0
    
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        ampm = time_match.group(3)
        
        if ampm == 'pm' and hour < 12:
            hour += 12
        elif ampm == 'am' and hour == 12:
            hour = 0
    
    # Extract date
    date = now
    
    if 'tomorrow' in text:
        date = now + timedelta(days=1)
    elif 'today' in text:
        date = now
    elif 'next week' in text:
        date = now + timedelta(weeks=1)
    else:
        # Try to find date like "January 5" or "5th"
        months = ['january', 'february', 'march', 'april', 'may', 'june',
                  'july', 'august', 'september', 'october', 'november', 'december']
        
        for i, month in enumerate(months):
            if month in text:
                day_match = re.search(rf'{month}\s+(\d{{1,2}})', text)
                if day_match:
                    day = int(day_match.group(1))
                    date = datetime(now.year, i + 1, day)
                    if date < now:
                        date = datetime(now.year + 1, i + 1, day)
                break
    
    # Set time
    start_time = date.replace(hour=hour, minute=minute, second=0, microsecond=0)
    
    # Extract summary (remove time/date phrases)
    summary = text
    for phrase in ['tomorrow', 'today', 'next week', 'at', 'on', 'am', 'pm']:
        summary = re.sub(rf'\b{phrase}\b', '', summary)
    summary = re.sub(r'\d{1,2}(?::\d{2})?', '', summary)
    summary = re.sub(r'\s+', ' ', summary).strip()
    
    if not summary:
        summary = "Event"
    
    return {
        'summary': summary.title(),
        'start_time': start_time
    }


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Test event parsing
    test_phrases = [
        "meeting tomorrow at 3pm",
        "doctor appointment at 10am",
        "call mom at 6pm today",
        "project deadline on January 15 at 9am"
    ]
    
    print("Testing event parsing:")
    for phrase in test_phrases:
        result = parse_event_from_text(phrase)
        print(f"  '{phrase}' → {result['summary']} at {result['start_time']}")
    
    # Test calendar (requires credentials)
    cal = GoogleCalendar()
    if cal.initialized:
        print("\nToday's events:")
        events = cal.get_todays_events()
        print(cal.format_events_speech(events))
    else:
        print("\nCalendar not initialized - need credentials.json")
