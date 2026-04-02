"""
LADA v7.0 - Voice Command NLU (Natural Language Understanding))
Optimized for real-time voice control with high accuracy

This module handles ALL voice commands including:
- System control (volume, brightness, mute, etc.)
- App control (open/close apps, browsers)
- File operations (search, create, delete)
- Web browsing (search, open sites, YouTube)
- Media control (play, pause, next, previous)
- System info (battery, CPU, RAM, time, date)
- Power control (shutdown, restart, sleep, lock)
- Weather and calendar integration
"""

import os
import re
import subprocess
import webbrowser
import psutil
import time
import random
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List, Callable
import logging

logger = logging.getLogger(__name__)


class VoiceCommandProcessor:
    """
    Complete voice command processor with AI-enhanced NLU
    
    Designed for real-time voice control with:
    - Fast pattern matching for quick commands
    - AI analysis for complex/contextual commands
    - Compound command support ("do X and then Y")
    - Action execution based on AI understanding
    """
    
    # Personality responses
    ACKNOWLEDGMENTS = [
        "Done.", "Got it.", "On it.", "Right away.", 
        "Consider it done.", "There you go.", "All set."
    ]
    
    # Compound command separators
    SEPARATORS = [' and then ', ' then ', ' and also ', ' also ', ' after that ', ' next ']
    
    def __init__(self, ai_router=None):
        """Initialize voice command processor with optional AI router"""
        # Try to import system controller
        try:
            from modules.system_control import SystemController
            self.system = SystemController()
        except Exception as e:
            self.system = None
            logger.warning(f"SystemController not available: {e}")

        # Use shared AI router if provided, otherwise create one
        self.ai_router = ai_router
        if self.ai_router is None:
            try:
                from lada_ai_router import HybridAIRouter
                self.ai_router = HybridAIRouter()
                logger.info("AI Router created for voice commands")
            except Exception as e:
                self.ai_router = None
                logger.warning(f"AI Router not available: {e}")
        else:
            logger.info("AI Router shared with voice commands")

        # Try to import agent actions
        try:
            from modules.agent_actions import AgentActions
            self.agent = AgentActions()
            logger.info("Agent Actions connected")
        except Exception as e:
            self.agent = None
        
        # Command history for context
        self.history: List[str] = []
        self.last_result: Dict = {}
        
        # Initialize command handlers
        self._init_commands()
        
        logger.info("VoiceCommandProcessor initialized with AI support")
    
    def _init_commands(self):
        """Initialize all command patterns and handlers"""
        # Application paths
        self.apps = {
            'chrome': 'chrome', 'google chrome': 'chrome',
            'firefox': 'firefox', 'mozilla firefox': 'firefox',
            'edge': 'msedge', 'microsoft edge': 'msedge',
            'notepad': 'notepad', 'text editor': 'notepad',
            'calculator': 'calc', 'calc': 'calc',
            'paint': 'mspaint',
            'explorer': 'explorer', 'file explorer': 'explorer', 'files': 'explorer',
            'cmd': 'cmd', 'command prompt': 'cmd',
            'powershell': 'powershell',
            'terminal': 'wt',
            'settings': 'ms-settings:',
            'control panel': 'control',
            'task manager': 'taskmgr',
            'snipping tool': 'snippingtool',
            'spotify': 'spotify',
            'discord': 'discord',
            'teams': 'teams',
            'zoom': 'zoom',
            'vlc': 'vlc',
            'vscode': 'code', 'vs code': 'code', 'visual studio code': 'code',
            'word': 'winword', 'microsoft word': 'winword',
            'excel': 'excel', 'microsoft excel': 'excel',
            'powerpoint': 'powerpnt',
        }
        
        # Websites
        self.websites = {
            'google': 'https://www.google.com',
            'youtube': 'https://www.youtube.com',
            'gmail': 'https://mail.google.com',
            'github': 'https://github.com',
            'twitter': 'https://twitter.com',
            'x': 'https://x.com',
            'facebook': 'https://facebook.com',
            'instagram': 'https://instagram.com',
            'linkedin': 'https://linkedin.com',
            'reddit': 'https://reddit.com',
            'amazon': 'https://amazon.in',
            'flipkart': 'https://flipkart.com',
            'netflix': 'https://netflix.com',
            'hotstar': 'https://hotstar.com',
            'chatgpt': 'https://chat.openai.com',
            'gemini': 'https://gemini.google.com',
            'claude': 'https://claude.ai',
            'stackoverflow': 'https://stackoverflow.com',
            'wikipedia': 'https://wikipedia.org',
        }
    
    def _ack(self) -> str:
        """Get random acknowledgment"""
        return random.choice(self.ACKNOWLEDGMENTS)
    
    def _split_compound(self, command: str) -> List[str]:
        """Split compound commands by separators"""
        parts = [command]
        for sep in self.SEPARATORS:
            new_parts = []
            for part in parts:
                new_parts.extend(part.split(sep))
            parts = new_parts
        # Clean up
        return [p.strip() for p in parts if p.strip()]
    
    def _analyze_with_ai(self, command: str) -> Tuple[bool, str]:
        """
        LADA execution-grade AI command analysis
        
        Analyzes complex commands and breaks them into actionable steps.
        Handles multi-step tasks like "create a file in VS Code" autonomously.
        """
        if not self.ai_router:
            return False, ""

        try:
            # Build execution-focused LADA prompt
            prompt = f"""You are LADA, a local desktop execution assistant with system control.
CRITICAL RULE: YOU MUST ONLY respond with ACTION: lines. NEVER write sentences, explanations, markdown, or any other text.
If you are unsure of the exact action, use: ACTION: answer | <brief one-line reply>

USER COMMAND: "{command}"

== AVAILABLE ACTIONS (respond with ONE action per line, no other text) ==

SINGLE ACTIONS:
- ACTION: open_app | <app_name>
- ACTION: close_app | <app_name>
- ACTION: create_file | <filename> | <optional_path>
- ACTION: create_folder | <folder_name> | <optional_path>
- ACTION: create_file_in_app | <filename> | <app_name>
- ACTION: open_folder | <path>
- ACTION: open_url | <url>
- ACTION: search_web | <query>
- ACTION: set_volume | <0-100>
- ACTION: set_brightness | <0-100>
- ACTION: screenshot | <optional_filename>
- ACTION: run_command | <shell_command>
- ACTION: answer | <response>

MULTI-STEP ACTIONS (for complex commands):
- ACTION: multi_step | step1 >> step2 >> step3

AUTONOMOUS ACTIONS (for complex tasks needing multiple steps):
- ACTION: autonomous | <task_description>

== COMMAND UNDERSTANDING RULES ==

1. "create a file named X in visual studio" = Multi-step:
   - Open VS Code → Create new file → Name it X → Save
   - Use: ACTION: multi_step | open_app:code >> wait:1 >> hotkey:ctrl+n >> wait:0.5 >> type_text:<filename> >> hotkey:ctrl+s

2. "open notepad and type hello" = Multi-step:
   - ACTION: multi_step | open_app:notepad >> wait:1 >> type_text:hello

3. "create a file named test on desktop" = Direct file creation:
   - ACTION: create_file | test.txt | C:\\Users\\{os.environ.get('USERNAME', 'User')}\\Desktop

4. "create a folder named projects on desktop":
   - ACTION: create_folder | projects | C:\\Users\\{os.environ.get('USERNAME', 'User')}\\Desktop

5. Questions or info requests:
   - ACTION: answer | <your intelligent response>

6. Simple app commands:
   - ACTION: open_app | <app_name>

7. "find my location" or "show my location":
   - ACTION: multi_step | open_url:https://maps.google.com >> wait:2

== EXAMPLES ==

"create a file named lalit in visual studio" →
ACTION: multi_step | open_app:code >> wait:2 >> hotkey:ctrl+n >> wait:1 >> hotkey:ctrl+shift+s >> wait:1 >> type_text:lalit.txt >> hotkey:enter

"open chrome and go to youtube" →
ACTION: multi_step | open_app:chrome >> wait:2 >> open_url:https://youtube.com

"what time is it" →
ACTION: answer | The current time is shown in your taskbar.

"create project folder structure" →
ACTION: autonomous | Create a standard project folder with src, tests, docs subfolders

"take a screenshot and save it" →
ACTION: screenshot | screenshot.png

"find my location" →
ACTION: multi_step | open_url:https://maps.google.com >> wait:2

"write hello world to a file on desktop" →
ACTION: create_file | hello.txt | C:\\Users\\{os.environ.get('USERNAME', 'User')}\\Desktop

NOW analyze the USER COMMAND above and respond with ONLY the ACTION line(s).
Do NOT write any other text. Just the ACTION: line(s).
Be INTELLIGENT - understand INTENT, not just keywords.
For multi-step tasks, chain steps with >>."""

            # Query AI
            response = self.ai_router.query(prompt)
            if not response:
                return False, ""
            
            # Parse AI response - extract ACTION if present anywhere in response
            response = response.strip()
            
            # Look for ACTION: anywhere in the response
            import re
            action_match = re.search(r'ACTION:\s*([^\n]+)', response)
            if action_match:
                action_line = "ACTION: " + action_match.group(1)
                return self._execute_ai_action(action_line)
            elif "ACTION:" in response:
                # Fallback: find first line with ACTION
                for line in response.split('\n'):
                    if 'ACTION:' in line:
                        return self._execute_ai_action(line)
            
            # AI gave a direct answer - clean it up
            # Remove any "I am LADA" intro if present
            clean_response = response
            if "here" in response.lower() and ":" in response:
                # Take everything after the intro
                parts = response.split('\n')
                clean_parts = [p for p in parts if p.strip() and 'ACTION' not in p]
                clean_response = ' '.join(clean_parts)
            return True, clean_response
                
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return False, ""
    
    def _execute_ai_action(self, action_str: str) -> Tuple[bool, str]:
        """Execute an action parsed by AI - IRON MAN LEVEL"""
        try:
            # Parse: ACTION: type | params
            parts = action_str.replace("ACTION:", "").strip().split("|")
            action_type = parts[0].strip().lower()
            params = [p.strip() for p in parts[1:]] if len(parts) > 1 else []
            
            logger.info(f"[JARVIS] Executing: {action_type} with params: {params}")
            
            # === MULTI-STEP ACTIONS (Iron Man level) ===
            if action_type == "multi_step":
                steps = params[0].split(">>") if params else []
                return self._execute_multi_step(steps)
            
            # === AUTONOMOUS ACTIONS (Comet-style) ===
            elif action_type == "autonomous":
                task = params[0] if params else ""
                return self._execute_autonomous(task)
            
            # === CREATE FILE IN APP (e.g., VS Code) ===
            elif action_type == "create_file_in_app":
                filename = params[0] if params else "untitled.txt"
                app_name = params[1] if len(params) > 1 else "code"
                return self._create_file_in_app(filename, app_name)
            
            # === CREATE FILE (direct) ===
            elif action_type == "create_file":
                filename = params[0] if params else "untitled.txt"
                path = params[1] if len(params) > 1 else os.path.expanduser("~\\Desktop")
                return self._create_file_direct(filename, path)

            # === CREATE FOLDER ===
            elif action_type == "create_folder":
                folder_name = params[0] if params else "New Folder"
                parent_path = params[1] if len(params) > 1 else os.path.expanduser("~\\Desktop")
                try:
                    full_path = os.path.join(parent_path.strip(), folder_name.strip())
                    os.makedirs(full_path, exist_ok=True)
                    return True, f"Folder '{folder_name}' created at {parent_path}."
                except Exception as e:
                    return True, f"Could not create folder: {e}"
            
            # === CLOSE APP ===
            elif action_type == "close_app":
                app_name = params[0] if params else ""
                return self._close_app(app_name)
            
            # === SCREENSHOT ===
            elif action_type == "screenshot":
                filename = params[0] if params else None
                return self._take_screenshot(filename)
            
            elif action_type == "open_app":
                app_name = params[0] if params else ""
                folder_path = None
                if len(params) > 1 and "with_path" in params[1]:
                    folder_path = params[1].replace("with_path", "").strip()
                return self._ai_open_app(app_name, folder_path)
            
            elif action_type == "search_web":
                query = params[0] if params else ""
                if query:
                    return False, ""  # Let main AI handle with web search
                return False, ""
            
            elif action_type == "open_browser_search":
                query = params[0] if params else ""
                import webbrowser
                if query:
                    webbrowser.open(f"https://www.google.com/search?q={query}")
                    return True, f"Opening browser to search for: {query}"
                else:
                    webbrowser.open("https://www.google.com")
                    return True, "Opening Google."
            
            elif action_type == "open_url":
                url = params[0] if params else ""
                import webbrowser
                webbrowser.open(url)
                return True, f"Opening {url}"
            
            elif action_type == "set_volume":
                level = int(params[0]) if params else 50
                if self.system:
                    self.system.set_volume(level)
                    return True, f"Volume set to {level}%"
            
            elif action_type == "set_brightness":
                level = int(params[0]) if params else 50
                if self.system:
                    self.system.set_brightness(level)
                    return True, f"Brightness set to {level}%"
            
            elif action_type == "open_folder":
                path = params[0] if params else ""
                os.startfile(path)
                return True, f"Opening folder: {path}"
            
            elif action_type == "run_command":
                cmd = params[0] if params else ""
                subprocess.Popen(cmd, shell=True)
                return True, f"Running: {cmd}"
            
            elif action_type == "answer":
                # Replace placeholders
                answer = params[0] if params else "I understand."
                answer = answer.replace("{{TIME}}", datetime.now().strftime("%I:%M %p"))
                answer = answer.replace("{{DATE}}", datetime.now().strftime("%B %d, %Y"))
                return True, answer
            
            return False, ""
            
        except Exception as e:
            logger.error(f"Failed to execute AI action: {e}")
            return False, ""
    
    def _execute_multi_step(self, steps: List[str]) -> Tuple[bool, str]:
        """Execute multi-step Iron Man level command sequence"""
        try:
            import pyautogui
            pyautogui.FAILSAFE = False
            
            executed = []
            for step in steps:
                step = step.strip()
                if not step:
                    continue
                
                logger.info(f"[JARVIS] Step: {step}")
                
                if step.startswith("open_app:"):
                    app = step.replace("open_app:", "").strip()
                    self._ai_open_app(app)
                    executed.append(f"Opened {app}")
                    
                elif step.startswith("wait:"):
                    seconds = float(step.replace("wait:", "").strip())
                    time.sleep(seconds)
                    
                elif step.startswith("hotkey:"):
                    keys = step.replace("hotkey:", "").strip()
                    key_list = [k.strip() for k in keys.split("+")]
                    pyautogui.hotkey(*key_list)
                    executed.append(f"Pressed {keys}")
                    
                elif step.startswith("type_text:"):
                    text = step.replace("type_text:", "").strip()
                    pyautogui.typewrite(text, interval=0.05)
                    executed.append(f"Typed '{text}'")
                    
                elif step.startswith("press:"):
                    key = step.replace("press:", "").strip()
                    pyautogui.press(key)
                    executed.append(f"Pressed {key}")
                    
                elif step.startswith("open_url:"):
                    url = step.replace("open_url:", "").strip()
                    webbrowser.open(url)
                    executed.append(f"Opened {url}")
                    
                elif step.startswith("click:"):
                    coords = step.replace("click:", "").strip()
                    if "," in coords:
                        x, y = map(int, coords.split(","))
                        pyautogui.click(x, y)
                        executed.append(f"Clicked at ({x}, {y})")
                    
            return True, f"Done! {', '.join(executed)}" if executed else "Task completed."
            
        except Exception as e:
            logger.error(f"Multi-step execution failed: {e}")
            return False, f"Error: {e}"
    
    def _execute_autonomous(self, task: str) -> Tuple[bool, str]:
        """Execute autonomous Comet-style task"""
        try:
            # Try to use Comet agent if available
            try:
                from modules.agents.comet_agent import CometAgent
                comet = CometAgent()
                result = comet.execute_task(task)
                return True, result
            except:
                pass
            
            # Fallback: Break down task and execute
            logger.info(f"[JARVIS] Autonomous task: {task}")
            
            # Simple autonomous tasks
            if "folder" in task.lower() and "create" in task.lower():
                # Create folder structure
                desktop = Path(os.path.expanduser("~\\Desktop"))
                project_dir = desktop / "NewProject"
                project_dir.mkdir(exist_ok=True)
                (project_dir / "src").mkdir(exist_ok=True)
                (project_dir / "tests").mkdir(exist_ok=True)
                (project_dir / "docs").mkdir(exist_ok=True)
                return True, f"Created project structure at {project_dir}"
            
            return True, f"Autonomous task queued: {task}"
            
        except Exception as e:
            logger.error(f"Autonomous execution failed: {e}")
            return False, f"Error: {e}"
    
    def _create_file_in_app(self, filename: str, app_name: str) -> Tuple[bool, str]:
        """Create a file inside an application (e.g., VS Code)"""
        try:
            import pyautogui
            pyautogui.FAILSAFE = False
            
            # Ensure filename has extension
            if "." not in filename:
                filename = f"{filename}.txt"
            
            logger.info(f"[JARVIS] Creating {filename} in {app_name}")
            
            # Open the app first
            self._ai_open_app(app_name)
            time.sleep(2)  # Wait for app to load
            
            if "code" in app_name.lower() or "visual" in app_name.lower():
                # VS Code workflow
                pyautogui.hotkey("ctrl", "n")  # New file
                time.sleep(0.5)
                pyautogui.hotkey("ctrl", "shift", "s")  # Save As
                time.sleep(1)
                pyautogui.typewrite(filename, interval=0.05)
                time.sleep(0.3)
                pyautogui.press("enter")
                return True, f"Created {filename} in VS Code"
                
            elif "notepad" in app_name.lower():
                # Notepad workflow
                time.sleep(0.5)
                pyautogui.hotkey("ctrl", "s")  # Save
                time.sleep(0.5)
                pyautogui.typewrite(filename, interval=0.05)
                pyautogui.press("enter")
                return True, f"Created {filename} in Notepad"
                
            else:
                # Generic: just open and try save
                time.sleep(1)
                pyautogui.hotkey("ctrl", "s")
                time.sleep(0.5)
                pyautogui.typewrite(filename, interval=0.05)
                pyautogui.press("enter")
                return True, f"Created {filename} in {app_name}"
                
        except Exception as e:
            logger.error(f"Create file in app failed: {e}")
            return False, f"Couldn't create file: {e}"
    
    def _create_file_direct(self, filename: str, path: str) -> Tuple[bool, str]:
        """Create file directly on filesystem"""
        try:
            # Replace user placeholder
            path = path.replace("{{USER}}", os.getlogin())
            path = os.path.expanduser(path.replace("~", "~"))
            
            if "." not in filename:
                filename = f"{filename}.txt"
            
            filepath = Path(path) / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.touch()
            
            logger.info(f"[JARVIS] Created file: {filepath}")
            return True, f"Created {filename} at {path}"
            
        except Exception as e:
            logger.error(f"Create file failed: {e}")
            return False, f"Couldn't create file: {e}"
    
    def _close_app(self, app_name: str) -> Tuple[bool, str]:
        """Close an application"""
        try:
            app_map = {
                'chrome': 'chrome.exe', 'notepad': 'notepad.exe',
                'code': 'Code.exe', 'vscode': 'Code.exe',
                'firefox': 'firefox.exe', 'edge': 'msedge.exe',
                'explorer': 'explorer.exe', 'cmd': 'cmd.exe',
            }
            
            exe = app_map.get(app_name.lower(), f"{app_name}.exe")
            subprocess.run(f"taskkill /IM {exe} /F", shell=True, capture_output=True)
            return True, f"Closed {app_name}"
            
        except Exception as e:
            return False, f"Couldn't close {app_name}: {e}"
    
    def _take_screenshot(self, filename: str = None) -> Tuple[bool, str]:
        """Take a screenshot"""
        try:
            import pyautogui
            
            if not filename:
                filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            
            screenshot_dir = Path(os.path.expanduser("~\\Pictures\\Screenshots"))
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            
            filepath = screenshot_dir / filename
            screenshot = pyautogui.screenshot()
            screenshot.save(str(filepath))
            
            return True, f"Screenshot saved to {filepath}"
            
        except Exception as e:
            return False, f"Screenshot failed: {e}"
    
    def _ai_open_app(self, app_name: str, folder_path: Optional[str] = None) -> Tuple[bool, str]:
        """Open app with optional folder context (AI-directed)"""
        app_commands = {
            'code': 'code', 'vscode': 'code', 'vs code': 'code', 'visual studio code': 'code',
            'chrome': 'chrome', 'firefox': 'firefox', 'edge': 'msedge',
            'notepad': 'notepad', 'explorer': 'explorer', 'terminal': 'wt',
            'cmd': 'cmd', 'powershell': 'powershell',
        }
        
        cmd = None
        for name, exe in app_commands.items():
            if name in app_name.lower():
                cmd = exe
                break
        
        if not cmd:
            cmd = app_name  # Try direct
        
        try:
            if folder_path and cmd == 'code':
                # VS Code with folder
                subprocess.Popen(f'code "{folder_path}"', shell=True)
                return True, f"Opening VS Code in {folder_path}"
            elif folder_path and cmd == 'explorer':
                os.startfile(folder_path)
                return True, f"Opening folder: {folder_path}"
            else:
                subprocess.Popen(cmd, shell=True)
                return True, f"Opening {app_name}"
        except:
            return False, f"Couldn't open {app_name}"
    
    def process(self, command: str) -> Tuple[bool, str]:
        """
        Process a voice command with AI analysis support
        
        Args:
            command: Voice transcription text
            
        Returns:
            (handled: bool, response: str)
            - handled=True: Command was executed, response contains result
            - handled=False: Not handled, forward to chat AI
        """
        if not command:
            return False, ""
        
        # Normalize command
        cmd = command.lower().strip()
        
        # Store in history
        self.history.append(cmd)
        if len(self.history) > 20:
            self.history = self.history[-20:]
        
        # Check for compound commands
        sub_commands = self._split_compound(cmd)
        
        if len(sub_commands) > 1:
            # Handle multiple commands
            responses = []
            for sub_cmd in sub_commands:
                handled, response = self._process_single(sub_cmd)
                if handled:
                    responses.append(response)
            if responses:
                return True, " ".join(responses)
            # If none handled, try AI for the full command
            return self._analyze_with_ai(command)
        
        # Single command processing
        handled, response = self._process_single(cmd)
        if handled:
            return handled, response
        
        # If not handled by patterns, try AI analysis
        ai_handled, ai_response = self._analyze_with_ai(command)
        if ai_handled:
            return True, ai_response
        
        # Not a system command, will be forwarded to chat AI
        return False, ""
    
    def _process_single(self, cmd: str) -> Tuple[bool, str]:
        """Process a single command through pattern handlers"""
        handlers = [
            self._handle_stop_listening,  # Voice mode control - first priority
            self._handle_time_date,
            self._handle_volume,
            self._handle_brightness,
            self._handle_battery,
            self._handle_system_info,
            self._handle_open_app,
            self._handle_close_app,
            self._handle_web_search,
            self._handle_youtube,
            self._handle_website,
            self._handle_screenshot,
            self._handle_screen_read,  # Screen reading/analysis
            self._handle_media,
            self._handle_power,
            self._handle_lock_sleep,
            self._handle_greetings,
            self._handle_file_ops,
        ]
        
        for handler in handlers:
            try:
                result = handler(cmd)
                if result[0]:  # handled
                    self.last_result = {'command': cmd, 'response': result[1]}
                    return result
            except Exception as e:
                logger.error(f"Handler error: {e}")
                continue
        
        # Not a system command
        return False, ""
    
    # ============ VOICE MODE CONTROL ============
    
    def _handle_stop_listening(self, cmd: str) -> Tuple[bool, str]:
        """Handle stop/pause/sleep commands for voice mode"""
        stop_patterns = [
            'stop listening', 'stop voice', 'pause listening', 'pause voice',
            'go to sleep', 'sleep mode', 'voice off', 'mic off', 'mute voice',
            'stop', 'pause', 'quiet', 'silence', 'shut up', 'be quiet',
            'exit voice', 'close voice', 'end voice', 'voice mode off',
            'thats all', "that's all", 'thank you', 'thanks', 'bye', 'goodbye',
            'stop talking', 'enough', 'ok stop', 'okay stop'
        ]
        
        if any(p in cmd for p in stop_patterns):
            responses = [
                "Going quiet. Tap the mic when you need me.",
                "Voice mode paused. I'll be here when you need me.",
                "Taking a break. Just tap the mic to continue.",
                "Alright, going silent. Wake me anytime.",
                "Got it. Voice mode off."
            ]
            import random
            return True, "__STOP_LISTENING__" + random.choice(responses)
        
        return False, ""
    
    # ============ TIME & DATE ============
    
    def _handle_time_date(self, cmd: str) -> Tuple[bool, str]:
        """Handle time and date queries"""
        now = datetime.now()
        
        # Time queries (handle apostrophe variations)
        time_patterns = [
            'what time', 'current time', 'tell me the time', 
            'what is the time', 'whats the time', "what's the time", 
            'time please', 'show time', 'display time', 'the time'
        ]
        if any(p in cmd for p in time_patterns):
            time_str = now.strftime("%I:%M %p")
            return True, f"It's {time_str}."
        
        # Date queries (handle apostrophe variations)
        date_patterns = [
            'what date', "today's date", 'todays date', 'what is the date',
            'whats the date', "what's the date", 'what day', 'which day', 
            'current date', 'date today', 'the date'
        ]
        if any(p in cmd for p in date_patterns):
            date_str = now.strftime("%A, %B %d, %Y")
            return True, f"Today is {date_str}."
        
        return False, ""
    
    # ============ VOLUME CONTROL ============
    
    def _handle_volume(self, cmd: str) -> Tuple[bool, str]:
        """Handle volume control commands"""
        if not self.system:
            return False, ""
        
        # Set specific volume
        if any(x in cmd for x in ['set volume', 'volume to', 'change volume', 'make volume', 'volume at']):
            match = re.search(r'(\d+)', cmd)
            if match:
                level = min(100, max(0, int(match.group(1))))
                result = self.system.set_volume(level)
                if result.get('success'):
                    return True, f"{self._ack()} Volume set to {level}%."
                return True, f"Couldn't change volume: {result.get('error', 'unknown error')}"
        
        # Mute
        if any(x in cmd for x in ['mute', 'mute volume', 'silence', 'quiet']):
            self.system.set_volume(0)
            return True, "Volume muted."
        
        # Unmute / Max volume
        if any(x in cmd for x in ['unmute', 'full volume', 'max volume', 'maximum volume', '100 volume']):
            self.system.set_volume(100)
            return True, "Volume set to maximum."
        
        # Volume up
        if any(x in cmd for x in ['volume up', 'increase volume', 'louder', 'turn up', 'raise volume']):
            vol = self.system.get_volume()
            current = vol.get('volume', 50) if isinstance(vol, dict) else 50
            new_vol = min(100, current + 10)
            self.system.set_volume(new_vol)
            return True, f"Volume increased to {new_vol}%."
        
        # Volume down
        if any(x in cmd for x in ['volume down', 'decrease volume', 'quieter', 'lower volume', 'turn down', 'softer']):
            vol = self.system.get_volume()
            current = vol.get('volume', 50) if isinstance(vol, dict) else 50
            new_vol = max(0, current - 10)
            self.system.set_volume(new_vol)
            return True, f"Volume decreased to {new_vol}%."
        
        # Current volume
        if any(x in cmd for x in ['what is the volume', 'current volume', 'volume level', 'how loud', 'check volume']):
            vol = self.system.get_volume()
            current = vol.get('volume', 'unknown') if isinstance(vol, dict) else vol
            return True, f"Volume is at {current}%."
        
        return False, ""
    
    # ============ BRIGHTNESS CONTROL ============
    
    def _handle_brightness(self, cmd: str) -> Tuple[bool, str]:
        """Handle brightness control"""
        if not self.system:
            return False, ""
        
        # Set brightness
        if any(x in cmd for x in ['set brightness', 'brightness to', 'change brightness', 'screen brightness']):
            match = re.search(r'(\d+)', cmd)
            if match:
                level = min(100, max(0, int(match.group(1))))
                result = self.system.set_brightness(level)
                if result.get('success'):
                    return True, f"{self._ack()} Brightness set to {level}%."
                return True, f"Couldn't change brightness: {result.get('error', '')}"
        
        # Brightness up/down
        if any(x in cmd for x in ['brightness up', 'increase brightness', 'brighter']):
            result = self.system.set_brightness(80)  # Increase to 80%
            return True, "Brightness increased."
        
        if any(x in cmd for x in ['brightness down', 'decrease brightness', 'dimmer', 'dim screen']):
            result = self.system.set_brightness(40)  # Decrease to 40%
            return True, "Brightness decreased."
        
        return False, ""
    
    # ============ BATTERY & SYSTEM INFO ============
    
    def _handle_battery(self, cmd: str) -> Tuple[bool, str]:
        """Handle battery status queries"""
        if any(x in cmd for x in ['battery', 'power status', 'battery level', 'charge', 'charging']):
            try:
                battery = psutil.sensors_battery()
                if battery:
                    percent = battery.percent
                    plugged = "plugged in" if battery.power_plugged else "on battery"
                    if battery.secsleft > 0 and not battery.power_plugged:
                        mins = battery.secsleft // 60
                        hrs = mins // 60
                        mins = mins % 60
                        if hrs > 0:
                            time_left = f", about {hrs} hours {mins} minutes remaining"
                        else:
                            time_left = f", about {mins} minutes remaining"
                    else:
                        time_left = ""
                    return True, f"Battery is at {percent}%, {plugged}{time_left}."
                return True, "This appears to be a desktop PC without a battery."
            except:
                return True, "Battery information unavailable."
        return False, ""
    
    def _handle_system_info(self, cmd: str) -> Tuple[bool, str]:
        """Handle system info queries"""
        # CPU
        if any(x in cmd for x in ['cpu usage', 'processor', 'cpu status', 'how is cpu']):
            cpu = psutil.cpu_percent(interval=0.5)
            return True, f"CPU usage is at {cpu}%."
        
        # Memory/RAM
        if any(x in cmd for x in ['memory usage', 'ram', 'memory status', 'how much ram', 'ram usage']):
            mem = psutil.virtual_memory()
            available_gb = mem.available / (1024**3)
            return True, f"Memory usage is at {mem.percent}%. {available_gb:.1f} GB available."
        
        # Disk/Storage
        if any(x in cmd for x in ['disk space', 'storage', 'disk usage', 'how much space', 'free space']):
            disk = psutil.disk_usage('C:\\')
            free_gb = disk.free / (1024**3)
            return True, f"Disk usage is at {disk.percent}%. {free_gb:.0f} GB free."
        
        # Full system status
        if any(x in cmd for x in ['system status', 'system info', 'pc status', 'computer status', 'system health']):
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('C:\\')
            try:
                battery = psutil.sensors_battery()
                bat_str = f", Battery: {battery.percent}%" if battery else ""
            except:
                bat_str = ""
            return True, f"CPU: {cpu}%, RAM: {mem.percent}%, Disk: {disk.percent}%{bat_str}."
        
        return False, ""
    
    # ============ OPEN/CLOSE APPS ============
    
    def _handle_open_app(self, cmd: str) -> Tuple[bool, str]:
        """Handle opening applications"""
        if not any(x in cmd for x in ['open', 'launch', 'start', 'run']):
            return False, ""
        
        # Extract target after command word
        for prefix in ['open ', 'launch ', 'start ', 'run ']:
            if prefix in cmd:
                target = cmd.split(prefix, 1)[-1].strip()
                break
        else:
            return False, ""
        
        # Remove common suffixes
        target = target.replace(' please', '').replace(' for me', '').strip()
        
        # Check if it's a website first
        for site, url in self.websites.items():
            if site in target:
                webbrowser.open(url)
                return True, f"{self._ack()} Opening {site}."
        
        # Check apps
        for app_name, app_cmd in self.apps.items():
            if app_name in target or target in app_name:
                try:
                    if app_cmd.startswith('ms-'):  # Windows settings URI
                        os.startfile(app_cmd)
                    else:
                        subprocess.Popen(app_cmd, shell=True, 
                                       stdout=subprocess.DEVNULL, 
                                       stderr=subprocess.DEVNULL)
                    return True, f"{self._ack()} Opening {app_name}."
                except Exception as e:
                    return True, f"Couldn't open {app_name}: {e}"
        
        # Try as generic command
        try:
            subprocess.Popen(target, shell=True, 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
            return True, f"{self._ack()} Opening {target}."
        except:
            return True, f"I couldn't find '{target}'. Try being more specific."
    
    def _handle_close_app(self, cmd: str) -> Tuple[bool, str]:
        """Handle closing applications"""
        if not any(x in cmd for x in ['close', 'quit', 'exit', 'kill', 'stop']):
            return False, ""
        
        # Extract target
        for prefix in ['close ', 'quit ', 'exit ', 'kill ', 'stop ']:
            if prefix in cmd:
                target = cmd.split(prefix, 1)[-1].strip()
                break
        else:
            return False, ""
        
        # Map common names to process names
        process_map = {
            'chrome': 'chrome.exe',
            'firefox': 'firefox.exe',
            'edge': 'msedge.exe',
            'notepad': 'notepad.exe',
            'spotify': 'Spotify.exe',
            'discord': 'Discord.exe',
            'word': 'WINWORD.EXE',
            'excel': 'EXCEL.EXE',
            'vlc': 'vlc.exe',
            'vscode': 'Code.exe',
            'vs code': 'Code.exe',
        }
        
        process_name = process_map.get(target, f"{target}.exe")
        
        try:
            os.system(f'taskkill /f /im {process_name}')
            return True, f"{self._ack()} Closed {target}."
        except:
            return True, f"Couldn't close {target}."
    
    # ============ WEB & YOUTUBE ============
    
    def _handle_web_search(self, cmd: str) -> Tuple[bool, str]:
        """Handle web searches"""
        patterns = [
            (r'(?:google|search|look up|search for|find)\s+(.+)', 'google'),
            (r'(?:bing)\s+(.+)', 'bing'),
        ]
        
        for pattern, engine in patterns:
            match = re.search(pattern, cmd)
            if match:
                query = match.group(1).strip()
                # Remove common suffixes
                query = query.replace(' on google', '').replace(' for me', '').strip()
                
                if engine == 'google':
                    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
                else:
                    url = f"https://www.bing.com/search?q={query.replace(' ', '+')}"
                
                webbrowser.open(url)
                return True, f"{self._ack()} Searching for '{query}'."
        
        return False, ""
    
    def _handle_youtube(self, cmd: str) -> Tuple[bool, str]:
        """Handle YouTube commands"""
        if 'youtube' not in cmd:
            return False, ""
        
        # Play/search on YouTube
        patterns = [
            r'(?:play|search|find|watch)\s+(.+)\s+on youtube',
            r'youtube\s+(.+)',
            r'(?:play|search|watch)\s+(.+)\s+(?:video|song)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, cmd)
            if match:
                query = match.group(1).strip()
                url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
                webbrowser.open(url)
                return True, f"{self._ack()} Searching YouTube for '{query}'."
        
        # Just open YouTube
        if any(x in cmd for x in ['open youtube', 'go to youtube', 'launch youtube']):
            webbrowser.open('https://www.youtube.com')
            return True, f"{self._ack()} Opening YouTube."
        
        return False, ""
    
    def _handle_website(self, cmd: str) -> Tuple[bool, str]:
        """Handle opening websites"""
        # Pattern: go to [website] or open [website].com
        patterns = [
            r'(?:go to|open|browse to|navigate to|visit)\s+([a-zA-Z0-9]+)(?:\.com|\.org|\.net|\.in)?',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, cmd)
            if match:
                site = match.group(1).lower().strip()
                
                # Check known sites
                if site in self.websites:
                    webbrowser.open(self.websites[site])
                    return True, f"{self._ack()} Opening {site}."
                
                # Try as domain
                url = f"https://www.{site}.com"
                webbrowser.open(url)
                return True, f"{self._ack()} Opening {site}."
        
        return False, ""
    
    # ============ SCREENSHOT ============
    
    def _handle_screenshot(self, cmd: str) -> Tuple[bool, str]:
        """Handle screenshot commands"""
        if any(x in cmd for x in ['screenshot', 'screen shot', 'capture screen', 'take screenshot', 'screen capture']):
            try:
                # Use Windows built-in
                screenshot_path = Path.home() / 'Pictures' / 'Screenshots'
                screenshot_path.mkdir(parents=True, exist_ok=True)
                
                filename = screenshot_path / f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                
                # Try with PIL if available
                try:
                    from PIL import ImageGrab
                    img = ImageGrab.grab()
                    img.save(str(filename))
                    return True, f"Screenshot saved to {filename.name}."
                except ImportError:
                    # Fallback to snipping tool
                    subprocess.Popen('snippingtool /clip', shell=True)
                    return True, "Snipping tool opened. Select area to capture."
            except Exception as e:
                return True, f"Couldn't take screenshot: {e}"
        return False, ""
    
    # ============ SCREEN READ/ANALYSIS ============
    
    def _handle_screen_read(self, cmd: str) -> Tuple[bool, str]:
        """Handle screen reading and analysis commands"""
        screen_patterns = [
            'read screen', 'what is on screen', "what's on screen", 'whats on screen',
            'read my screen', 'analyze screen', 'describe screen', 'look at screen',
            'what do you see', 'read this', 'what is this', 'read the screen',
            'screen content', 'read display', 'what am i looking at',
            'read window', 'read active window', 'what window is open'
        ]
        
        if any(p in cmd for p in screen_patterns):
            try:
                from PIL import ImageGrab
                import pyautogui
                
                # Get active window info
                try:
                    import ctypes
                    user32 = ctypes.windll.user32
                    hwnd = user32.GetForegroundWindow()
                    length = user32.GetWindowTextLengthW(hwnd)
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    active_window = buff.value
                except:
                    active_window = "Unknown"
                
                # Take screenshot
                screenshot = ImageGrab.grab()
                
                # Get screen dimensions
                width, height = screenshot.size
                
                # Try to get text from screen using OCR
                screen_text = ""
                try:
                    import pytesseract
                    screen_text = pytesseract.image_to_string(screenshot)
                except ImportError:
                    screen_text = "(OCR not available - install pytesseract)"
                except Exception as e:
                    screen_text = f"(Could not read text: {e})"
                
                # Build response
                response = f"Active window: {active_window}. Screen size: {width}x{height}."
                
                if screen_text and len(screen_text.strip()) > 10:
                    # Truncate if too long
                    text_preview = screen_text.strip()[:300]
                    response += f" Screen text: {text_preview}"
                
                return True, response
                
            except ImportError:
                return True, "Screen reading requires PIL. Install with: pip install Pillow"
            except Exception as e:
                return True, f"Couldn't read screen: {e}"
        
        # Get active window title
        if any(p in cmd for p in ['active window', 'current window', 'which window', 'what app']):
            try:
                import ctypes
                user32 = ctypes.windll.user32
                hwnd = user32.GetForegroundWindow()
                length = user32.GetWindowTextLengthW(hwnd)
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                return True, f"Active window: {buff.value}"
            except:
                return True, "Couldn't get active window."
        
        # Mouse position
        if any(p in cmd for p in ['mouse position', 'cursor position', 'where is cursor', 'where is mouse']):
            try:
                import pyautogui
                x, y = pyautogui.position()
                return True, f"Mouse is at position {x}, {y}."
            except:
                return True, "Couldn't get mouse position."
        
        # Click at position
        click_match = re.search(r'click (?:at |position )?(\d+)[,\s]+(\d+)', cmd)
        if click_match:
            try:
                import pyautogui
                x, y = int(click_match.group(1)), int(click_match.group(2))
                pyautogui.click(x, y)
                return True, f"Clicked at {x}, {y}."
            except:
                return True, "Couldn't click at that position."
        
        # Type text
        type_match = re.search(r'type ["\']?(.+?)["\']?$', cmd)
        if type_match:
            try:
                import pyautogui
                text = type_match.group(1)
                pyautogui.typewrite(text, interval=0.02)
                return True, f"Typed: {text}"
            except:
                return True, "Couldn't type that text."
        
        return False, ""
    
    # ============ MEDIA CONTROL ============
    
    def _handle_media(self, cmd: str) -> Tuple[bool, str]:
        """Handle media playback control"""
        try:
            import ctypes
            
            # Virtual key codes for media
            VK_MEDIA_PLAY_PAUSE = 0xB3
            VK_MEDIA_NEXT = 0xB0
            VK_MEDIA_PREV = 0xB1
            VK_MEDIA_STOP = 0xB2
            VK_VOLUME_MUTE = 0xAD
            
            def press_key(key):
                ctypes.windll.user32.keybd_event(key, 0, 0, 0)
                ctypes.windll.user32.keybd_event(key, 0, 2, 0)
            
            if any(x in cmd for x in ['play music', 'play', 'resume', 'pause', 'pause music']):
                press_key(VK_MEDIA_PLAY_PAUSE)
                return True, "Play/Pause toggled."
            
            if any(x in cmd for x in ['next song', 'next track', 'skip', 'next']):
                press_key(VK_MEDIA_NEXT)
                return True, "Playing next track."
            
            if any(x in cmd for x in ['previous song', 'previous track', 'go back', 'previous']):
                press_key(VK_MEDIA_PREV)
                return True, "Playing previous track."
            
            if any(x in cmd for x in ['stop music', 'stop playing']):
                press_key(VK_MEDIA_STOP)
                return True, "Playback stopped."
        except:
            pass
        
        return False, ""
    
    # ============ POWER CONTROL ============
    
    def _handle_power(self, cmd: str) -> Tuple[bool, str]:
        """Handle power commands (shutdown, restart)"""
        # Shutdown
        if any(x in cmd for x in ['shutdown', 'turn off computer', 'shut down', 'power off']):
            return True, "⚠️ Say 'confirm shutdown' to shut down, or 'cancel' to abort."
        
        if 'confirm shutdown' in cmd:
            os.system('shutdown /s /t 60')
            return True, "Shutting down in 60 seconds. Say 'cancel shutdown' to abort."
        
        if 'cancel shutdown' in cmd:
            os.system('shutdown /a')
            return True, "Shutdown cancelled."
        
        # Restart
        if any(x in cmd for x in ['restart', 'reboot', 'restart computer']):
            return True, "⚠️ Say 'confirm restart' to restart, or 'cancel' to abort."
        
        if 'confirm restart' in cmd:
            os.system('shutdown /r /t 60')
            return True, "Restarting in 60 seconds. Say 'cancel shutdown' to abort."
        
        return False, ""
    
    def _handle_lock_sleep(self, cmd: str) -> Tuple[bool, str]:
        """Handle lock and sleep commands"""
        # Lock screen
        if any(x in cmd for x in ['lock screen', 'lock computer', 'lock pc', 'lock']):
            subprocess.run('rundll32.exe user32.dll,LockWorkStation', shell=True)
            return True, "Locking the screen."
        
        # Sleep
        if any(x in cmd for x in ['go to sleep', 'sleep mode', 'hibernate', 'sleep']):
            subprocess.run('rundll32.exe powrprof.dll,SetSuspendState 0,1,0', shell=True)
            return True, "Going to sleep."
        
        return False, ""
    
    # ============ GREETINGS ============
    
    def _handle_greetings(self, cmd: str) -> Tuple[bool, str]:
        """Handle greetings and casual conversation"""
        hour = datetime.now().hour
        
        if any(x in cmd for x in ['hello', 'hi lada', 'hey lada', 'hi there', 'hey there', 'hi l', 'hey l', 'hello l']):
            if 5 <= hour < 12:
                return True, "Good morning! How can I help you?"
            elif 12 <= hour < 17:
                return True, "Good afternoon! What can I do for you?"
            elif 17 <= hour < 21:
                return True, "Good evening! I'm here to help."
            else:
                return True, "Hello! What do you need?"
        
        if any(x in cmd for x in ['good morning', 'good afternoon', 'good evening', 'good night']):
            return True, "Hello! I'm ready to assist you."
        
        if any(x in cmd for x in ['thank', 'thanks', 'thank you']):
            return True, "You're welcome! Let me know if you need anything else."
        
        if any(x in cmd for x in ['how are you', "how's it going", 'what up']):
            return True, "I'm doing great! Ready to help you with anything."
        
        return False, ""
    
    # ============ FILE OPERATIONS ============
    
    def _handle_file_ops(self, cmd: str) -> Tuple[bool, str]:
        """Handle file operation commands"""
        # Open file explorer
        if any(x in cmd for x in ['open files', 'open file explorer', 'open explorer', 'show files', 'my files']):
            os.startfile('explorer')
            return True, f"{self._ack()} Opening File Explorer."
        
        # Create file commands
        if any(x in cmd for x in ['create file', 'make file', 'new file', 'create a file']):
            # Extract filename from command
            import re
            # Try patterns like "named X", "called X", "name X"
            patterns = [
                r'(?:named?|called?)\s+([^\s]+(?:\.[a-zA-Z]+)?)',
                r'file\s+([^\s]+\.[a-zA-Z]+)',
                r'create\s+(?:a\s+)?(?:file\s+)?([^\s]+\.[a-zA-Z]+)',
            ]
            filename = None
            for pattern in patterns:
                match = re.search(pattern, cmd, re.IGNORECASE)
                if match:
                    filename = match.group(1)
                    # Clean up filename
                    filename = re.sub(r'[^\w\.\-]', '', filename)
                    if '.' not in filename:
                        filename += '.txt'
                    break
            
            if not filename:
                filename = "new_file.txt"
            
            # Determine location
            if 'desktop' in cmd:
                file_path = Path.home() / 'Desktop' / filename
            elif 'documents' in cmd:
                file_path = Path.home() / 'Documents' / filename
            elif 'downloads' in cmd:
                file_path = Path.home() / 'Downloads' / filename
            else:
                file_path = Path.home() / 'Desktop' / filename  # Default to desktop
            
            try:
                file_path.touch()
                return True, f"Created {filename} on your Desktop."
            except Exception as e:
                return True, f"Couldn't create file: {e}"
        
        # Open specific folders
        folders = {
            'downloads': Path.home() / 'Downloads',
            'documents': Path.home() / 'Documents',
            'desktop': Path.home() / 'Desktop',
            'pictures': Path.home() / 'Pictures',
            'music': Path.home() / 'Music',
            'videos': Path.home() / 'Videos',
        }
        
        for folder_name, folder_path in folders.items():
            if any(x in cmd for x in [f'open {folder_name}', f'show {folder_name}', f'go to {folder_name}']):
                os.startfile(str(folder_path))
                return True, f"{self._ack()} Opening {folder_name} folder."
        
        # Search files (simplified)
        if any(x in cmd for x in ['find file', 'search file', 'look for file']):
            # Open Windows search
            subprocess.Popen('explorer shell:search', shell=True)
            return True, "Opening Windows search. Type your file name."
        
        return False, ""


# Singleton instance
_processor = None

def get_processor() -> VoiceCommandProcessor:
    """Get singleton instance of VoiceCommandProcessor"""
    global _processor
    if _processor is None:
        _processor = VoiceCommandProcessor()
    return _processor


# Test
if __name__ == "__main__":
    processor = VoiceCommandProcessor()
    
    # Test commands
    test_commands = [
        "what time is it",
        "set volume to 50",
        "open chrome",
        "search python tutorials on google",
        "battery status",
        "play youtube lo-fi music",
        "what's the date",
        "volume up",
        "mute",
        "open notepad",
        "close chrome",
        "take screenshot",
        "lock screen",
        "hello",
    ]
    
    print("=" * 50)
    print("Voice NLU Test")
    print("=" * 50)
    
    for cmd in test_commands:
        handled, response = processor.process(cmd)
        status = "✅" if handled else "❌"
        print(f"{status} '{cmd}' → {response[:60]}..." if len(response) > 60 else f"{status} '{cmd}' → {response}")
