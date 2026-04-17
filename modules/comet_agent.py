"""
Comet Agent - True Autonomous AI Control
Implements See → Think → Act loop for full autonomous task execution
Like Iron Man's JARVIS - analyzes screen, plans actions, executes autonomously
"""

import asyncio
import time
import json
import re
import threading
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Import existing LADA modules
try:
    from modules.browser_automation import CometBrowserAgent
    BROWSER_OK = True
except ImportError:
    BROWSER_OK = False
    
try:
    from modules.gui_automator import GUIAutomator
    GUI_OK = True
except ImportError:
    GUI_OK = False
    
try:
    from modules.screen_vision import ScreenVision
    SCREEN_VISION_OK = True
except ImportError:
    SCREEN_VISION_OK = False
    
try:
    from modules.screenshot_analysis import ScreenshotAnalyzer
    SCREENSHOT_OK = True
except ImportError:
    SCREENSHOT_OK = False

try:
    from modules.visual_grounding import VisualGrounder
    VISUAL_GROUNDING_OK = True
except ImportError:
    VISUAL_GROUNDING_OK = False

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.3
    PYAUTOGUI_OK = True
except ImportError:
    PYAUTOGUI_OK = False

try:
    from lada_ai_router import HybridAIRouter
    AI_ROUTER_OK = True
except ImportError:
    AI_ROUTER_OK = False


class ActionType(Enum):
    """Types of actions the agent can perform"""
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    NAVIGATE = "navigate"
    WAIT = "wait"
    EXTRACT = "extract"
    SCREENSHOT = "screenshot"
    KEYBOARD = "keyboard"
    OPEN_APP = "open_app"
    CLOSE_APP = "close_app"
    THINK = "think"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class Action:
    """Represents a single action to perform"""
    type: ActionType
    target: Optional[str] = None  # Element selector, coordinates, or text
    value: Optional[str] = None   # Text to type, URL to navigate, etc.
    confidence: float = 1.0
    reasoning: str = ""
    

@dataclass
class ScreenState:
    """Current state of the screen"""
    screenshot_path: Optional[str] = None
    visible_text: str = ""
    detected_elements: List[Dict] = field(default_factory=list)
    current_url: Optional[str] = None
    active_window: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class StateCheckpoint:
    """Snapshot of state before an action for rollback"""
    screen_state: ScreenState
    action: Optional[Action] = None
    step_number: int = 0


@dataclass
class TaskResult:
    """Result of task execution"""
    success: bool
    message: str
    steps_taken: int
    final_state: Optional[ScreenState] = None
    extracted_data: Optional[Dict] = None
    error: Optional[str] = None


class CometAgent:
    """
    Autonomous AI Agent with See → Think → Act control loop
    
    This agent can:
    1. SEE: Capture screen, analyze UI elements, read text
    2. THINK: Use AI to plan multi-step actions
    3. ACT: Execute actions (click, type, navigate, etc.)
    4. VERIFY: Check if action succeeded and self-correct
    """
    
    MAX_STEPS = 50  # Safety limit
    STEP_DELAY = 0.5  # Seconds between actions
    MAX_RETRIES_PER_STEP = 3  # Self-correction retry limit
    CAPTURE_RETRIES = 3

    def __init__(self, ai_router=None, headless: bool = False,
                 progress_callback=None):
        """Initialize the Comet Agent

        Args:
            ai_router: AI router for intelligent planning (HybridAIRouter)
            headless: Whether to run browser in headless mode
            progress_callback: Optional callable(step, max_steps, phase, detail, screenshot_path)
                               phase is one of: 'see', 'think', 'act', 'verify', 'retry', 'done', 'error'
        """
        self.ai_router = ai_router
        self.headless = headless
        self.progress_callback = progress_callback

        # Initialize components
        self.browser: Optional[CometBrowserAgent] = None
        self.gui: Optional[GUIAutomator] = None
        self.screen_vision: Optional[ScreenVision] = None
        self.screenshot_analyzer: Optional[ScreenshotAnalyzer] = None
        self.visual_grounder: Optional[VisualGrounder] = None

        # State tracking
        self.current_task: Optional[str] = None
        self.action_history: List[Action] = []
        self.state_history: List[ScreenState] = []
        self.checkpoints: List[StateCheckpoint] = []
        self.is_running = False
        self._pause_event = threading.Event()
        self._pause_event.set()  # Set = not paused (clear = paused)
        self.click_effect_callback = None  # Optional callable(x, y) for click visual feedback
        self._current_screenshot_path: Optional[str] = None  # Last captured screenshot for SoM

        self._initialize_components()
        
    def _initialize_components(self):
        """Initialize available components"""
        if BROWSER_OK:
            try:
                self.browser = CometBrowserAgent(headless=self.headless)
            except Exception:
                pass
                
        if GUI_OK:
            try:
                self.gui = GUIAutomator()
            except Exception:
                pass
                
        if SCREEN_VISION_OK:
            try:
                self.screen_vision = ScreenVision()
            except Exception:
                pass
                
        if SCREENSHOT_OK:
            try:
                self.screenshot_analyzer = ScreenshotAnalyzer()
            except Exception:
                pass

        if VISUAL_GROUNDING_OK:
            try:
                self.visual_grounder = VisualGrounder()
            except Exception:
                pass
                
    def _capture_screen_state(self) -> ScreenState:
        """SEE: Capture and analyze current screen state"""
        state = ScreenState()

        # Take screenshot
        screenshot_taken = False
        if self.screenshot_analyzer:
            screenshot_path = None
            for _ in range(self.CAPTURE_RETRIES):
                try:
                    screenshot_path = self.screenshot_analyzer.capture_screenshot()
                    if screenshot_path:
                        state.screenshot_path = screenshot_path
                        screenshot_taken = True
                        break
                except Exception:
                    continue

            if screenshot_taken and screenshot_path:
                # Try visual grounding with SoM first (more accurate)
                if self.visual_grounder:
                    try:
                        elements = self.visual_grounder.identify_elements_som(
                            screenshot_path, task_description=self.current_task or ""
                        )
                        if elements:
                            state.detected_elements = [
                                {
                                    'label': e.label,
                                    'type': e.element_type,
                                    'x': e.x, 'y': e.y,
                                    'width': e.width, 'height': e.height,
                                    'center': e.center,
                                    'confidence': e.confidence,
                                }
                                for e in elements
                            ]
                    except Exception:
                        pass

                # Fallback: Analyze screenshot for elements with OCR
                if not state.detected_elements:
                    analysis = self.screenshot_analyzer.analyze_screenshot(screenshot_path)
                    if analysis:
                        state.detected_elements = analysis.get('elements', [])

        # Fallback: use pyautogui for screenshot
        if not screenshot_taken and PYAUTOGUI_OK:
            for _ in range(self.CAPTURE_RETRIES):
                try:
                    from pathlib import Path
                    ss_dir = Path("screenshots")
                    ss_dir.mkdir(exist_ok=True)
                    ss_path = str(ss_dir / f"screen_{int(time.time() * 1000)}.png")
                    img = pyautogui.screenshot()
                    img.save(ss_path)
                    state.screenshot_path = ss_path
                    screenshot_taken = True
                    break
                except Exception:
                    continue

        # Final fallback through GUI automator
        if not screenshot_taken and self.gui:
            for _ in range(self.CAPTURE_RETRIES):
                try:
                    shot = self.gui.screenshot()
                    if shot.get("success") and shot.get("path"):
                        state.screenshot_path = shot["path"]
                        screenshot_taken = True
                        break
                except Exception:
                    continue

        # Get visible text via OCR
        if self.screen_vision:
            try:
                text = self.screen_vision.read_screen_text()
                state.visible_text = text or ""
            except Exception:
                pass

        # Get browser state if active
        if self.browser:
            try:
                state.current_url = self.browser.get_current_url()
            except Exception:
                pass

        # Get active window
        if self.gui:
            try:
                state.active_window = self.gui.get_active_window_title()
            except Exception:
                pass
        elif PYAUTOGUI_OK:
            try:
                import subprocess
                result = subprocess.run(
                    ['powershell', '-Command',
                     '(Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object -First 1).MainWindowTitle'],
                    capture_output=True, text=True, timeout=2
                )
                if result.stdout.strip():
                    state.active_window = result.stdout.strip()
            except Exception:
                pass

        state.timestamp = time.time()
        self.state_history.append(state)
        return state
        
    def _think(self, task: str, current_state: ScreenState, 
               history: List[Action]) -> List[Action]:
        """THINK: Use AI to plan next actions based on current state"""
        
        if not self.ai_router:
            # Fallback: Basic pattern matching for common tasks
            return self._basic_planning(task, current_state)
            
        # Build context for AI
        context = self._build_ai_context(task, current_state, history)
        
        # Ask AI for action plan
        prompt = f"""You are an autonomous AI agent controlling a computer. 
Your task: {task}

Current screen state:
- Active window: {current_state.active_window}
- Current URL: {current_state.current_url}
- Visible text (excerpt): {current_state.visible_text[:500] if current_state.visible_text else 'None'}
- Detected elements: {len(current_state.detected_elements)} UI elements

Previous actions taken: {len(history)}
Last 3 actions: {[f"{a.type.value}: {a.target}" for a in history[-3:]] if history else 'None'}

Based on this state, what is the NEXT action to take?

Respond in JSON format:
{{
    "action": "click|type|scroll|navigate|wait|extract|keyboard|open_app|complete|error",
    "target": "element description, coordinates (x,y), or selector",
    "value": "text to type, URL to navigate, or key to press",
    "reasoning": "why this action is needed"
}}

If the task is complete, use action="complete".
If the task cannot be completed, use action="error" with reasoning.
"""
        
        try:
            # Force smart/reasoning tier for screen control planning
            # Disable web search and caching for internal comet queries
            old_web = getattr(self.ai_router, 'web_search_enabled', False)
            old_cache = getattr(self.ai_router, 'cache_enabled', True)
            self.ai_router.web_search_enabled = False
            self.ai_router.cache_enabled = False
            try:
                response = self.ai_router.query(prompt)
            finally:
                self.ai_router.web_search_enabled = old_web
                self.ai_router.cache_enabled = old_cache

            # Parse AI response
            actions = self._parse_ai_response(response)
            return actions
            
        except Exception as e:
            return [Action(
                type=ActionType.ERROR,
                reasoning=f"AI planning failed: {str(e)}"
            )]
            
    def _build_ai_context(self, task: str, state: ScreenState, 
                          history: List[Action]) -> Dict:
        """Build context dictionary for AI"""
        return {
            "task": task,
            "current_state": {
                "url": state.current_url,
                "window": state.active_window,
                "text_excerpt": state.visible_text[:1000] if state.visible_text else None,
                "element_count": len(state.detected_elements)
            },
            "history_length": len(history),
            "recent_actions": [
                {"type": a.type.value, "target": a.target, "value": a.value}
                for a in history[-5:]
            ]
        }
        
    def _parse_ai_response(self, response: str) -> List[Action]:
        """Parse AI response into actions"""
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                
                action_type = ActionType(data.get('action', 'error'))
                return [Action(
                    type=action_type,
                    target=data.get('target'),
                    value=data.get('value'),
                    reasoning=data.get('reasoning', '')
                )]
        except Exception:
            pass
            
        # Fallback: return thinking action
        return [Action(
            type=ActionType.THINK,
            reasoning="Could not parse AI response, will retry"
        )]
        
    def _basic_planning(self, task: str, state: ScreenState) -> List[Action]:
        """Basic planning without AI - pattern matching"""
        task_lower = task.lower()
        
        # Common patterns
        patterns = [
            # Web navigation
            (r"(?:go to|open|navigate to|visit)\s+(\S+\.(?:com|org|net|io))", 
             lambda m: Action(ActionType.NAVIGATE, value=f"https://{m.group(1)}")),
             
            # Google search
            (r"(?:search|google|look up)\s+(?:for\s+)?(.+)",
             lambda m: Action(ActionType.NAVIGATE, 
                            value=f"https://www.google.com/search?q={m.group(1).replace(' ', '+')}")),
             
            # Click action
            (r"click\s+(?:on\s+)?(.+)",
             lambda m: Action(ActionType.CLICK, target=m.group(1))),
             
            # Type action
            (r"type\s+(.+)",
             lambda m: Action(ActionType.TYPE, value=m.group(1))),
             
            # Open app
            (r"open\s+(?:app\s+)?(\w+)",
             lambda m: Action(ActionType.OPEN_APP, target=m.group(1))),
        ]
        
        for pattern, action_fn in patterns:
            match = re.search(pattern, task_lower)
            if match:
                return [action_fn(match)]
                
        # Default: return error
        return [Action(
            type=ActionType.ERROR,
            reasoning=f"Could not understand task: {task}"
        )]
        
    def _execute_action(self, action: Action) -> Tuple[bool, str]:
        """ACT: Execute a single action"""
        
        try:
            if action.type == ActionType.NAVIGATE:
                if self.browser:
                    self.browser.navigate(action.value)
                    return True, f"Navigated to {action.value}"
                else:
                    import webbrowser
                    webbrowser.open(action.value)
                    return True, f"Opened {action.value} in browser"
                    
            elif action.type == ActionType.CLICK:
                if action.target:
                    # Check if coordinates
                    coord_match = re.match(r'\((\d+),\s*(\d+)\)', action.target)
                    if coord_match:
                        x, y = int(coord_match.group(1)), int(coord_match.group(2))
                        if self.gui:
                            self.gui.click(x, y)
                        elif PYAUTOGUI_OK:
                            pyautogui.click(x, y)
                        # Fire click visual effect callback
                        if self.click_effect_callback:
                            try:
                                self.click_effect_callback(x, y)
                            except Exception:
                                pass
                        return True, f"Clicked at ({x}, {y})"
                    else:
                        # Try SoM-based visual grounding first (most accurate)
                        if self.visual_grounder and self._current_screenshot_path:
                            try:
                                element = self.visual_grounder.find_element_som(
                                    self._current_screenshot_path, action.target
                                )
                                if element and element.confidence > 0.4:
                                    cx, cy = element.center
                                    if self.gui:
                                        self.gui.click(cx, cy)
                                    elif PYAUTOGUI_OK:
                                        pyautogui.click(cx, cy)
                                    if self.click_effect_callback:
                                        try:
                                            self.click_effect_callback(cx, cy)
                                        except Exception:
                                            pass
                                    return True, f"Clicked '{action.target}' at ({cx}, {cy}) [SoM]"
                            except Exception as e:
                                logger.debug(f"[CometAgent] SoM visual grounding failed: {e}")

                        # Fallback: Try to find by text/label with GUI automator
                        if self.gui:
                            click_result = self.gui.click_on_text(action.target)
                            if click_result.get("success"):
                                # Try to get coordinates from gui for effect
                                if self.click_effect_callback:
                                    try:
                                        import pyautogui as _pg
                                        px, py = _pg.position()
                                        self.click_effect_callback(int(px), int(py))
                                    except Exception:
                                        pass
                                return True, f"Clicked on '{action.target}'"
                        # Fallback: try pyautogui locateOnScreen or just log
                        if PYAUTOGUI_OK:
                            try:
                                loc = pyautogui.locateOnScreen(action.target)
                                if loc:
                                    pyautogui.click(loc)
                                    return True, f"Clicked on '{action.target}'"
                            except Exception:
                                pass
                elif self.browser:
                    self.browser.click(action.target)
                    return True, f"Clicked {action.target}"

                return False, f"Could not click '{action.target}'"
                
            elif action.type == ActionType.TYPE:
                text_to_type = action.value or action.target or ""
                if not text_to_type:
                    return False, "No text provided for type action"
                if self.gui:
                    type_result = self.gui.type_text(text_to_type)
                    if not type_result.get("success"):
                        return False, type_result.get("error", "GUI typing failed")
                    return True, f"Typed '{text_to_type[:20]}...'"
                elif PYAUTOGUI_OK:
                    pyautogui.write(text_to_type, interval=0.03)
                    return True, f"Typed '{text_to_type[:20]}...'"
                elif self.browser:
                    self.browser.type(action.target or "input", text_to_type)
                    return True, f"Typed in {action.target or 'input'}"

                return False, "No typing capability available"
                
            elif action.type == ActionType.SCROLL:
                direction = (action.value or "down").lower()
                if self.gui:
                    self.gui.scroll(direction)
                    return True, f"Scrolled {direction}"
                elif PYAUTOGUI_OK:
                    clicks = -5 if 'down' in direction else 5
                    pyautogui.scroll(clicks)
                    return True, f"Scrolled {direction}"
                elif self.browser:
                    self.browser.execute_js("window.scrollBy(0, 500)")
                    return True, "Scrolled down"
                    
            elif action.type == ActionType.WAIT:
                duration = float(action.value) if action.value else 1.0
                time.sleep(duration)
                return True, f"Waited {duration}s"
                
            elif action.type == ActionType.KEYBOARD:
                if self.gui:
                    self.gui.press_key(action.value)
                    return True, f"Pressed {action.value}"
                elif PYAUTOGUI_OK:
                    pyautogui.press(action.value)
                    return True, f"Pressed {action.value}"
                    
            elif action.type == ActionType.OPEN_APP:
                if self.gui:
                    self.gui.open_application(action.target)
                    return True, f"Opened {action.target}"
                else:
                    import subprocess
                    subprocess.Popen(action.target)
                    return True, f"Launched {action.target}"
                    
            elif action.type == ActionType.EXTRACT:
                if self.browser:
                    text = self.browser.extract_text(action.target or "body")
                    return True, f"Extracted: {text[:100]}..."
                elif self.screen_vision:
                    text = self.screen_vision.read_screen_text()
                    return True, f"Read: {text[:100]}..."
                    
            elif action.type == ActionType.SCREENSHOT:
                if self.screenshot_analyzer:
                    path = self.screenshot_analyzer.capture_screenshot()
                    if path:
                        return True, f"Screenshot saved: {path}"
                if self.gui:
                    shot = self.gui.screenshot()
                    if shot.get("success"):
                        return True, f"Screenshot saved: {shot.get('path', 'unknown')}"
                    return False, shot.get("error", "Screenshot failed")
                if PYAUTOGUI_OK:
                    try:
                        from pathlib import Path
                        ss_dir = Path("screenshots")
                        ss_dir.mkdir(exist_ok=True)
                        ss_path = str(ss_dir / f"screen_{int(time.time() * 1000)}.png")
                        pyautogui.screenshot().save(ss_path)
                        return True, f"Screenshot saved: {ss_path}"
                    except Exception as screenshot_exc:
                        return False, f"Screenshot failed: {screenshot_exc}"
                return False, "No screenshot capability available"
                    
            elif action.type == ActionType.COMPLETE:
                return True, "Task completed successfully"
                
            elif action.type == ActionType.ERROR:
                return False, action.reasoning
                
            elif action.type == ActionType.THINK:
                return True, "Thinking..."
                
            return False, f"Unknown action type: {action.type}"
            
        except Exception as e:
            return False, f"Action failed: {str(e)}"
            
    def _verify_action(self, action: Action,
                       before_state: ScreenState) -> Tuple[bool, ScreenState]:
        """VERIFY: Check if action succeeded using state comparison"""
        # Capture new state
        after_state = self._capture_screen_state()

        # Simple verification: check if something changed
        changed = (
            after_state.current_url != before_state.current_url or
            after_state.active_window != before_state.active_window or
            after_state.visible_text != before_state.visible_text
        )

        # For some actions, change is expected
        if action.type in [ActionType.NAVIGATE, ActionType.CLICK,
                           ActionType.OPEN_APP, ActionType.TYPE]:
            return changed, after_state

        # For wait/screenshot/extract, just return success
        if action.type in [ActionType.WAIT, ActionType.SCREENSHOT,
                           ActionType.EXTRACT, ActionType.COMPLETE]:
            return True, after_state

        return True, after_state

    def _create_checkpoint(self, state: ScreenState, action: Action, step: int):
        """Create a state checkpoint before executing an action."""
        self.checkpoints.append(StateCheckpoint(
            screen_state=state,
            action=action,
            step_number=step,
        ))
        # Keep only last 10 checkpoints to limit memory
        if len(self.checkpoints) > 10:
            self.checkpoints = self.checkpoints[-10:]

    def _try_alternative_strategies(self, failed_action: Action,
                                     current_state: ScreenState,
                                     failure_reason: str) -> Optional[Action]:
        """
        Generate alternative action strategies when an action fails.
        Returns an alternative Action or None if no alternatives.
        """
        # Strategy 1: For CLICK failures, try different targeting methods
        if failed_action.type == ActionType.CLICK:
            target = failed_action.target or ""

            # Try by coordinates if text-based click failed
            if not re.match(r'\(\d+,\s*\d+\)', target):
                # Ask AI for coordinates if available
                if self.ai_router and current_state.visible_text:
                    try:
                        prompt = (
                            f"I need to click on '{target}' but text-based click failed. "
                            f"The screen shows: {current_state.visible_text[:300]}\n"
                            f"Suggest an alternative way to interact with this element. "
                            f"Respond with ONLY one of:\n"
                            f"- SCROLL: if element might be off-screen\n"
                            f"- KEYBOARD: Tab and Enter to reach it\n"
                            f"- WAIT: if page is still loading"
                        )
                        alt = self.ai_router.query(prompt)
                        if alt:
                            alt_lower = alt.strip().lower()
                            if 'scroll' in alt_lower:
                                return Action(ActionType.SCROLL, value="down",
                                              reasoning="Scrolling to find target element")
                            elif 'keyboard' in alt_lower or 'tab' in alt_lower:
                                return Action(ActionType.KEYBOARD, value="tab",
                                              reasoning="Using Tab to reach element")
                            elif 'wait' in alt_lower:
                                return Action(ActionType.WAIT, value="2",
                                              reasoning="Waiting for page to load")
                    except Exception:
                        pass

                # Default: try scrolling down to find element
                return Action(ActionType.SCROLL, value="down",
                              reasoning=f"Click on '{target}' failed, scrolling to find it")

        # Strategy 2: For TYPE failures, try clipboard paste
        if failed_action.type == ActionType.TYPE and self.gui:
            return Action(ActionType.KEYBOARD, value="ctrl+v",
                          reasoning="Typing failed, trying clipboard paste")

        # Strategy 3: For NAVIGATE failures, try search instead
        if failed_action.type == ActionType.NAVIGATE:
            url = failed_action.value or ""
            # Try Google search for the domain
            search_query = url.replace('https://', '').replace('http://', '').split('/')[0]
            return Action(ActionType.NAVIGATE,
                          value=f"https://www.google.com/search?q={search_query}",
                          reasoning=f"Direct navigation failed, searching for {search_query}")

        return None

    def _self_correct(self, failed_action: Action, current_state: ScreenState,
                      failure_reason: str, attempt: int) -> Optional[Action]:
        """
        Self-correction: analyze failure and generate recovery action.
        Uses AI when available, falls back to heuristic strategies.
        """
        if attempt >= self.MAX_RETRIES_PER_STEP:
            return None  # Give up after max retries

        # Try AI-powered correction first
        if self.ai_router:
            try:
                prompt = (
                    f"Action FAILED (attempt {attempt + 1}/{self.MAX_RETRIES_PER_STEP}):\n"
                    f"- Action: {failed_action.type.value} on '{failed_action.target}'\n"
                    f"- Error: {failure_reason}\n"
                    f"- Screen: {current_state.active_window}, "
                    f"URL: {current_state.current_url}\n"
                    f"- Visible text: {current_state.visible_text[:200]}\n\n"
                    f"Suggest ONE alternative action in JSON:\n"
                    f'{{"action": "...", "target": "...", "value": "...", "reasoning": "..."}}'
                )
                response = self.ai_router.query(prompt)
                if response:
                    actions = self._parse_ai_response(response)
                    if actions and actions[0].type != ActionType.ERROR:
                        actions[0].reasoning = f"Self-correction attempt {attempt + 1}: {actions[0].reasoning}"
                        return actions[0]
            except Exception:
                pass

        # Fall back to heuristic alternatives
        return self._try_alternative_strategies(failed_action, current_state, failure_reason)
        
    def _report_progress(self, step, max_steps, phase, detail='', screenshot_path=None):
        """Report progress via callback if available"""
        if self.progress_callback:
            try:
                self.progress_callback(step, max_steps, phase, detail, screenshot_path)
            except Exception:
                pass

    async def execute_task(self, task: str,
                          max_steps: int = None) -> TaskResult:
        """Execute a task autonomously using See -> Think -> Act loop

        Args:
            task: Natural language description of what to do
            max_steps: Maximum steps to take (default: MAX_STEPS)

        Returns:
            TaskResult with success status and details
        """
        max_steps = max_steps or self.MAX_STEPS
        self.current_task = task
        self.action_history = []
        self.state_history = []
        self.checkpoints = []
        self.is_running = True

        steps = 0
        extracted_data = {}

        try:
            while self.is_running and steps < max_steps:
                # Pause support - wait here if paused
                self._pause_event.wait()
                if not self.is_running:
                    break

                steps += 1

                # 1. SEE - Capture current state
                self._report_progress(steps, max_steps, 'see', 'Analyzing screen...')
                current_state = self._capture_screen_state()
                self._current_screenshot_path = current_state.screenshot_path  # Store for SoM
                self._report_progress(steps, max_steps, 'see',
                                      f'Window: {current_state.active_window or "Desktop"}',
                                      current_state.screenshot_path)

                # 2. THINK - Plan next action(s)
                self._report_progress(steps, max_steps, 'think', 'Planning next actions...')
                actions = self._think(task, current_state, self.action_history)

                if not actions:
                    break

                # 3. ACT - Execute each planned action
                for action in actions:
                    # Check for completion
                    if action.type == ActionType.COMPLETE:
                        self._report_progress(steps, max_steps, 'done', 'Task completed successfully')
                        return TaskResult(
                            success=True,
                            message="Task completed successfully",
                            steps_taken=steps,
                            final_state=current_state,
                            extracted_data=extracted_data
                        )

                    # Check for error
                    if action.type == ActionType.ERROR:
                        self._report_progress(steps, max_steps, 'error', action.reasoning)
                        return TaskResult(
                            success=False,
                            message=action.reasoning,
                            steps_taken=steps,
                            final_state=current_state,
                            error=action.reasoning
                        )

                    # Create checkpoint before action
                    self._create_checkpoint(current_state, action, steps)

                    # Report action
                    action_desc = f"{action.type.value}: {action.target or ''} {action.value or ''}".strip()
                    self._report_progress(steps, max_steps, 'act', action_desc)

                    # Execute action with self-correction loop
                    retry_count = 0
                    current_action = action

                    while retry_count <= self.MAX_RETRIES_PER_STEP:
                        success, message = self._execute_action(current_action)
                        current_action.reasoning = message
                        self.action_history.append(current_action)

                        if success:
                            break  # Action succeeded

                        # Action failed - try self-correction
                        retry_count += 1
                        self._report_progress(steps, max_steps, 'retry',
                                              f'Retry {retry_count}/{self.MAX_RETRIES_PER_STEP}: {message}')
                        recovery = self._self_correct(
                            current_action, current_state, message, retry_count
                        )
                        if recovery:
                            current_action = recovery
                        else:
                            break  # No recovery available

                    # Small delay between actions
                    await asyncio.sleep(self.STEP_DELAY)

                    # 4. VERIFY - Check if action succeeded
                    self._report_progress(steps, max_steps, 'verify', 'Verifying action result...')
                    verified, new_state = self._verify_action(current_action, current_state)

                    if current_action.type == ActionType.EXTRACT and message:
                        extracted_data['text'] = message

            # Max steps reached
            self._report_progress(steps, max_steps, 'error',
                                  f'Max steps ({max_steps}) reached without completion')
            return TaskResult(
                success=False,
                message=f"Max steps ({max_steps}) reached without completion",
                steps_taken=steps,
                final_state=self._capture_screen_state()
            )
            
        except Exception as e:
            return TaskResult(
                success=False,
                message=f"Task execution failed: {str(e)}",
                steps_taken=steps,
                error=str(e)
            )
        finally:
            self.is_running = False
            
    def execute_task_sync(self, task: str, max_steps: int = None) -> TaskResult:
        """Synchronous wrapper for execute_task"""
        return asyncio.run(self.execute_task(task, max_steps))
        
    def stop(self):
        """Stop current task execution"""
        self.is_running = False
        self._pause_event.set()  # Unblock any waiting pause so the loop can exit

    def pause(self):
        """Pause current task execution (can be resumed)"""
        self._pause_event.clear()

    def resume(self):
        """Resume a paused task"""
        self._pause_event.set()

    @property
    def paused(self) -> bool:
        """Whether the agent is currently paused"""
        return not self._pause_event.is_set()
        
    def cleanup(self):
        """Clean up resources"""
        self.stop()
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass


class QuickActions:
    """Pre-defined quick actions for common tasks"""
    
    def __init__(self, agent: CometAgent):
        self.agent = agent
        
    async def google_search(self, query: str) -> TaskResult:
        """Search Google for something"""
        return await self.agent.execute_task(f"search google for {query}")
        
    async def open_website(self, url: str) -> TaskResult:
        """Open a website"""
        if not url.startswith('http'):
            url = f"https://{url}"
        return await self.agent.execute_task(f"navigate to {url}")
        
    async def book_flight(self, origin: str, destination: str, 
                         date: str) -> TaskResult:
        """Book a flight"""
        return await self.agent.execute_task(
            f"go to google flights and search for flights from {origin} to {destination} on {date}"
        )
        
    async def order_food(self, restaurant: str, items: List[str]) -> TaskResult:
        """Order food from a restaurant"""
        items_str = ", ".join(items)
        return await self.agent.execute_task(
            f"go to {restaurant} website and order {items_str}"
        )
        
    async def send_email(self, to: str, subject: str, body: str) -> TaskResult:
        """Compose and send email"""
        return await self.agent.execute_task(
            f"open gmail, compose new email to {to} with subject '{subject}' and body '{body}', then send it"
        )
        
    async def schedule_meeting(self, title: str, date: str, 
                              time: str, attendees: List[str] = None) -> TaskResult:
        """Schedule a calendar meeting"""
        attendees_str = ", ".join(attendees) if attendees else ""
        return await self.agent.execute_task(
            f"open google calendar, create event titled '{title}' on {date} at {time}" +
            (f" with attendees {attendees_str}" if attendees_str else "")
        )


# Factory function
def create_comet_agent(ai_router=None) -> CometAgent:
    """Create and configure a Comet Agent
    
    Args:
        ai_router: Optional AI router for intelligent planning
        
    Returns:
        Configured CometAgent instance
    """
    agent = CometAgent(ai_router=ai_router)
    return agent
