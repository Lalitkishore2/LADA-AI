import os
import time
import base64
import io
import logging
from typing import List, Dict, Optional, Union
import pyautogui
import pygetwindow as gw
from PIL import Image

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

logger = logging.getLogger(__name__)

# Safety settings
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.5  # Add a small pause between PyAutoGUI calls

class ComputerControl:
    """
    OS-level computer control class.
    Handles mouse, keyboard, and window management.
    """
    def __init__(self):
        # Get screen size for bounds checking
        self.screen_width, self.screen_height = pyautogui.size()
        logger.info(f"ComputerControl initialized. Resolution: {self.screen_width}x{self.screen_height}")

    def _check_bounds(self, x: int, y: int) -> bool:
        """Verify coordinates are within screen bounds."""
        if x < 0 or x >= self.screen_width or y < 0 or y >= self.screen_height:
            raise ValueError(f"Coordinates ({x}, {y}) are out of screen bounds ({self.screen_width}x{self.screen_height}).")
        return True

    def screenshot(self) -> str:
        """Capture the screen and return as base64 PNG."""
        try:
            if HAS_MSS:
                with mss.mss() as sct:
                    monitor = sct.monitors[0]  # All monitors
                    shot = sct.grab(monitor)
                    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            else:
                img = pyautogui.screenshot()
            
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return base64.b64encode(buf.getvalue()).decode('utf-8')
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
            raise

    def click(self, x: int, y: int, type: str = "left") -> Dict[str, Union[bool, str]]:
        """Click at specified coordinates."""
        try:
            self._check_bounds(x, y)
            pyautogui.click(x=x, y=y, button=type)
            return {"success": True, "action": f"clicked {type} at ({x}, {y})"}
        except Exception as e:
            logger.error(f"Click failed: {e}")
            return {"success": False, "error": str(e)}

    def type_text(self, text: str, interval: float = 0.05) -> Dict[str, Union[bool, str]]:
        """Type text sequentially."""
        try:
            pyautogui.write(text, interval=interval)
            return {"success": True, "action": f"typed text: '{text[:10]}...'"}
        except Exception as e:
            logger.error(f"Type failed: {e}")
            return {"success": False, "error": str(e)}

    def hotkey(self, *keys) -> Dict[str, Union[bool, str]]:
        """Press a combination of keys (e.g., 'ctrl', 'c')."""
        try:
            pyautogui.hotkey(*keys)
            return {"success": True, "action": f"pressed hotkey: {'+'.join(keys)}"}
        except Exception as e:
            logger.error(f"Hotkey failed: {e}")
            return {"success": False, "error": str(e)}

    def scroll(self, direction: str, amount: int) -> Dict[str, Union[bool, str]]:
        """Scroll mouse wheel. direction can be 'up' or 'down'."""
        try:
            clicks = amount if direction.lower() == 'up' else -amount
            pyautogui.scroll(clicks)
            return {"success": True, "action": f"scrolled {direction} {amount} clicks"}
        except Exception as e:
            logger.error(f"Scroll failed: {e}")
            return {"success": False, "error": str(e)}

    def get_windows(self) -> List[str]:
        """Get a list of all visible window titles."""
        try:
            windows = gw.getAllTitles()
            # Filter out empty titles
            return [w for w in windows if w.strip()]
        except Exception as e:
            logger.error(f"Failed to get windows: {e}")
            return []

    def focus_window(self, title: str) -> Dict[str, Union[bool, str]]:
        """Focus a window by its title."""
        try:
            windows = gw.getWindowsWithTitle(title)
            if not windows:
                return {"success": False, "error": f"No window found matching '{title}'"}
            
            win = windows[0]
            if win.isMinimized:
                win.restore()
            win.activate()
            return {"success": True, "action": f"focused window '{win.title}'"}
        except Exception as e:
            logger.error(f"Focus window failed: {e}")
            return {"success": False, "error": str(e)}

    def move_mouse(self, x: int, y: int, smooth: bool = True) -> Dict[str, Union[bool, str]]:
        """Move mouse to coordinates."""
        try:
            self._check_bounds(x, y)
            duration = 0.5 if smooth else 0.0
            pyautogui.moveTo(x, y, duration=duration, tween=pyautogui.easeInOutQuad)
            return {"success": True, "action": f"moved mouse to ({x}, {y})"}
        except Exception as e:
            logger.error(f"Move mouse failed: {e}")
            return {"success": False, "error": str(e)}
