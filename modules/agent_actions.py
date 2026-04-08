"""
LADA v7.0 - Comet-Style Agent Actions
Full control: browser, email, calendar, bookings, task automation

Agent-First Design:
- Operates within the system environment
- Contextual understanding from browsing/system context
- Performs actions: booking, email drafts, summarizing, calendar management
"""

import os
import re
import json
import logging
import subprocess
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger(__name__)

# Try imports for advanced features
try:
    import pyautogui
    PYAUTOGUI_OK = True
except ImportError:
    PYAUTOGUI_OK = False

try:
    from modules.system_control import SystemController
    SYS_OK = True
except:
    SystemController = None
    SYS_OK = False

try:
    from modules.google_calendar import GoogleCalendar
    CALENDAR_OK = True
except:
    GoogleCalendar = None
    CALENDAR_OK = False


class AgentActions:
    """
    Comet-style intelligent agent for task automation
    
    Capabilities:
    - Browser control (open, search, navigate)
    - App launching and control
    - Email drafting (opens email client)
    - Calendar management
    - File operations
    - Web search and information synthesis
    - System control (volume, brightness, etc.)
    """
    
    def __init__(self):
        self.sys = SystemController() if SYS_OK else None
        self.calendar = GoogleCalendar() if CALENDAR_OK else None
        
        # Action patterns for natural language understanding
        self.action_patterns = {
            'open_browser': [
                r'open (?:the )?(?:browser|chrome|firefox|edge)',
                r'go to (?:the )?(?:internet|web)',
                r'browse (?:the )?(?:internet|web)',
            ],
            'search_web': [
                # Only explicit search commands, NOT questions like "what is X"
                # Questions should go to AI for reasoning
                r'^(?:search|google|look up|search for)(?: for)? (.+)',
                r'^search the web for (.+)',
            ],
            'open_url': [
                r'open (?:the )?(?:website|site|page|url) (.+)',
                r'go to (.+\.(?:com|org|net|io|dev|ai|edu))',
                r'navigate to (.+)',
            ],
            'open_youtube': [
                r'(?:open|play|watch)(?: on)? youtube(?: for)? ?(.+)?',
                r'youtube (.+)',
                r'play (?:the )?(?:video|song) (.+)',
            ],
            'open_app': [
                r'open (?:the )?(?:app|application|program) (.+)',
                r'launch (.+)',
                r'start (.+)',
                r'run (.+)',
            ],
            'close_app': [
                r'close (?:the )?(?:app|application|program|window) ?(.+)?',
                r'exit (.+)',
                r'quit (.+)',
            ],
            'send_email': [
                r'(?:send|compose|write|draft)(?: an?)? email(?: to)? ?(.+)?',
                r'email (.+)',
                r'mail (.+)',
            ],
            'add_calendar': [
                r'(?:add|create|schedule|set)(?: an?)? (?:event|meeting|appointment|reminder)(?: (?:for|on|at))? (.+)',
                r'remind me (?:to|about) (.+)',
            ],
            'show_calendar': [
                r'(?:show|what\'?s|check)(?: my)? (?:calendar|schedule|events|agenda)',
                r'what (?:do i have|are my events) (?:today|tomorrow|this week)',
            ],
            'take_screenshot': [
                r'(?:take|capture)(?: a)? screenshot',
                r'screenshot',
                r'screen capture',
            ],
            'control_volume': [
                r'(?:set|change|adjust)(?: the)? volume(?: to)? (\d+)',
                r'volume (\d+)',
                r'mute(?: the)? (?:volume|sound|audio)?',
                r'unmute',
                r'(?:max|full|maximum) volume',
            ],
            'control_media': [
                r'(?:play|pause|resume)(?: the)? (?:music|video|media)?',
                r'(?:next|skip)(?: the)? (?:track|song|video)?',
                r'(?:previous|prev|back)(?: the)? (?:track|song|video)?',
            ],
            'file_search': [
                r'(?:find|search|locate)(?: for)? (?:the )?files?(?: named| called)? (.+)',
                r'where is (?:the )?(?:file|document) (.+)',
                r'find (?:the )?location of (.+?) in (?:the )?(?:file manager|file explorer|explorer)',
                r'where is (.+?) in (?:the )?(?:file manager|file explorer|explorer)',
            ],
            'shutdown': [
                r'(?:shutdown|shut down|power off)(?: the)? (?:computer|pc|system)?',
                r'(?:restart|reboot)(?: the)? (?:computer|pc|system)?',
                r'(?:sleep|hibernate)(?: the)? (?:computer|pc|system)?',
            ],
            'summarize_page': [
                r'(?:summarize|summarise|summary of|tldr)(?: (?:this|the))? ?(?:page|article|website|url)? ?(https?://\S+)?',
                r'(?:summarize|summarise) (https?://\S+)',
            ],
        }
    
    def process(self, command: str) -> Tuple[bool, str]:
        """
        Process a natural language command and execute appropriate action
        
        Returns:
            (handled: bool, response: str)
        """
        cmd = command.lower().strip()
        
        # Check each action category
        for action_type, patterns in self.action_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, cmd, re.IGNORECASE)
                if match:
                    # Get the captured group if any
                    query = match.group(1).strip() if match.groups() and match.group(1) else None
                    
                    # Execute the action
                    return self._execute_action(action_type, query, cmd)
        
        return False, ""
    
    def _execute_action(self, action_type: str, query: Optional[str], full_cmd: str) -> Tuple[bool, str]:
        """Execute the identified action"""
        
        try:
            if action_type == 'open_browser':
                return self._open_browser()
            
            elif action_type == 'search_web':
                return self._search_web(query or full_cmd)
            
            elif action_type == 'open_url':
                return self._open_url(query)
            
            elif action_type == 'open_youtube':
                return self._open_youtube(query)
            
            elif action_type == 'open_app':
                return self._open_app(query)
            
            elif action_type == 'close_app':
                return self._close_app(query)
            
            elif action_type == 'send_email':
                return self._draft_email(query)
            
            elif action_type == 'add_calendar':
                return self._add_calendar_event(query)
            
            elif action_type == 'show_calendar':
                return self._show_calendar()
            
            elif action_type == 'take_screenshot':
                return self._take_screenshot()
            
            elif action_type == 'control_volume':
                return self._control_volume(query, full_cmd)
            
            elif action_type == 'control_media':
                return self._control_media(full_cmd)
            
            elif action_type == 'file_search':
                return self._search_files(query)
            
            elif action_type == 'shutdown':
                return self._system_power(full_cmd)

            elif action_type == 'summarize_page':
                return self.summarize_page(query)
            
        except Exception as e:
            logger.error(f"Action error [{action_type}]: {e}")
            return True, f"Sorry, I encountered an error: {e}"
        
        return False, ""
    
    # ============ Browser Actions ============
    
    def _open_browser(self) -> Tuple[bool, str]:
        """Open default browser"""
        webbrowser.open('https://google.com')
        return True, "Opening your browser."
    
    def _search_web(self, query: str) -> Tuple[bool, str]:
        """Search the web"""
        if not query:
            return True, "What would you like me to search for?"
        
        # Clean the query
        query = re.sub(r'^(search|google|look up|find|for|what is|who is|how to)\s*', '', query, flags=re.I).strip()
        
        url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        webbrowser.open(url)
        return True, f"Searching for '{query}'."
    
    def _open_url(self, url: str) -> Tuple[bool, str]:
        """Open a specific URL"""
        if not url:
            return True, "What website would you like me to open?"
        
        # Add https if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        webbrowser.open(url)
        return True, f"Opening {url}"
    
    def _open_youtube(self, query: Optional[str]) -> Tuple[bool, str]:
        """Open YouTube or search on YouTube"""
        if query:
            url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
            webbrowser.open(url)
            return True, f"Searching YouTube for '{query}'."
        else:
            webbrowser.open('https://www.youtube.com')
            return True, "Opening YouTube."
    
    # ============ App Actions ============
    
    def _open_app(self, app_name: str) -> Tuple[bool, str]:
        """Open an application"""
        if not app_name:
            return True, "Which app would you like me to open?"
        
        app_name = app_name.lower().strip()
        
        # Common Windows apps mapping
        apps = {
            'notepad': 'notepad.exe',
            'calculator': 'calc.exe',
            'paint': 'mspaint.exe',
            'word': 'winword.exe',
            'excel': 'excel.exe',
            'powerpoint': 'powerpnt.exe',
            'outlook': 'outlook.exe',
            'chrome': 'chrome.exe',
            'firefox': 'firefox.exe',
            'edge': 'msedge.exe',
            'explorer': 'explorer.exe',
            'file explorer': 'explorer.exe',
            'files': 'explorer.exe',
            'settings': 'ms-settings:',
            'control panel': 'control.exe',
            'task manager': 'taskmgr.exe',
            'cmd': 'cmd.exe',
            'command prompt': 'cmd.exe',
            'terminal': 'wt.exe',
            'powershell': 'powershell.exe',
            'spotify': 'spotify.exe',
            'discord': 'discord.exe',
            'slack': 'slack.exe',
            'teams': 'teams.exe',
            'vs code': 'code.exe',
            'visual studio code': 'code.exe',
            'vscode': 'code.exe',
        }
        
        # Find matching app
        exe = None
        for key, value in apps.items():
            if key in app_name or app_name in key:
                exe = value
                break
        
        if exe:
            try:
                if exe.startswith('ms-'):
                    # Windows settings URI
                    os.startfile(exe)
                else:
                    subprocess.Popen(exe, shell=True)
                return True, f"Opening {app_name}."
            except Exception as e:
                return True, f"Couldn't open {app_name}. It might not be installed."
        else:
            # Try to open directly
            try:
                subprocess.Popen(app_name, shell=True)
                return True, f"Opening {app_name}."
            except:
                return True, f"I couldn't find an app called '{app_name}'."
    
    def _close_app(self, app_name: Optional[str]) -> Tuple[bool, str]:
        """Close an application"""
        if not app_name:
            # Close current window using Alt+F4
            if PYAUTOGUI_OK:
                pyautogui.hotkey('alt', 'F4')
                return True, "Closing the current window."
            return True, "Which app would you like me to close?"
        
        try:
            subprocess.run(['taskkill', '/IM', f'{app_name}.exe', '/F'], 
                          capture_output=True, shell=True)
            return True, f"Closing {app_name}."
        except:
            return True, f"Couldn't close {app_name}."
    
    # ============ Email Actions ============
    
    def _draft_email(self, recipient: Optional[str]) -> Tuple[bool, str]:
        """Open email client to compose"""
        if recipient:
            # Try to extract email address
            email_match = re.search(r'[\w.-]+@[\w.-]+\.\w+', recipient)
            if email_match:
                mailto = f"mailto:{email_match.group()}"
            else:
                mailto = f"mailto:?to={recipient}"
        else:
            mailto = "mailto:"
        
        webbrowser.open(mailto)
        return True, "Opening email composer."
    
    # ============ Calendar Actions ============
    
    def _add_calendar_event(self, event_text: str) -> Tuple[bool, str]:
        """Add event to calendar"""
        if not self.calendar:
            # Open Google Calendar in browser as fallback
            webbrowser.open('https://calendar.google.com/calendar/r/eventedit')
            return True, "Opening Google Calendar to create an event. (Calendar integration not configured)"
        
        # Parse event details
        parsed = self.calendar.parse_event_from_text(event_text)
        if parsed and parsed.get('summary'):
            success, msg = self.calendar.add_event(
                summary=parsed['summary'],
                start_time=parsed.get('start_time'),
                end_time=parsed.get('end_time'),
                description=parsed.get('description', '')
            )
            if success:
                return True, f"Added '{parsed['summary']}' to your calendar."
            else:
                return True, f"Couldn't add event: {msg}"
        
        return True, "I couldn't understand the event details. Try: 'Add meeting with John tomorrow at 3pm'"
    
    def _show_calendar(self) -> Tuple[bool, str]:
        """Show calendar events"""
        if not self.calendar:
            webbrowser.open('https://calendar.google.com')
            return True, "Opening Google Calendar."
        
        events = self.calendar.get_todays_events()
        if events:
            return True, self.calendar.format_events_speech(events)
        return True, "You have no events scheduled for today."
    
    # ============ Screenshot ============
    
    def _take_screenshot(self) -> Tuple[bool, str]:
        """Take a screenshot"""
        try:
            # Create screenshots directory
            ss_dir = Path("screenshots")
            ss_dir.mkdir(exist_ok=True)
            
            filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            filepath = ss_dir / filename
            
            if PYAUTOGUI_OK:
                screenshot = pyautogui.screenshot()
                screenshot.save(str(filepath))
                return True, f"Screenshot saved as {filename}"
            else:
                # Use Windows Snipping Tool
                subprocess.Popen('snippingtool', shell=True)
                return True, "Opening Snipping Tool for screenshot."
                
        except Exception as e:
            return True, f"Couldn't take screenshot: {e}"
    
    # ============ Volume/Media Control ============
    
    def _control_volume(self, level: Optional[str], full_cmd: str) -> Tuple[bool, str]:
        """Control system volume"""
        if not self.sys:
            return True, "System control not available."
        
        if 'mute' in full_cmd and 'unmute' not in full_cmd:
            self.sys.set_volume(0)
            return True, "Volume muted."
        elif 'unmute' in full_cmd:
            self.sys.set_volume(50)
            return True, "Volume unmuted and set to 50%."
        elif 'max' in full_cmd or 'full' in full_cmd:
            self.sys.set_volume(100)
            return True, "Volume set to maximum."
        elif level:
            try:
                vol = int(level)
                self.sys.set_volume(min(100, max(0, vol)))
                return True, f"Volume set to {vol}%."
            except:
                pass
        
        return True, f"Current volume: {self.sys.get_volume()}%"
    
    def _control_media(self, cmd: str) -> Tuple[bool, str]:
        """Control media playback"""
        if not PYAUTOGUI_OK:
            return True, "Media control requires pyautogui. Install with: pip install pyautogui"
        
        if any(x in cmd for x in ['play', 'pause', 'resume']):
            pyautogui.press('playpause')
            return True, "Play/Pause toggled."
        elif any(x in cmd for x in ['next', 'skip']):
            pyautogui.press('nexttrack')
            return True, "Skipped to next track."
        elif any(x in cmd for x in ['previous', 'prev', 'back']):
            pyautogui.press('prevtrack')
            return True, "Went to previous track."
        
        return False, ""
    
    # ============ File Operations ============
    
    def _search_files(self, query: str) -> Tuple[bool, str]:
        """Search for files"""
        if not query:
            return True, "What file are you looking for?"
        
        # Open Windows search
        if PYAUTOGUI_OK:
            pyautogui.hotkey('win', 's')
            import time
            time.sleep(0.3)
            pyautogui.typewrite(query, interval=0.02)
            return True, f"Searching for files named '{query}'."
        else:
            # Open Explorer search
            subprocess.Popen(f'explorer /root,"search-ms:query={query}&"', shell=True)
            return True, f"Searching for '{query}'."
    
    # ============ System Power ============
    
    def _system_power(self, cmd: str) -> Tuple[bool, str]:
        """Handle shutdown/restart/sleep"""
        if 'restart' in cmd or 'reboot' in cmd:
            return True, "Restart requested. For safety, please use the Start menu to restart your computer."
        elif 'sleep' in cmd:
            # Sleep the system
            subprocess.run('rundll32.exe powrprof.dll,SetSuspendState 0,1,0', shell=True)
            return True, "Putting the computer to sleep."
        elif 'hibernate' in cmd:
            subprocess.run('shutdown /h', shell=True)
            return True, "Hibernating the computer."
        elif 'shutdown' in cmd or 'power off' in cmd:
            return True, "Shutdown requested. For safety, please use the Start menu to shut down your computer."
        
        return False, ""
    
    # ============ Comet-Style Agentic Actions ============
    
    def book_flight(self, details: str) -> Tuple[bool, str]:
        """Open flight booking sites with search"""
        # Extract destination and dates if possible
        webbrowser.open(f"https://www.google.com/travel/flights?q={details.replace(' ', '+')}")
        return True, f"Opening flight search for: {details}"
    
    def book_restaurant(self, details: str) -> Tuple[bool, str]:
        """Open restaurant booking"""
        webbrowser.open(f"https://www.google.com/maps/search/restaurants+{details.replace(' ', '+')}")
        return True, f"Searching for restaurants: {details}"
    
    def compare_products(self, product: str) -> Tuple[bool, str]:
        """Open product comparison"""
        webbrowser.open(f"https://www.google.com/search?q={product.replace(' ', '+')}+price+comparison")
        return True, f"Comparing prices for: {product}"
    
    def summarize_page(self, url: str = None) -> Tuple[bool, str]:
        """Summarize a web page. If no URL given, prompts user to provide one."""
        if not url:
            return True, "Provide a URL to summarize: 'summarize https://example.com/article'"

        try:
            from modules.page_summarizer import get_page_summarizer
            summarizer = get_page_summarizer()
            page = summarizer.extract_page(url)
            if not page.is_valid:
                return True, f"Could not extract content: {page.error}"
            summary = summarizer.summarize_url(url)
            if summary.key_points:
                points = '\n'.join(f"  - {p}" for p in summary.key_points)
                return True, f"Summary of {summary.title}:\n\n{points}"
            elif summary.tldr:
                return True, f"TL;DR: {summary.tldr}"
            return True, f"Summary: {summary.detailed_summary[:500]}"
        except ImportError:
            return True, "Page summarizer module not available. Install requests and beautifulsoup4."
        except Exception as e:
            return True, f"Summarization error: {e}"


# Test
if __name__ == "__main__":
    agent = AgentActions()
    
    # Test commands
    test_commands = [
        "open chrome",
        "search for Python tutorials",
        "open youtube",
        "play video Python basics",
        "set volume to 50",
        "mute",
        "take a screenshot",
        "what's on my calendar today",
    ]
    
    for cmd in test_commands:
        handled, response = agent.process(cmd)
        print(f"'{cmd}' -> {handled}: {response}")
