"""
LADA v11.0 - LLM-Driven Computer Use Agent
Autonomous screen understanding + GUI actions via LLM reasoning.

Integrates:
- modules.computer_control
- modules.browser_control
"""

import os
import json
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from modules.computer_control import ComputerControl
try:
    from modules.browser_control import BrowserControl
    HAS_BROWSER_CONTROL = True
except ImportError:
    HAS_BROWSER_CONTROL = False

# Import event hooks for UI updates
try:
    from modules.event_hooks import emit_event
except ImportError:
    def emit_event(*args, **kwargs): pass

logger = logging.getLogger(__name__)

class ActionType(Enum):
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    TYPE_TEXT = "type_text"
    PRESS_KEY = "press_key"
    HOTKEY = "hotkey"
    SCROLL = "scroll"
    MOVE_TO = "move_to"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    BROWSER_OPEN = "browser_open"
    BROWSER_CLICK = "browser_click"
    BROWSER_TYPE = "browser_type"

@dataclass
class UIAction:
    """A single UI action to perform."""
    action_type: ActionType
    target_description: str = ""
    x: int = 0
    y: int = 0
    text: str = ""
    keys: List[str] = field(default_factory=list)
    scroll_amount: int = 0
    wait_seconds: float = 0.5
    url: str = ""
    selector: str = ""

@dataclass
class ActionResult:
    """Result of executing a UI action."""
    success: bool
    action: UIAction
    screenshot_after: Optional[str] = None
    error: Optional[str] = None
    duration_ms: float = 0

class ActionExecutor:
    """Execute UI actions via new ComputerControl and BrowserControl."""

    def __init__(self):
        self._action_log: List[Dict[str, Any]] = []
        self.computer = ComputerControl()
        self.browser = None
        self._browser_initialized = False

    def _ensure_browser(self):
        if HAS_BROWSER_CONTROL and not self._browser_initialized:
            self.browser = BrowserControl(profile="user")
            self._browser_initialized = True

    def execute(self, action: UIAction) -> ActionResult:
        start = time.time()
        result_dict = {"success": False, "error": "Unknown action"}
        
        try:
            # OS Actions
            if action.action_type == ActionType.CLICK:
                result_dict = self.computer.click(action.x, action.y, "left")
            elif action.action_type == ActionType.DOUBLE_CLICK:
                result_dict = self.computer.click(action.x, action.y, "left")
                time.sleep(0.1)
                result_dict = self.computer.click(action.x, action.y, "left")
            elif action.action_type == ActionType.RIGHT_CLICK:
                result_dict = self.computer.click(action.x, action.y, "right")
            elif action.action_type == ActionType.TYPE_TEXT:
                if action.x and action.y:
                    self.computer.click(action.x, action.y)
                result_dict = self.computer.type_text(action.text)
            elif action.action_type == ActionType.PRESS_KEY:
                if action.keys:
                    result_dict = self.computer.hotkey(*action.keys)
            elif action.action_type == ActionType.HOTKEY:
                result_dict = self.computer.hotkey(*action.keys)
            elif action.action_type == ActionType.SCROLL:
                dir_str = "up" if action.scroll_amount > 0 else "down"
                result_dict = self.computer.scroll(dir_str, abs(action.scroll_amount))
            elif action.action_type == ActionType.MOVE_TO:
                result_dict = self.computer.move_mouse(action.x, action.y)
            elif action.action_type == ActionType.WAIT:
                time.sleep(action.wait_seconds)
                result_dict = {"success": True, "action": f"waited {action.wait_seconds}s"}
            
            # Browser Actions
            elif action.action_type == ActionType.BROWSER_OPEN:
                self._ensure_browser()
                if self.browser:
                    result_dict = self.browser.open(action.url)
            elif action.action_type == ActionType.BROWSER_CLICK:
                self._ensure_browser()
                if self.browser:
                    result_dict = self.browser.click(action.selector)
            elif action.action_type == ActionType.BROWSER_TYPE:
                self._ensure_browser()
                if self.browser:
                    result_dict = self.browser.type(action.selector, action.text)
            elif action.action_type == ActionType.SCREENSHOT:
                result_dict = {"success": True}

            duration = (time.time() - start) * 1000
            success = result_dict.get("success", False)
            
            self._action_log.append({
                "action": action.action_type.value,
                "target": action.target_description,
                "success": success,
                "duration_ms": duration,
                "details": result_dict
            })
            
            # Log to lada_actions.log
            with open("lada_actions.log", "a") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {action.action_type.value} -> {action.target_description} | Success: {success}\n")

            time.sleep(0.5)
            screenshot_b64 = self.computer.screenshot()

            return ActionResult(
                success=success,
                action=action,
                screenshot_after=screenshot_b64,
                duration_ms=duration,
                error=result_dict.get("error") if not success else None
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            logger.error(f"[ComputerUse] Action failed: {e}")
            return ActionResult(success=False, action=action, error=str(e), duration_ms=duration)

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._action_log)

    def close(self):
        if self.browser:
            self.browser.close()

class ComputerUseAgent:
    MAX_ACTIONS = 20

    SYSTEM_PROMPT = (
        "You are an autonomous computer control agent. Analyze the provided screenshot and goal to take the next action.\n"
        "Available actions (JSON):\n"
        "- {\"action\": \"click\", \"x\": X, \"y\": Y, \"description\": \"...\"}\n"
        "- {\"action\": \"type_text\", \"text\": \"...\", \"description\": \"...\"}\n"
        "- {\"action\": \"hotkey\", \"keys\": [\"ctrl\", \"c\"], \"description\": \"...\"}\n"
        "- {\"action\": \"browser_open\", \"url\": \"https:...\", \"description\": \"...\"}\n"
        "- {\"action\": \"browser_click\", \"selector\": \"...\", \"description\": \"...\"}\n"
        "- {\"action\": \"browser_type\", \"selector\": \"...\", \"text\": \"...\", \"description\": \"...\"}\n"
        "- {\"action\": \"done\", \"description\": \"Task complete\"}\n"
        "Return strictly JSON."
    )

    def __init__(self, ai_router=None):
        self.ai_router = ai_router
        self.executor = ActionExecutor()
        self.approval_mode = os.getenv("LADA_APPROVAL_MODE", "false").lower() == "true"

    def _ui_log(self, msg: str, image_b64: str = None):
        """Send live action log to WebUI via event hooks."""
        payload = {"message": msg, "timestamp": time.time()}
        if image_b64:
            payload["screenshot_b64"] = image_b64
        emit_event("computer_control_log", payload)
        logger.info(f"[Computer Control] {msg}")

    def run_computer_task(self, goal: str) -> Dict[str, Any]:
        """Execute task with live WebUI tracking."""
        if not self.ai_router:
            return {"status": "error", "message": "No AI router configured"}

        steps_taken = 0
        self._ui_log(f"🚀 Starting task: {goal}")

        while steps_taken < self.MAX_ACTIONS:
            screenshot_b64 = self.executor.computer.screenshot()
            self._ui_log("📸 Analyzing screen...", screenshot_b64)

            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": f"Goal: {goal}\nSteps taken: {steps_taken}\nWhat is the next action?"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}}
                ]}
            ]

            try:
                response = self.ai_router.analyze_image(screenshot_b64, self.SYSTEM_PROMPT + f"\nGoal: {goal}")
            except Exception as e:
                self._ui_log(f"❌ Vision API Error: {e}")
                break

            action = self._parse_action(response)
            if not action:
                self._ui_log(f"⚠️ Could not parse LLM response: {response[:100]}...")
                break

            if action.action_type.value == "done":
                self._ui_log("✅ Task completed successfully!", screenshot_b64)
                return {"status": "completed", "steps": steps_taken}

            self._ui_log(f"🤖 Action: {action.action_type.value} -> {action.target_description}")

            # Safety Mode Approval (Mock wait for user - in real app would block via WebSocket)
            if self.approval_mode:
                self._ui_log("🛑 Waiting for user approval (Safety Mode ON)...")
                # Implementation of pausing for approval goes here

            result = self.executor.execute(action)
            steps_taken += 1

            if not result.success:
                self._ui_log(f"❌ Action failed: {result.error}")
            else:
                self._ui_log(f"✅ Action succeeded", result.screenshot_after)

        self.executor.close()
        return {"status": "max_steps_reached", "steps": steps_taken}

    def _parse_action(self, response: str) -> Optional[UIAction]:
        import re
        match = re.search(r'\{.*\}', response.replace('\n', ''), re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                act_str = data.get("action", "").upper()
                return UIAction(
                    action_type=getattr(ActionType, act_str, ActionType.WAIT),
                    target_description=data.get("description", ""),
                    x=int(data.get("x", 0)),
                    y=int(data.get("y", 0)),
                    text=data.get("text", ""),
                    keys=data.get("keys", []),
                    url=data.get("url", ""),
                    selector=data.get("selector", "")
                )
            except Exception:
                pass
        return None

_computer_use_agent = None
def get_computer_use_agent(ai_router=None) -> ComputerUseAgent:
    global _computer_use_agent
    if _computer_use_agent is None:
        _computer_use_agent = ComputerUseAgent(ai_router=ai_router)
    return _computer_use_agent
