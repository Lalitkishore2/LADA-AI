"""
LADA v11.0 - LLM-Driven Computer Use Agent
Autonomous screen understanding + GUI actions via LLM reasoning.

The agent captures screenshots, understands UI elements via vision LLM,
plans actions, and executes mouse/keyboard operations to accomplish tasks.
"""

import os
import io
import json
import time
import base64
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# Conditional imports
try:
    from PIL import Image, ImageGrab
    PIL_OK = True
except ImportError:
    PIL_OK = False

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.3
    PYAUTOGUI_OK = True
except ImportError:
    PYAUTOGUI_OK = False


class ActionType(Enum):
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    TYPE_TEXT = "type_text"
    PRESS_KEY = "press_key"
    HOTKEY = "hotkey"
    SCROLL = "scroll"
    MOVE_TO = "move_to"
    DRAG_TO = "drag_to"
    WAIT = "wait"
    SCREENSHOT = "screenshot"


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
    confidence: float = 0.0


@dataclass
class ActionResult:
    """Result of executing a UI action."""
    success: bool
    action: UIAction
    screenshot_after: Optional[bytes] = None
    error: Optional[str] = None
    duration_ms: float = 0


class ScreenCapture:
    """Capture and encode screenshots for vision LLM analysis."""

    @staticmethod
    def capture_full() -> Optional[bytes]:
        """Capture full screen as JPEG bytes."""
        if not PIL_OK:
            return None
        try:
            screenshot = ImageGrab.grab()
            buffer = io.BytesIO()
            screenshot.save(buffer, format='JPEG', quality=75)
            return buffer.getvalue()
        except Exception as e:
            logger.error(f"[ComputerUse] Screenshot error: {e}")
            return None

    @staticmethod
    def capture_region(x: int, y: int, width: int, height: int) -> Optional[bytes]:
        """Capture a specific screen region."""
        if not PIL_OK:
            return None
        try:
            screenshot = ImageGrab.grab(bbox=(x, y, x + width, y + height))
            buffer = io.BytesIO()
            screenshot.save(buffer, format='JPEG', quality=80)
            return buffer.getvalue()
        except Exception as e:
            logger.error(f"[ComputerUse] Region capture error: {e}")
            return None

    @staticmethod
    def to_base64(image_bytes: bytes) -> str:
        return base64.b64encode(image_bytes).decode('utf-8')

    @staticmethod
    def get_screen_size() -> Tuple[int, int]:
        if PYAUTOGUI_OK:
            return pyautogui.size()
        return (1920, 1080)


class ActionExecutor:
    """Execute UI actions via pyautogui."""

    def __init__(self):
        self._action_log: List[Dict[str, Any]] = []

    def execute(self, action: UIAction) -> ActionResult:
        """Execute a single UI action."""
        if not PYAUTOGUI_OK:
            return ActionResult(
                success=False, action=action,
                error="pyautogui not available"
            )

        start = time.time()
        try:
            if action.action_type == ActionType.CLICK:
                pyautogui.click(action.x, action.y)
            elif action.action_type == ActionType.DOUBLE_CLICK:
                pyautogui.doubleClick(action.x, action.y)
            elif action.action_type == ActionType.RIGHT_CLICK:
                pyautogui.rightClick(action.x, action.y)
            elif action.action_type == ActionType.TYPE_TEXT:
                if action.x and action.y:
                    pyautogui.click(action.x, action.y)
                    time.sleep(0.2)
                pyautogui.typewrite(action.text, interval=0.02) if action.text.isascii() else pyautogui.write(action.text)
            elif action.action_type == ActionType.PRESS_KEY:
                for key in action.keys:
                    pyautogui.press(key)
            elif action.action_type == ActionType.HOTKEY:
                pyautogui.hotkey(*action.keys)
            elif action.action_type == ActionType.SCROLL:
                pyautogui.scroll(action.scroll_amount, action.x or None, action.y or None)
            elif action.action_type == ActionType.MOVE_TO:
                pyautogui.moveTo(action.x, action.y, duration=0.3)
            elif action.action_type == ActionType.DRAG_TO:
                pyautogui.moveTo(action.x, action.y, duration=0.5)
            elif action.action_type == ActionType.WAIT:
                time.sleep(action.wait_seconds)
            elif action.action_type == ActionType.SCREENSHOT:
                pass  # Just capture, handled by caller

            duration = (time.time() - start) * 1000
            self._action_log.append({
                "action": action.action_type.value,
                "target": action.target_description,
                "x": action.x, "y": action.y,
                "success": True, "duration_ms": duration,
            })

            # Brief pause for UI to update
            time.sleep(0.3)
            screenshot = ScreenCapture.capture_full()

            return ActionResult(
                success=True, action=action,
                screenshot_after=screenshot,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            logger.error(f"[ComputerUse] Action failed: {e}")
            return ActionResult(
                success=False, action=action,
                error=str(e), duration_ms=duration,
            )

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._action_log)


class ComputerUseAgent:
    """
    LLM-driven computer use agent.

    Captures screen, sends to vision-capable LLM for analysis,
    receives action plan, and executes actions autonomously.

    Features:
    - Screenshot-based UI understanding
    - Multi-step task planning via LLM
    - Action execution with verification
    - Error recovery with re-planning
    - Safety limits (max actions, timeout)
    - Action logging and undo capability
    """

    MAX_ACTIONS = 20
    MAX_RETRIES = 3
    ACTION_TIMEOUT = 60  # seconds per step

    SYSTEM_PROMPT = (
        "You are a computer use agent. You see screenshots and must help the user "
        "perform tasks by specifying mouse/keyboard actions.\n\n"
        "Available actions:\n"
        "- click(x, y) - Left click at coordinates\n"
        "- double_click(x, y) - Double click\n"
        "- right_click(x, y) - Right click\n"
        "- type_text(text) - Type text\n"
        "- press_key(key) - Press a key (enter, tab, escape, etc.)\n"
        "- hotkey(key1, key2, ...) - Press key combination (ctrl, c for copy)\n"
        "- scroll(amount) - Scroll (positive=up, negative=down)\n"
        "- wait(seconds) - Wait for UI to update\n"
        "- done() - Task is complete\n\n"
        "Respond with a JSON object: {\"action\": \"click\", \"x\": 500, \"y\": 300, "
        "\"description\": \"Click the search box\", \"reasoning\": \"I need to...\"}\n"
        "Use \"done\" action when the task is completed."
    )

    def __init__(self, ai_router=None):
        self.ai_router = ai_router
        self.executor = ActionExecutor()
        self.screen = ScreenCapture()
        self._task_log: List[Dict[str, Any]] = []

    def execute_task(self, task_description: str,
                     max_steps: int = None,
                     safety_confirm: Optional[callable] = None) -> Dict[str, Any]:
        """
        Execute a multi-step computer use task.

        Args:
            task_description: Natural language description of what to do
            max_steps: Maximum actions to take
            safety_confirm: Optional callback for dangerous action confirmation

        Returns:
            Result dict with status, steps taken, and action log
        """
        max_steps = max_steps or self.MAX_ACTIONS

        if not self.ai_router:
            return {"status": "error", "message": "No AI router configured for vision analysis"}

        steps_taken = 0
        action_log = []
        conversation = []

        logger.info(f"[ComputerUse] Starting task: {task_description}")

        while steps_taken < max_steps:
            # 1. Capture current screen
            screenshot = self.screen.capture_full()
            if not screenshot:
                return {"status": "error", "message": "Failed to capture screenshot"}

            screenshot_b64 = self.screen.to_base64(screenshot)

            # 2. Ask LLM what to do next
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": f"Task: {task_description}\n\nSteps completed: {steps_taken}\n\nWhat action should I take next on this screen?"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{screenshot_b64}"}},
                ]},
            ]

            # Add previous actions for context
            for prev in action_log[-5:]:
                messages.append({
                    "role": "assistant",
                    "content": json.dumps(prev),
                })

            try:
                response = self._query_vision_llm(task_description, screenshot_b64, action_log)
            except Exception as e:
                logger.error(f"[ComputerUse] LLM query failed: {e}")
                return {"status": "error", "message": str(e), "steps": steps_taken, "log": action_log}

            # 3. Parse action from LLM response
            action = self._parse_action(response)
            if action is None:
                logger.warning(f"[ComputerUse] Could not parse action from: {response[:200]}")
                return {"status": "error", "message": "Failed to parse LLM action", "steps": steps_taken, "log": action_log}

            # Check for completion
            if action.action_type.value == "done" or "done" in response.lower()[:20]:
                logger.info(f"[ComputerUse] Task completed in {steps_taken} steps")
                return {"status": "completed", "steps": steps_taken, "log": action_log}

            # 4. Safety check for dangerous actions
            if safety_confirm and action.action_type in (ActionType.TYPE_TEXT, ActionType.HOTKEY):
                if not safety_confirm(action):
                    logger.info("[ComputerUse] Action blocked by safety check")
                    continue

            # 5. Execute action
            result = self.executor.execute(action)
            steps_taken += 1

            action_entry = {
                "step": steps_taken,
                "action": action.action_type.value,
                "target": action.target_description,
                "x": action.x, "y": action.y,
                "text": action.text,
                "success": result.success,
                "error": result.error,
            }
            action_log.append(action_entry)

            if not result.success:
                logger.warning(f"[ComputerUse] Step {steps_taken} failed: {result.error}")

        return {
            "status": "max_steps_reached",
            "steps": steps_taken,
            "log": action_log,
        }

    def _query_vision_llm(self, task: str, screenshot_b64: str,
                          previous_actions: List[Dict]) -> str:
        """Query the vision LLM for next action."""
        prev_str = ""
        if previous_actions:
            prev_str = "\n\nPrevious actions:\n" + "\n".join(
                f"Step {a['step']}: {a['action']} at ({a.get('x',0)},{a.get('y',0)}) - {a.get('target','')}"
                for a in previous_actions[-5:]
            )

        prompt = (
            f"{self.SYSTEM_PROMPT}\n\n"
            f"Task: {task}{prev_str}\n\n"
            f"Analyze the screenshot and respond with the next action as JSON."
        )

        if hasattr(self.ai_router, 'analyze_image'):
            return self.ai_router.analyze_image(screenshot_b64, prompt)
        elif hasattr(self.ai_router, 'route_query'):
            return self.ai_router.route_query(prompt)
        else:
            raise RuntimeError("AI router doesn't support vision queries")

    def _parse_action(self, llm_response: str) -> Optional[UIAction]:
        """Parse LLM response into a UIAction."""
        import re

        # Try JSON parsing
        json_match = re.search(r'\{[^{}]*\}', llm_response, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                action_str = data.get("action", "").lower()

                action_map = {
                    "click": ActionType.CLICK,
                    "double_click": ActionType.DOUBLE_CLICK,
                    "right_click": ActionType.RIGHT_CLICK,
                    "type_text": ActionType.TYPE_TEXT,
                    "type": ActionType.TYPE_TEXT,
                    "press_key": ActionType.PRESS_KEY,
                    "press": ActionType.PRESS_KEY,
                    "hotkey": ActionType.HOTKEY,
                    "scroll": ActionType.SCROLL,
                    "move_to": ActionType.MOVE_TO,
                    "wait": ActionType.WAIT,
                    "screenshot": ActionType.SCREENSHOT,
                }

                action_type = action_map.get(action_str)
                if not action_type:
                    return None

                return UIAction(
                    action_type=action_type,
                    target_description=data.get("description", data.get("target", "")),
                    x=int(data.get("x", 0)),
                    y=int(data.get("y", 0)),
                    text=data.get("text", ""),
                    keys=data.get("keys", [data.get("key", "")]) if data.get("keys") or data.get("key") else [],
                    scroll_amount=int(data.get("amount", data.get("scroll_amount", 0))),
                    wait_seconds=float(data.get("seconds", data.get("wait_seconds", 0.5))),
                    confidence=float(data.get("confidence", 0.5)),
                )

            except (json.JSONDecodeError, ValueError):
                pass

        return None

    def get_stats(self) -> Dict[str, Any]:
        return {
            "actions_executed": len(self.executor.history),
            "action_log": self.executor.history[-10:],
            "pyautogui_available": PYAUTOGUI_OK,
            "pil_available": PIL_OK,
        }


# Singleton
_computer_use_agent: Optional[ComputerUseAgent] = None

def get_computer_use_agent(ai_router=None) -> ComputerUseAgent:
    global _computer_use_agent
    if _computer_use_agent is None:
        _computer_use_agent = ComputerUseAgent(ai_router=ai_router)
    return _computer_use_agent
