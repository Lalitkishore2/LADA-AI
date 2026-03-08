"""
LADA v7.0 - Screen Vision Module
Screen capture, OCR, and visual AI analysis

Features:
- Screenshot capture (full screen, window, region)
- OCR text extraction with pytesseract
- AI-powered image analysis
- Screen element detection
"""

import os
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)

# Try to import required modules
try:
    import pyautogui
    PYAUTOGUI_OK = True
except ImportError:
    PYAUTOGUI_OK = False
    logger.warning("[ScreenVision] pyautogui not available")

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False
    logger.warning("[ScreenVision] PIL not available")

try:
    import pytesseract
    # Try common Tesseract paths on Windows
    tesseract_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        r'C:\Users\{}\AppData\Local\Tesseract-OCR\tesseract.exe'.format(os.getenv('USERNAME', '')),
    ]
    for path in tesseract_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            break
    OCR_OK = True
except ImportError:
    OCR_OK = False
    logger.warning("[ScreenVision] pytesseract not available")


class ScreenVision:
    """
    Screen capture and vision analysis module.
    Combines OCR with AI for understanding screen content.
    """
    
    def __init__(self, ai_router=None):
        """
        Initialize screen vision.
        
        Args:
            ai_router: HybridAIRouter instance for AI analysis
        """
        self.ai_router = ai_router
        self.screenshot_dir = Path("screenshots")
        self.screenshot_dir.mkdir(exist_ok=True)
        self.last_screenshot = None
        
    def capture_screen(self, region: Optional[Tuple[int, int, int, int]] = None) -> Dict[str, Any]:
        """
        Capture screenshot of entire screen or region.
        
        Args:
            region: Optional (x, y, width, height) tuple
            
        Returns:
            {'success': True, 'path': '...', 'image': PIL.Image}
        """
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            if region:
                screenshot = pyautogui.screenshot(region=region)
            else:
                screenshot = pyautogui.screenshot()
            
            # Save with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
            filepath = self.screenshot_dir / filename
            screenshot.save(str(filepath))
            
            self.last_screenshot = screenshot
            
            logger.info(f"[ScreenVision] Screenshot saved: {filepath}")
            
            return {
                'success': True,
                'path': str(filepath),
                'image': screenshot,
                'size': screenshot.size
            }
            
        except Exception as e:
            logger.error(f"[ScreenVision] Screenshot error: {e}")
            return {'success': False, 'error': str(e)}
    
    def capture_active_window(self) -> Dict[str, Any]:
        """Capture screenshot of active window only."""
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            import pygetwindow as gw
            active = gw.getActiveWindow()
            if active:
                region = (active.left, active.top, active.width, active.height)
                return self.capture_screen(region=region)
            else:
                return self.capture_screen()  # Fallback to full screen
        except ImportError:
            return self.capture_screen()  # Full screen fallback
    
    def extract_text(self, image=None, path: str = None) -> Dict[str, Any]:
        """
        Extract text from image using OCR.
        
        Args:
            image: PIL Image object
            path: Path to image file
            
        Returns:
            {'success': True, 'text': '...', 'confidence': 0.9}
        """
        if not OCR_OK:
            return {
                'success': False, 
                'error': 'OCR not available. Install Tesseract and pytesseract.'
            }
        
        try:
            # Load image
            if path:
                image = Image.open(path)
            elif image is None and self.last_screenshot:
                image = self.last_screenshot
            elif image is None:
                return {'success': False, 'error': 'No image provided'}
            
            # Run OCR
            text = pytesseract.image_to_string(image)
            
            # Get detailed data for confidence
            try:
                data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
                confidences = [int(c) for c in data['conf'] if int(c) > 0]
                avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            except:
                avg_confidence = 0
            
            return {
                'success': True,
                'text': text.strip(),
                'confidence': avg_confidence / 100,
                'word_count': len(text.split())
            }
            
        except Exception as e:
            logger.error(f"[ScreenVision] OCR error: {e}")
            return {'success': False, 'error': str(e)}
    
    def find_text_on_screen(self, search_text: str) -> Dict[str, Any]:
        """
        Find text location on screen.
        
        Args:
            search_text: Text to find
            
        Returns:
            {'success': True, 'found': True, 'locations': [(x, y, w, h), ...]}
        """
        if not OCR_OK:
            return {'success': False, 'error': 'OCR not available'}
        
        try:
            # Capture screen
            result = self.capture_screen()
            if not result['success']:
                return result
            
            image = result['image']
            
            # Get word-level OCR data
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            
            locations = []
            search_lower = search_text.lower()
            
            for i, word in enumerate(data['text']):
                if search_lower in word.lower():
                    x = data['left'][i]
                    y = data['top'][i]
                    w = data['width'][i]
                    h = data['height'][i]
                    locations.append((x, y, w, h))
            
            return {
                'success': True,
                'found': len(locations) > 0,
                'search_text': search_text,
                'locations': locations,
                'count': len(locations)
            }
            
        except Exception as e:
            logger.error(f"[ScreenVision] Find text error: {e}")
            return {'success': False, 'error': str(e)}
    
    def read_screen(self) -> Dict[str, Any]:
        """
        Capture screen and extract all text.
        
        Returns:
            {'success': True, 'text': '...', 'summary': '...'}
        """
        # Capture
        capture_result = self.capture_screen()
        if not capture_result['success']:
            return capture_result
        
        # OCR
        ocr_result = self.extract_text(capture_result['image'])
        if not ocr_result['success']:
            return ocr_result
        
        # Summarize with AI if available
        summary = None
        if self.ai_router and len(ocr_result['text']) > 100:
            try:
                prompt = f"Summarize this screen content in 2-3 sentences:\n\n{ocr_result['text'][:2000]}"
                summary = self.ai_router.query(prompt)
            except:
                pass
        
        return {
            'success': True,
            'text': ocr_result['text'],
            'confidence': ocr_result.get('confidence', 0),
            'word_count': ocr_result.get('word_count', 0),
            'screenshot_path': capture_result['path'],
            'summary': summary
        }
    
    def analyze_screen(self, query: str = None) -> Dict[str, Any]:
        """
        Analyze screen content with AI.
        
        Args:
            query: Optional question about the screen
            
        Returns:
            {'success': True, 'analysis': '...'}
        """
        # Get screen text
        result = self.read_screen()
        if not result['success']:
            return result
        
        if not self.ai_router:
            return {
                'success': True,
                'text': result['text'],
                'analysis': 'AI analysis not available.'
            }
        
        try:
            if query:
                prompt = f"Based on this screen content, answer: {query}\n\nScreen content:\n{result['text'][:3000]}"
            else:
                prompt = f"Describe what's visible on this screen and identify any important information:\n\n{result['text'][:3000]}"
            
            analysis = self.ai_router.query(prompt)
            
            return {
                'success': True,
                'text': result['text'],
                'analysis': analysis,
                'screenshot_path': result['screenshot_path']
            }
            
        except Exception as e:
            return {
                'success': True,
                'text': result['text'],
                'analysis': f'Analysis failed: {e}'
            }
    
    def click_on_text(self, search_text: str) -> Dict[str, Any]:
        """
        Find text and click on it.
        
        Args:
            search_text: Text to find and click
            
        Returns:
            {'success': True, 'clicked': True, 'location': (x, y)}
        """
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        # Find text
        result = self.find_text_on_screen(search_text)
        if not result['success']:
            return result
        
        if not result['found']:
            return {
                'success': True,
                'clicked': False,
                'error': f"Text '{search_text}' not found on screen"
            }
        
        # Click on first match (center of bounding box)
        x, y, w, h = result['locations'][0]
        click_x = x + w // 2
        click_y = y + h // 2
        
        try:
            pyautogui.click(click_x, click_y)
            return {
                'success': True,
                'clicked': True,
                'location': (click_x, click_y),
                'text': search_text
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}


# Singleton instance
_screen_vision = None

def get_screen_vision(ai_router=None) -> ScreenVision:
    """Get or create screen vision instance."""
    global _screen_vision
    if _screen_vision is None:
        _screen_vision = ScreenVision(ai_router)
    elif ai_router and not _screen_vision.ai_router:
        _screen_vision.ai_router = ai_router
    return _screen_vision


# Quick functions
def capture_screen(region=None) -> Dict[str, Any]:
    """Take a screenshot."""
    return get_screen_vision().capture_screen(region)

def read_screen_text() -> str:
    """Read text from current screen."""
    result = get_screen_vision().read_screen()
    return result.get('text', '') if result['success'] else ''

def find_and_click(text: str) -> bool:
    """Find text on screen and click it."""
    result = get_screen_vision().click_on_text(text)
    return result.get('clicked', False)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 50)
    print("LADA Screen Vision Test")
    print("=" * 50)
    
    vision = ScreenVision()
    
    # Test screenshot
    print("\n📸 Taking screenshot...")
    result = vision.capture_screen()
    if result['success']:
        print(f"  ✓ Saved to: {result['path']}")
        print(f"  ✓ Size: {result['size']}")
    else:
        print(f"  ✗ Error: {result['error']}")
    
    # Test OCR
    if OCR_OK:
        print("\n🔍 Running OCR...")
        result = vision.extract_text()
        if result['success']:
            text = result['text'][:200] + "..." if len(result['text']) > 200 else result['text']
            print(f"  ✓ Extracted {result['word_count']} words")
            print(f"  ✓ Confidence: {result['confidence']:.1%}")
            print(f"  ✓ Text: {text}")
        else:
            print(f"  ✗ Error: {result['error']}")
    else:
        print("\n🔍 OCR not available (Tesseract not installed)")
    
    print("\n" + "=" * 50)
    print("Test complete!")
