"""
LADA v9.0 - GUI Automator Module
Complete GUI automation for JARVIS-level interaction.

Features:
- Click, double-click, right-click at coordinates
- Type text with human-like delays
- Keyboard shortcuts and hotkeys
- Find elements by image (template matching)
- Find elements by text (OCR)
- Screenshot and screen analysis
- Mouse movement and scrolling
- Drag and drop
"""

import os
import time
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass
from io import BytesIO
import base64

logger = logging.getLogger(__name__)

# Try to import pyautogui
try:
    import pyautogui
    # Configure pyautogui
    pyautogui.PAUSE = 0.1  # Small pause between actions
    pyautogui.FAILSAFE = True  # Move mouse to corner to abort
    PYAUTOGUI_OK = True
except ImportError:
    pyautogui = None
    PYAUTOGUI_OK = False
    logger.warning("[!] pyautogui not available - GUI automation limited")

# Try to import PIL for screenshots
try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    Image = None
    PIL_OK = False

# Try to import pytesseract for OCR
try:
    import pytesseract
    PYTESSERACT_OK = True
except ImportError:
    pytesseract = None
    PYTESSERACT_OK = False
    logger.warning("[!] pytesseract not available - OCR disabled")

# Try to import cv2 for image matching
try:
    import cv2
    import numpy as np
    CV2_OK = True
except ImportError:
    cv2 = None
    np = None
    CV2_OK = False
    logger.warning("[!] opencv-python not available - image matching disabled")


@dataclass
class ScreenPosition:
    """A position on the screen"""
    x: int
    y: int
    confidence: float = 1.0


@dataclass
class FoundElement:
    """An element found on screen"""
    x: int
    y: int
    width: int
    height: int
    text: str = ""
    confidence: float = 0.0


class GUIAutomator:
    """
    Complete GUI automation for mouse/keyboard control.
    Enables JARVIS-level interaction with any application.
    """
    
    def __init__(self):
        """Initialize the GUI automator"""
        self.screenshots_dir = Path("screenshots")
        self.screenshots_dir.mkdir(exist_ok=True)
        
        # Get screen size
        if PYAUTOGUI_OK:
            self.screen_width, self.screen_height = pyautogui.size()
        else:
            self.screen_width, self.screen_height = 1920, 1080
        
        # Default typing speed (seconds between keys)
        self.typing_interval = 0.05
        
        logger.info(f"[OK] GUI Automator initialized ({self.screen_width}x{self.screen_height})")
    
    # ==================== MOUSE CONTROL ====================
    
    def click(self, x: Optional[int] = None, y: Optional[int] = None, 
              button: str = 'left', clicks: int = 1) -> Dict[str, Any]:
        """
        Click at a position (or current position if no coords given).
        
        Args:
            x: X coordinate (optional)
            y: Y coordinate (optional)
            button: 'left', 'right', or 'middle'
            clicks: Number of clicks (1=single, 2=double)
        
        Returns:
            Dict with success status
        """
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            if x is not None and y is not None:
                pyautogui.click(x, y, button=button, clicks=clicks)
                pos = (x, y)
            else:
                pyautogui.click(button=button, clicks=clicks)
                pos = pyautogui.position()
            
            action = "double-clicked" if clicks == 2 else "clicked"
            logger.info(f"[OK] {button.capitalize()} {action} at {pos}")
            
            return {
                'success': True,
                'position': {'x': pos[0], 'y': pos[1]},
                'button': button,
                'clicks': clicks,
                'message': f"{button.capitalize()} {action} at ({pos[0]}, {pos[1]})"
            }
        
        except Exception as e:
            logger.error(f"[X] Click failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def double_click(self, x: Optional[int] = None, y: Optional[int] = None) -> Dict[str, Any]:
        """Double-click at position"""
        return self.click(x, y, clicks=2)
    
    def right_click(self, x: Optional[int] = None, y: Optional[int] = None) -> Dict[str, Any]:
        """Right-click at position"""
        return self.click(x, y, button='right')
    
    def middle_click(self, x: Optional[int] = None, y: Optional[int] = None) -> Dict[str, Any]:
        """Middle-click at position"""
        return self.click(x, y, button='middle')
    
    def move_mouse(self, x: int, y: int, duration: float = 0.25) -> Dict[str, Any]:
        """
        Move mouse to a position.
        
        Args:
            x: X coordinate
            y: Y coordinate
            duration: Time to take for movement (smoother if > 0)
        
        Returns:
            Dict with success status
        """
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            pyautogui.moveTo(x, y, duration=duration)
            
            return {
                'success': True,
                'position': {'x': x, 'y': y},
                'message': f"Moved mouse to ({x}, {y})"
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_mouse_position(self) -> Dict[str, Any]:
        """Get current mouse position"""
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            pos = pyautogui.position()
            return {
                'success': True,
                'x': pos[0],
                'y': pos[1]
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def scroll(self, direction: str = 'down', amount: int = 3) -> Dict[str, Any]:
        """
        Scroll the mouse wheel.
        
        Args:
            direction: 'up' or 'down'
            amount: Number of scroll "clicks"
        
        Returns:
            Dict with success status
        """
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            scroll_amount = amount if direction.lower() == 'up' else -amount
            pyautogui.scroll(scroll_amount)
            
            return {
                'success': True,
                'direction': direction,
                'amount': amount,
                'message': f"Scrolled {direction} by {amount}"
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def drag(self, start_x: int, start_y: int, end_x: int, end_y: int, 
             duration: float = 0.5) -> Dict[str, Any]:
        """
        Drag from one position to another.
        
        Args:
            start_x, start_y: Starting position
            end_x, end_y: Ending position
            duration: Time for drag operation
        
        Returns:
            Dict with success status
        """
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            pyautogui.moveTo(start_x, start_y)
            pyautogui.drag(end_x - start_x, end_y - start_y, duration=duration)
            
            return {
                'success': True,
                'from': {'x': start_x, 'y': start_y},
                'to': {'x': end_x, 'y': end_y},
                'message': f"Dragged from ({start_x}, {start_y}) to ({end_x}, {end_y})"
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== KEYBOARD CONTROL ====================
    
    def type_text(self, text: str, interval: Optional[float] = None) -> Dict[str, Any]:
        """
        Type text with human-like delays.
        
        Args:
            text: Text to type
            interval: Seconds between keystrokes (None = default)
        
        Returns:
            Dict with success status
        """
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            typing_speed = interval if interval is not None else self.typing_interval
            pyautogui.typewrite(text, interval=typing_speed)
            
            logger.info(f"[OK] Typed: {text[:30]}...")
            return {
                'success': True,
                'text': text,
                'length': len(text),
                'message': f"Typed {len(text)} characters"
            }
        
        except Exception as e:
            logger.error(f"[X] Type failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def type_unicode(self, text: str) -> Dict[str, Any]:
        """
        Type text including unicode characters (uses clipboard).
        
        Args:
            text: Text to type (including unicode)
        
        Returns:
            Dict with success status
        """
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            import pyperclip
            
            # Save current clipboard
            old_clipboard = pyperclip.paste()
            
            # Copy text to clipboard
            pyperclip.copy(text)
            
            # Paste
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.1)
            
            # Restore clipboard
            pyperclip.copy(old_clipboard)
            
            return {
                'success': True,
                'text': text,
                'message': f"Typed (via clipboard): {text[:30]}..."
            }
        
        except ImportError:
            # Fallback: try regular typewrite
            return self.type_text(text.encode('ascii', 'ignore').decode())
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def press_key(self, key: str) -> Dict[str, Any]:
        """
        Press a single key.
        
        Args:
            key: Key to press ('enter', 'tab', 'escape', 'space', 'backspace', etc.)
        
        Returns:
            Dict with success status
        """
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            pyautogui.press(key)
            
            return {
                'success': True,
                'key': key,
                'message': f"Pressed {key}"
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def hotkey(self, *keys) -> Dict[str, Any]:
        """
        Press a keyboard shortcut (multiple keys).
        
        Args:
            *keys: Keys to press together (e.g., 'ctrl', 'c' for Ctrl+C)
        
        Returns:
            Dict with success status
        """
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            pyautogui.hotkey(*keys)
            
            key_combo = '+'.join(keys)
            return {
                'success': True,
                'keys': list(keys),
                'combo': key_combo,
                'message': f"Pressed {key_combo}"
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def hold_key(self, key: str, duration: float = 1.0) -> Dict[str, Any]:
        """
        Hold a key for a duration.
        
        Args:
            key: Key to hold
            duration: Seconds to hold
        
        Returns:
            Dict with success status
        """
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            pyautogui.keyDown(key)
            time.sleep(duration)
            pyautogui.keyUp(key)
            
            return {
                'success': True,
                'key': key,
                'duration': duration,
                'message': f"Held {key} for {duration}s"
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # Common shortcuts
    def copy(self) -> Dict[str, Any]:
        """Press Ctrl+C"""
        return self.hotkey('ctrl', 'c')
    
    def paste(self) -> Dict[str, Any]:
        """Press Ctrl+V"""
        return self.hotkey('ctrl', 'v')
    
    def cut(self) -> Dict[str, Any]:
        """Press Ctrl+X"""
        return self.hotkey('ctrl', 'x')
    
    def undo(self) -> Dict[str, Any]:
        """Press Ctrl+Z"""
        return self.hotkey('ctrl', 'z')
    
    def redo(self) -> Dict[str, Any]:
        """Press Ctrl+Y"""
        return self.hotkey('ctrl', 'y')
    
    def select_all(self) -> Dict[str, Any]:
        """Press Ctrl+A"""
        return self.hotkey('ctrl', 'a')
    
    def save(self) -> Dict[str, Any]:
        """Press Ctrl+S"""
        return self.hotkey('ctrl', 's')
    
    def find(self) -> Dict[str, Any]:
        """Press Ctrl+F"""
        return self.hotkey('ctrl', 'f')
    
    def switch_app(self) -> Dict[str, Any]:
        """Press Alt+Tab"""
        return self.hotkey('alt', 'tab')
    
    # ==================== SCREENSHOTS ====================
    
    def screenshot(self, region: Optional[Tuple[int, int, int, int]] = None,
                   save_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Take a screenshot.
        
        Args:
            region: Optional (x, y, width, height) to capture
            save_path: Optional path to save screenshot
        
        Returns:
            Dict with success status and image data
        """
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            if region:
                screenshot = pyautogui.screenshot(region=region)
            else:
                screenshot = pyautogui.screenshot()
            
            # Generate filename if not provided
            if not save_path:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                save_path = str(self.screenshots_dir / f"screenshot_{timestamp}.png")
            
            screenshot.save(save_path)
            
            # Also create base64 for potential API use
            buffer = BytesIO()
            screenshot.save(buffer, format='PNG')
            base64_image = base64.b64encode(buffer.getvalue()).decode()
            
            logger.info(f"[OK] Screenshot saved: {save_path}")
            return {
                'success': True,
                'path': save_path,
                'size': {'width': screenshot.width, 'height': screenshot.height},
                'base64': base64_image[:100] + '...',  # Truncated for display
                'message': f"Screenshot saved to {save_path}"
            }
        
        except Exception as e:
            logger.error(f"[X] Screenshot failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_pixel_color(self, x: int, y: int) -> Dict[str, Any]:
        """
        Get the color of a pixel.
        
        Args:
            x: X coordinate
            y: Y coordinate
        
        Returns:
            Dict with RGB color
        """
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            screenshot = pyautogui.screenshot(region=(x, y, 1, 1))
            pixel = screenshot.getpixel((0, 0))
            
            return {
                'success': True,
                'position': {'x': x, 'y': y},
                'color': {'r': pixel[0], 'g': pixel[1], 'b': pixel[2]},
                'hex': '#{:02x}{:02x}{:02x}'.format(*pixel)
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== ELEMENT FINDING ====================
    
    def find_image_on_screen(self, image_path: str, confidence: float = 0.8) -> Dict[str, Any]:
        """
        Find an image on the screen (template matching).
        
        Args:
            image_path: Path to image to find
            confidence: Match confidence threshold (0-1)
        
        Returns:
            Dict with position if found
        """
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            location = pyautogui.locateOnScreen(image_path, confidence=confidence)
            
            if location:
                center = pyautogui.center(location)
                return {
                    'success': True,
                    'found': True,
                    'position': {'x': center.x, 'y': center.y},
                    'region': {
                        'x': location.left,
                        'y': location.top,
                        'width': location.width,
                        'height': location.height
                    },
                    'confidence': confidence
                }
            else:
                return {
                    'success': True,
                    'found': False,
                    'message': f"Image not found on screen"
                }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def find_all_images_on_screen(self, image_path: str, confidence: float = 0.8) -> Dict[str, Any]:
        """
        Find all instances of an image on screen.
        
        Args:
            image_path: Path to image to find
            confidence: Match confidence threshold
        
        Returns:
            Dict with all positions found
        """
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            locations = list(pyautogui.locateAllOnScreen(image_path, confidence=confidence))
            
            if locations:
                positions = []
                for loc in locations:
                    center = pyautogui.center(loc)
                    positions.append({
                        'x': center.x,
                        'y': center.y,
                        'region': {
                            'x': loc.left,
                            'y': loc.top,
                            'width': loc.width,
                            'height': loc.height
                        }
                    })
                
                return {
                    'success': True,
                    'found': True,
                    'count': len(positions),
                    'positions': positions
                }
            else:
                return {
                    'success': True,
                    'found': False,
                    'count': 0,
                    'positions': []
                }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def click_on_image(self, image_path: str, confidence: float = 0.8) -> Dict[str, Any]:
        """
        Find an image and click on it.
        
        Args:
            image_path: Path to image to find and click
            confidence: Match confidence threshold
        
        Returns:
            Dict with success status
        """
        result = self.find_image_on_screen(image_path, confidence)
        
        if result.get('found'):
            pos = result['position']
            return self.click(pos['x'], pos['y'])
        
        return {
            'success': False,
            'error': 'Image not found on screen'
        }
    
    def find_text_on_screen(self, search_text: str, 
                            region: Optional[Tuple[int, int, int, int]] = None) -> Dict[str, Any]:
        """
        Find text on screen using OCR.
        
        Args:
            search_text: Text to find
            region: Optional region to search in (x, y, width, height)
        
        Returns:
            Dict with position if found
        """
        if not PYTESSERACT_OK:
            return {'success': False, 'error': 'pytesseract not available'}
        
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            # Take screenshot
            if region:
                screenshot = pyautogui.screenshot(region=region)
                offset_x, offset_y = region[0], region[1]
            else:
                screenshot = pyautogui.screenshot()
                offset_x, offset_y = 0, 0
            
            # Get OCR data with bounding boxes
            data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)
            
            search_lower = search_text.lower()
            matches = []
            
            for i, text in enumerate(data['text']):
                if text and search_lower in text.lower():
                    x = data['left'][i] + offset_x
                    y = data['top'][i] + offset_y
                    w = data['width'][i]
                    h = data['height'][i]
                    conf = data['conf'][i]
                    
                    matches.append(FoundElement(
                        x=x + w // 2,  # Center
                        y=y + h // 2,
                        width=w,
                        height=h,
                        text=text,
                        confidence=conf / 100.0
                    ))
            
            if matches:
                best_match = max(matches, key=lambda m: m.confidence)
                return {
                    'success': True,
                    'found': True,
                    'position': {'x': best_match.x, 'y': best_match.y},
                    'text': best_match.text,
                    'confidence': best_match.confidence,
                    'all_matches': len(matches)
                }
            else:
                return {
                    'success': True,
                    'found': False,
                    'message': f"Text '{search_text}' not found on screen"
                }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def click_on_text(self, search_text: str, 
                      region: Optional[Tuple[int, int, int, int]] = None) -> Dict[str, Any]:
        """
        Find text on screen and click on it.
        
        Args:
            search_text: Text to find and click
            region: Optional region to search in
        
        Returns:
            Dict with success status
        """
        result = self.find_text_on_screen(search_text, region)
        
        if result.get('found'):
            pos = result['position']
            return self.click(pos['x'], pos['y'])
        
        return {
            'success': False,
            'error': f"Text '{search_text}' not found on screen"
        }
    
    def extract_text_from_screen(self, 
                                  region: Optional[Tuple[int, int, int, int]] = None) -> Dict[str, Any]:
        """
        Extract all text from screen using OCR.
        
        Args:
            region: Optional region to extract from (x, y, width, height)
        
        Returns:
            Dict with extracted text
        """
        if not PYTESSERACT_OK:
            return {'success': False, 'error': 'pytesseract not available'}
        
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            # Take screenshot
            if region:
                screenshot = pyautogui.screenshot(region=region)
            else:
                screenshot = pyautogui.screenshot()
            
            # Extract text
            text = pytesseract.image_to_string(screenshot)
            
            return {
                'success': True,
                'text': text.strip(),
                'length': len(text.strip()),
                'region': region if region else 'full_screen'
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== ELEMENT WAITING ====================
    
    def wait_for_image(self, image_path: str, timeout: int = 30, 
                       confidence: float = 0.8) -> Dict[str, Any]:
        """
        Wait for an image to appear on screen.
        
        Args:
            image_path: Path to image to wait for
            timeout: Maximum seconds to wait
            confidence: Match confidence threshold
        
        Returns:
            Dict with position when found
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            result = self.find_image_on_screen(image_path, confidence)
            
            if result.get('found'):
                result['wait_time'] = time.time() - start_time
                return result
            
            time.sleep(0.5)
        
        return {
            'success': False,
            'error': f"Image not found within {timeout}s"
        }
    
    def wait_for_text(self, search_text: str, timeout: int = 30) -> Dict[str, Any]:
        """
        Wait for text to appear on screen.
        
        Args:
            search_text: Text to wait for
            timeout: Maximum seconds to wait
        
        Returns:
            Dict with position when found
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            result = self.find_text_on_screen(search_text)
            
            if result.get('found'):
                result['wait_time'] = time.time() - start_time
                return result
            
            time.sleep(0.5)
        
        return {
            'success': False,
            'error': f"Text '{search_text}' not found within {timeout}s"
        }
    
    # ==================== UTILITY METHODS ====================
    
    def get_screen_size(self) -> Dict[str, Any]:
        """Get screen dimensions"""
        return {
            'success': True,
            'width': self.screen_width,
            'height': self.screen_height
        }
    
    def set_typing_speed(self, interval: float) -> Dict[str, Any]:
        """
        Set the default typing speed.
        
        Args:
            interval: Seconds between keystrokes
        
        Returns:
            Dict with success status
        """
        self.typing_interval = interval
        return {
            'success': True,
            'interval': interval,
            'message': f"Typing speed set to {interval}s between keys"
        }
    
    def alert(self, message: str, title: str = "LADA Alert") -> Dict[str, Any]:
        """
        Show an alert dialog.
        
        Args:
            message: Message to display
            title: Dialog title
        
        Returns:
            Dict with success status
        """
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            pyautogui.alert(message, title)
            return {'success': True, 'message': 'Alert shown'}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def confirm(self, message: str, title: str = "LADA Confirm") -> Dict[str, Any]:
        """
        Show a confirmation dialog.
        
        Args:
            message: Message to display
            title: Dialog title
        
        Returns:
            Dict with user's choice
        """
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            result = pyautogui.confirm(message, title)
            return {
                'success': True,
                'confirmed': result == 'OK',
                'response': result
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def prompt(self, message: str, default: str = "", 
               title: str = "LADA Input") -> Dict[str, Any]:
        """
        Show an input prompt dialog.
        
        Args:
            message: Message to display
            default: Default input value
            title: Dialog title
        
        Returns:
            Dict with user's input
        """
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            result = pyautogui.prompt(message, title, default)
            return {
                'success': True,
                'input': result,
                'cancelled': result is None
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}


# Factory function for workflow engine integration
def create_gui_automator() -> GUIAutomator:
    """Create and return a GUIAutomator instance"""
    return GUIAutomator()


if __name__ == '__main__':
    # Test the GUI automator
    logging.basicConfig(level=logging.INFO)
    gui = GUIAutomator()
    
    print("\n=== Testing GUI Automator ===")
    
    # Get screen size
    size = gui.get_screen_size()
    print(f"Screen size: {size['width']}x{size['height']}")
    
    # Get mouse position
    pos = gui.get_mouse_position()
    print(f"Mouse position: ({pos.get('x', 'N/A')}, {pos.get('y', 'N/A')})")
    
    # Take screenshot
    result = gui.screenshot()
    if result['success']:
        print(f"Screenshot saved: {result['path']}")
    
    # Test OCR (if available)
    if PYTESSERACT_OK:
        result = gui.extract_text_from_screen(region=(0, 0, 500, 100))
        if result['success']:
            print(f"Extracted text (first 100 chars): {result['text'][:100]}...")
    
    print("\n[OK] GUI Automator tests complete!")
    print("\nNote: Full testing requires user interaction.")
    print("Try commands like:")
    print("  gui.click(100, 100)")
    print("  gui.type_text('Hello World')")
    print("  gui.hotkey('ctrl', 'c')")
    print("  gui.find_text_on_screen('OK')")
