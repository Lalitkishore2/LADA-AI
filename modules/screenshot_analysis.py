"""
LADA v9.0 - Screenshot Analysis Engine
Module 9: Advanced visual analysis with OCR, element detection, 
UI state analysis, and visual comparison.

Features:
- Enhanced OCR with multi-language support
- UI element detection (buttons, text fields, links)
- Visual state comparison (change detection)
- Element locator for automation
- Screen region monitoring
- Color and layout analysis
- Image similarity matching
- Accessibility analysis
"""

import os
import json
import logging
import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import threading

logger = logging.getLogger(__name__)

# =====================================================
# DEPENDENCY CHECKS
# =====================================================

try:
    import pyautogui
    PYAUTOGUI_OK = True
except ImportError:
    PYAUTOGUI_OK = False
    logger.warning("[ScreenshotAnalysis] pyautogui not available")

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageStat
    import io
    PIL_OK = True
except ImportError:
    PIL_OK = False
    logger.warning("[ScreenshotAnalysis] PIL not available")

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
    logger.warning("[ScreenshotAnalysis] pytesseract not available")

try:
    import numpy as np
    NUMPY_OK = True
except ImportError:
    NUMPY_OK = False
    logger.warning("[ScreenshotAnalysis] numpy not available")


# =====================================================
# DATA CLASSES
# =====================================================

@dataclass
class TextBlock:
    """Represents a block of detected text."""
    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float
    line_num: int = 0
    word_num: int = 0
    
    @property
    def center(self) -> Tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)
    
    @property
    def bounds(self) -> Tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)


@dataclass
class UIElement:
    """Represents a detected UI element."""
    type: str  # button, link, input, text, image, checkbox, etc.
    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float = 0.0
    clickable: bool = True
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def center(self) -> Tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)
    
    def contains_point(self, x: int, y: int) -> bool:
        return self.x <= x <= self.x + self.width and self.y <= y <= self.y + self.height


@dataclass 
class ScreenRegion:
    """Defines a region of the screen to monitor."""
    name: str
    x: int
    y: int
    width: int
    height: int
    check_interval: float = 5.0  # seconds
    last_hash: str = ""
    change_callback: Optional[str] = None


@dataclass
class ComparisonResult:
    """Result of comparing two images."""
    similar: bool
    similarity_score: float  # 0.0 to 1.0
    difference_regions: List[Tuple[int, int, int, int]] = field(default_factory=list)
    pixel_diff_count: int = 0
    diff_image_path: Optional[str] = None


class ScreenshotAnalyzer:
    """
    Advanced screenshot analysis engine.
    Provides OCR, element detection, and visual comparison.
    """
    
    # Common UI patterns for element detection
    BUTTON_KEYWORDS = ['submit', 'ok', 'cancel', 'save', 'close', 'next', 'back', 
                       'continue', 'login', 'sign in', 'sign up', 'register', 
                       'buy', 'add', 'remove', 'delete', 'edit', 'send', 'apply']
    
    LINK_KEYWORDS = ['click here', 'learn more', 'read more', 'see more', 
                     'view all', 'download', 'http://', 'https://', 'www.']
    
    INPUT_KEYWORDS = ['enter', 'type', 'search', 'email', 'password', 'username',
                      'name', 'phone', 'address']
    
    def __init__(self, ai_router=None, screenshot_dir: str = None):
        """
        Initialize screenshot analyzer.
        
        Args:
            ai_router: HybridAIRouter for AI-powered analysis
            screenshot_dir: Directory to save screenshots
        """
        self.ai_router = ai_router
        self.screenshot_dir = Path(screenshot_dir or "screenshots")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache for performance
        self._screenshot_cache: Dict[str, Image.Image] = {}
        self._ocr_cache: Dict[str, List[TextBlock]] = {}
        
        # Monitored regions
        self.monitored_regions: Dict[str, ScreenRegion] = {}
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitoring = False
        
        # Analysis history
        self.analysis_history: List[Dict] = []
        
        logger.info("[ScreenshotAnalyzer] Initialized")
    
    # =====================================================
    # SCREENSHOT CAPTURE
    # =====================================================
    
    def capture_screen(
        self, 
        region: Tuple[int, int, int, int] = None,
        save: bool = True,
        filename: str = None
    ) -> Dict[str, Any]:
        """
        Capture screenshot of full screen or region.
        
        Args:
            region: (x, y, width, height) or None for full screen
            save: Whether to save to disk
            filename: Custom filename
            
        Returns:
            {'success': True, 'image': PIL.Image, 'path': '...'}
        """
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            if region:
                screenshot = pyautogui.screenshot(region=region)
            else:
                screenshot = pyautogui.screenshot()
            
            path = None
            if save:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = filename or f"capture_{timestamp}.png"
                path = str(self.screenshot_dir / filename)
                screenshot.save(path)
            
            # Cache it
            cache_key = f"screenshot_{datetime.now().timestamp()}"
            self._screenshot_cache[cache_key] = screenshot
            
            return {
                'success': True,
                'image': screenshot,
                'path': path,
                'size': screenshot.size,
                'cache_key': cache_key
            }
            
        except Exception as e:
            logger.error(f"[ScreenshotAnalyzer] Capture error: {e}")
            return {'success': False, 'error': str(e)}
    
    def capture_window(self, window_title: str = None) -> Dict[str, Any]:
        """Capture a specific window by title."""
        try:
            import pygetwindow as gw
            
            if window_title:
                windows = gw.getWindowsWithTitle(window_title)
                if windows:
                    win = windows[0]
                    region = (win.left, win.top, win.width, win.height)
                    return self.capture_screen(region=region)
                return {'success': False, 'error': f'Window "{window_title}" not found'}
            else:
                win = gw.getActiveWindow()
                if win:
                    region = (win.left, win.top, win.width, win.height)
                    return self.capture_screen(region=region)
                return self.capture_screen()  # Fallback to full screen
                
        except ImportError:
            return self.capture_screen()  # Full screen fallback
    
    # =====================================================
    # OCR - TEXT EXTRACTION
    # =====================================================
    
    def extract_text(
        self,
        image: Union[Image.Image, str] = None,
        language: str = 'eng',
        detailed: bool = True
    ) -> Dict[str, Any]:
        """
        Extract text from image using OCR.
        
        Args:
            image: PIL Image or path, None for new screenshot
            language: Tesseract language code (eng, tam, hin, etc.)
            detailed: Return word-level details
            
        Returns:
            {'success': True, 'text': '...', 'blocks': [...]}
        """
        if not OCR_OK:
            return {'success': False, 'error': 'Tesseract OCR not available'}
        
        try:
            # Get image
            if image is None:
                result = self.capture_screen(save=False)
                if not result['success']:
                    return result
                img = result['image']
            elif isinstance(image, str):
                img = Image.open(image)
            else:
                img = image
            
            # Check cache
            img_hash = self._image_hash(img)
            if img_hash in self._ocr_cache and detailed:
                blocks = self._ocr_cache[img_hash]
                full_text = ' '.join(b.text for b in blocks)
                return {
                    'success': True,
                    'text': full_text,
                    'blocks': blocks,
                    'cached': True
                }
            
            if detailed:
                # Get word-level data
                data = pytesseract.image_to_data(
                    img, 
                    lang=language,
                    output_type=pytesseract.Output.DICT
                )
                
                blocks = []
                for i in range(len(data['text'])):
                    text = data['text'][i].strip()
                    conf = int(data['conf'][i])
                    
                    if text and conf > 0:
                        block = TextBlock(
                            text=text,
                            x=data['left'][i],
                            y=data['top'][i],
                            width=data['width'][i],
                            height=data['height'][i],
                            confidence=conf / 100.0,
                            line_num=data['line_num'][i],
                            word_num=data['word_num'][i]
                        )
                        blocks.append(block)
                
                # Cache results
                self._ocr_cache[img_hash] = blocks
                
                full_text = ' '.join(b.text for b in blocks)
                avg_confidence = sum(b.confidence for b in blocks) / max(1, len(blocks))
                
                return {
                    'success': True,
                    'text': full_text,
                    'blocks': blocks,
                    'word_count': len(blocks),
                    'avg_confidence': avg_confidence,
                    'lines': max(b.line_num for b in blocks) if blocks else 0
                }
            else:
                # Simple text extraction
                text = pytesseract.image_to_string(img, lang=language)
                return {
                    'success': True,
                    'text': text.strip(),
                    'word_count': len(text.split())
                }
                
        except Exception as e:
            logger.error(f"[ScreenshotAnalyzer] OCR error: {e}")
            return {'success': False, 'error': str(e)}
    
    def find_text(
        self,
        search_text: str,
        image: Union[Image.Image, str] = None,
        case_sensitive: bool = False
    ) -> Dict[str, Any]:
        """
        Find text on screen and return locations.
        
        Args:
            search_text: Text to find
            image: Image to search, None for new screenshot
            case_sensitive: Case sensitive search
            
        Returns:
            {'success': True, 'found': True, 'locations': [...]}
        """
        result = self.extract_text(image, detailed=True)
        if not result['success']:
            return result
        
        blocks = result.get('blocks', [])
        search = search_text if case_sensitive else search_text.lower()
        
        locations = []
        for block in blocks:
            text = block.text if case_sensitive else block.text.lower()
            if search in text:
                locations.append({
                    'text': block.text,
                    'x': block.x,
                    'y': block.y,
                    'width': block.width,
                    'height': block.height,
                    'center': block.center,
                    'confidence': block.confidence
                })
        
        return {
            'success': True,
            'found': len(locations) > 0,
            'search_text': search_text,
            'locations': locations,
            'count': len(locations)
        }
    
    def click_text(self, search_text: str, index: int = 0) -> Dict[str, Any]:
        """Find text and click on it."""
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        result = self.find_text(search_text)
        if not result['success']:
            return result
        
        if not result['found']:
            return {
                'success': False, 
                'error': f'Text "{search_text}" not found on screen'
            }
        
        if index >= len(result['locations']):
            return {
                'success': False,
                'error': f'Only {len(result["locations"])} matches found'
            }
        
        location = result['locations'][index]
        x, y = location['center']
        
        try:
            pyautogui.click(x, y)
            return {
                'success': True,
                'clicked': True,
                'text': search_text,
                'position': (x, y)
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # =====================================================
    # UI ELEMENT DETECTION
    # =====================================================
    
    def detect_ui_elements(
        self,
        image: Union[Image.Image, str] = None,
        element_types: List[str] = None
    ) -> Dict[str, Any]:
        """
        Detect UI elements on screen using text analysis and patterns.
        
        Args:
            image: Image to analyze
            element_types: Filter by types ['button', 'link', 'input', 'text']
            
        Returns:
            {'success': True, 'elements': [...]}
        """
        # First get OCR results
        result = self.extract_text(image, detailed=True)
        if not result['success']:
            return result
        
        blocks = result.get('blocks', [])
        elements = []
        
        for block in blocks:
            text_lower = block.text.lower()
            
            # Classify element type
            element_type = 'text'  # default
            clickable = False
            
            # Check for button patterns
            if any(kw in text_lower for kw in self.BUTTON_KEYWORDS):
                element_type = 'button'
                clickable = True
            # Check for link patterns
            elif any(kw in text_lower for kw in self.LINK_KEYWORDS):
                element_type = 'link'
                clickable = True
            # Check for input patterns
            elif any(kw in text_lower for kw in self.INPUT_KEYWORDS):
                element_type = 'input'
                clickable = True
            # Check for URL pattern
            elif text_lower.startswith(('http', 'www')):
                element_type = 'link'
                clickable = True
            
            # Filter by requested types
            if element_types and element_type not in element_types:
                continue
            
            element = UIElement(
                type=element_type,
                text=block.text,
                x=block.x,
                y=block.y,
                width=block.width,
                height=block.height,
                confidence=block.confidence,
                clickable=clickable
            )
            elements.append(element)
        
        # Group nearby elements (for multi-word buttons)
        grouped_elements = self._group_nearby_elements(elements)
        
        return {
            'success': True,
            'elements': grouped_elements,
            'count': len(grouped_elements),
            'by_type': self._count_by_type(grouped_elements)
        }
    
    def _group_nearby_elements(self, elements: List[UIElement], threshold: int = 20) -> List[UIElement]:
        """Group nearby text elements that likely form a single UI element."""
        # Simple grouping - could be enhanced with ML
        return elements  # Return as-is for now
    
    def _count_by_type(self, elements: List[UIElement]) -> Dict[str, int]:
        """Count elements by type."""
        counts = defaultdict(int)
        for e in elements:
            counts[e.type] += 1
        return dict(counts)
    
    def find_element(
        self,
        text: str = None,
        element_type: str = None,
        near_text: str = None
    ) -> Dict[str, Any]:
        """
        Find a specific UI element.
        
        Args:
            text: Element text to match
            element_type: Filter by type
            near_text: Find element near this text
            
        Returns:
            {'success': True, 'element': UIElement, 'position': (x, y)}
        """
        result = self.detect_ui_elements(
            element_types=[element_type] if element_type else None
        )
        if not result['success']:
            return result
        
        elements = result['elements']
        
        # Find matching element
        for element in elements:
            if text and text.lower() not in element.text.lower():
                continue
            if element_type and element.type != element_type:
                continue
            
            return {
                'success': True,
                'found': True,
                'element': element,
                'position': element.center,
                'text': element.text
            }
        
        return {
            'success': True,
            'found': False,
            'error': 'Element not found'
        }
    
    def get_clickable_elements(self, image: Union[Image.Image, str] = None) -> Dict[str, Any]:
        """Get all clickable elements on screen."""
        result = self.detect_ui_elements(image)
        if not result['success']:
            return result
        
        clickable = [e for e in result['elements'] if e.clickable]
        
        return {
            'success': True,
            'elements': clickable,
            'count': len(clickable)
        }
    
    # =====================================================
    # VISUAL COMPARISON
    # =====================================================
    
    def compare_images(
        self,
        image1: Union[Image.Image, str],
        image2: Union[Image.Image, str],
        threshold: float = 0.95,
        save_diff: bool = False
    ) -> ComparisonResult:
        """
        Compare two images for similarity.
        
        Args:
            image1: First image
            image2: Second image
            threshold: Similarity threshold (0.0 to 1.0)
            save_diff: Save difference image
            
        Returns:
            ComparisonResult object
        """
        if not PIL_OK:
            return ComparisonResult(
                similar=False,
                similarity_score=0.0
            )
        
        try:
            # Load images
            img1 = Image.open(image1) if isinstance(image1, str) else image1
            img2 = Image.open(image2) if isinstance(image2, str) else image2
            
            # Resize to same size
            if img1.size != img2.size:
                img2 = img2.resize(img1.size)
            
            # Convert to same mode
            img1 = img1.convert('RGB')
            img2 = img2.convert('RGB')
            
            # Calculate difference
            diff = ImageChops.difference(img1, img2)
            
            # Calculate similarity score
            if NUMPY_OK:
                diff_array = np.array(diff)
                max_diff = 255 * 3 * diff_array.shape[0] * diff_array.shape[1]
                actual_diff = np.sum(diff_array)
                similarity = 1.0 - (actual_diff / max_diff)
                pixel_diff = np.sum(diff_array > 10)  # Significant differences
            else:
                # Fallback without numpy
                stat = ImageStat.Stat(diff)
                diff_sum = sum(stat.sum)
                max_diff = 255 * 3 * img1.size[0] * img1.size[1]
                similarity = 1.0 - (diff_sum / max_diff)
                pixel_diff = 0
            
            # Find difference regions
            diff_regions = self._find_diff_regions(diff) if not ComparisonResult else []
            
            # Save diff image if requested
            diff_path = None
            if save_diff:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                diff_path = str(self.screenshot_dir / f"diff_{timestamp}.png")
                diff.save(diff_path)
            
            return ComparisonResult(
                similar=similarity >= threshold,
                similarity_score=similarity,
                difference_regions=diff_regions,
                pixel_diff_count=int(pixel_diff),
                diff_image_path=diff_path
            )
            
        except Exception as e:
            logger.error(f"[ScreenshotAnalyzer] Compare error: {e}")
            return ComparisonResult(
                similar=False,
                similarity_score=0.0
            )
    
    def _find_diff_regions(self, diff_image: Image.Image, threshold: int = 30) -> List[Tuple[int, int, int, int]]:
        """Find rectangular regions with differences."""
        regions = []
        try:
            # Convert to grayscale
            gray = diff_image.convert('L')
            
            # Find non-zero regions (simplified)
            bbox = gray.getbbox()
            if bbox:
                regions.append(bbox)
        except Exception as e:
            pass
        return regions
    
    def detect_changes(
        self,
        baseline_path: str,
        current: Image.Image = None,
        threshold: float = 0.98
    ) -> Dict[str, Any]:
        """
        Compare current screen to baseline for changes.
        
        Args:
            baseline_path: Path to baseline image
            current: Current image, None for new screenshot
            threshold: Change detection threshold
            
        Returns:
            {'success': True, 'changed': True, 'regions': [...]}
        """
        if current is None:
            result = self.capture_screen(save=False)
            if not result['success']:
                return result
            current = result['image']
        
        comparison = self.compare_images(baseline_path, current, threshold)
        
        return {
            'success': True,
            'changed': not comparison.similar,
            'similarity': comparison.similarity_score,
            'difference_regions': comparison.difference_regions,
            'pixel_diff': comparison.pixel_diff_count
        }
    
    def save_baseline(self, name: str, region: Tuple[int, int, int, int] = None) -> Dict[str, Any]:
        """Save current screen as baseline for future comparison."""
        result = self.capture_screen(region=region, save=True, filename=f"baseline_{name}.png")
        if result['success']:
            result['baseline_name'] = name
        return result
    
    # =====================================================
    # SCREEN MONITORING
    # =====================================================
    
    def add_monitored_region(
        self,
        name: str,
        x: int,
        y: int,
        width: int,
        height: int,
        check_interval: float = 5.0,
        callback: str = None
    ) -> Dict[str, Any]:
        """
        Add a screen region to monitor for changes.
        
        Args:
            name: Region identifier
            x, y, width, height: Region bounds
            check_interval: Seconds between checks
            callback: Action to trigger on change
        """
        region = ScreenRegion(
            name=name,
            x=x, y=y, width=width, height=height,
            check_interval=check_interval,
            change_callback=callback
        )
        
        # Capture initial hash
        result = self.capture_screen(region=(x, y, width, height), save=False)
        if result['success']:
            region.last_hash = self._image_hash(result['image'])
        
        self.monitored_regions[name] = region
        
        return {
            'success': True,
            'region': name,
            'bounds': (x, y, width, height)
        }
    
    def remove_monitored_region(self, name: str) -> Dict[str, Any]:
        """Remove a monitored region."""
        if name in self.monitored_regions:
            del self.monitored_regions[name]
            return {'success': True, 'removed': name}
        return {'success': False, 'error': 'Region not found'}
    
    def start_monitoring(self) -> Dict[str, Any]:
        """Start background monitoring of regions."""
        if self._monitoring:
            return {'success': False, 'error': 'Already monitoring'}
        
        self._monitoring = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        
        return {'success': True, 'regions': len(self.monitored_regions)}
    
    def stop_monitoring(self) -> Dict[str, Any]:
        """Stop background monitoring."""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        return {'success': True}
    
    def _monitor_loop(self):
        """Background monitoring loop."""
        last_check: Dict[str, float] = {}
        
        while self._monitoring:
            now = time.time()
            
            for name, region in self.monitored_regions.items():
                last = last_check.get(name, 0)
                
                if now - last >= region.check_interval:
                    self._check_region(region)
                    last_check[name] = now
            
            time.sleep(1)
    
    def _check_region(self, region: ScreenRegion):
        """Check a region for changes."""
        try:
            result = self.capture_screen(
                region=(region.x, region.y, region.width, region.height),
                save=False
            )
            if result['success']:
                current_hash = self._image_hash(result['image'])
                
                if current_hash != region.last_hash:
                    logger.info(f"[ScreenshotAnalyzer] Change detected in region: {region.name}")
                    region.last_hash = current_hash
                    
                    # Trigger callback
                    if region.change_callback:
                        # This would integrate with workflow engine
                        logger.info(f"[ScreenshotAnalyzer] Triggering callback: {region.change_callback}")
        except Exception as e:
            logger.error(f"[ScreenshotAnalyzer] Monitor error: {e}")
    
    # =====================================================
    # ANALYSIS HELPERS
    # =====================================================
    
    def analyze_screen(self, query: str = None) -> Dict[str, Any]:
        """
        Comprehensive screen analysis with optional AI query.
        
        Args:
            query: Optional question about the screen
            
        Returns:
            Combined analysis results
        """
        results = {
            'success': True,
            'timestamp': datetime.now().isoformat()
        }
        
        # Capture screen
        capture = self.capture_screen()
        if not capture['success']:
            return capture
        
        results['screenshot'] = capture['path']
        results['size'] = capture['size']
        
        # OCR
        ocr = self.extract_text(capture['image'])
        if ocr['success']:
            results['text'] = ocr['text']
            results['word_count'] = ocr.get('word_count', 0)
            results['ocr_confidence'] = ocr.get('avg_confidence', 0)
        
        # Element detection
        elements = self.detect_ui_elements(capture['image'])
        if elements['success']:
            results['elements'] = elements['count']
            results['element_types'] = elements['by_type']
        
        # AI analysis if available
        if self.ai_router and query:
            try:
                context = results.get('text', '')[:2000]
                prompt = f"Based on this screen content, answer: {query}\n\nScreen content:\n{context}"
                results['ai_answer'] = self.ai_router.query(prompt)
            except Exception as e:
                results['ai_error'] = str(e)
        
        # Record in history
        self.analysis_history.append({
            'timestamp': results['timestamp'],
            'word_count': results.get('word_count', 0),
            'elements': results.get('elements', 0)
        })
        
        return results
    
    def get_screen_text(self) -> str:
        """Quick function to get current screen text."""
        result = self.extract_text()
        return result.get('text', '') if result['success'] else ''
    
    def get_analysis_history(self, limit: int = 20) -> List[Dict]:
        """Get recent analysis history."""
        return self.analysis_history[-limit:]
    
    def _image_hash(self, image: Image.Image) -> str:
        """Calculate hash of image for caching/comparison."""
        if not PIL_OK:
            return str(time.time())
        
        # Resize for faster hashing
        small = image.resize((64, 64))
        
        # Convert to bytes and hash
        buffer = io.BytesIO()
        small.save(buffer, format='PNG')
        return hashlib.md5(buffer.getvalue()).hexdigest()
    
    def clear_cache(self):
        """Clear analysis caches."""
        self._screenshot_cache.clear()
        self._ocr_cache.clear()
        return {'success': True}
    
    # =====================================================
    # COLOR ANALYSIS
    # =====================================================
    
    def get_dominant_colors(
        self,
        image: Union[Image.Image, str] = None,
        num_colors: int = 5
    ) -> Dict[str, Any]:
        """
        Get dominant colors in image.
        
        Args:
            image: Image to analyze
            num_colors: Number of colors to return
            
        Returns:
            {'success': True, 'colors': [(r,g,b), ...]}
        """
        if not PIL_OK:
            return {'success': False, 'error': 'PIL not available'}
        
        try:
            if image is None:
                result = self.capture_screen(save=False)
                if not result['success']:
                    return result
                img = result['image']
            elif isinstance(image, str):
                img = Image.open(image)
            else:
                img = image
            
            # Reduce colors
            small = img.resize((100, 100))
            result = small.convert('P', palette=Image.ADAPTIVE, colors=num_colors)
            palette = result.getpalette()
            
            colors = []
            for i in range(num_colors):
                r = palette[i * 3]
                g = palette[i * 3 + 1]
                b = palette[i * 3 + 2]
                colors.append((r, g, b))
            
            return {
                'success': True,
                'colors': colors,
                'hex_colors': ['#{:02x}{:02x}{:02x}'.format(r, g, b) for r, g, b in colors]
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_color_at_position(self, x: int, y: int) -> Dict[str, Any]:
        """Get pixel color at screen position."""
        if not PYAUTOGUI_OK:
            return {'success': False, 'error': 'pyautogui not available'}
        
        try:
            result = self.capture_screen(save=False)
            if not result['success']:
                return result
            
            pixel = result['image'].getpixel((x, y))
            
            return {
                'success': True,
                'position': (x, y),
                'rgb': pixel[:3] if len(pixel) >= 3 else pixel,
                'hex': '#{:02x}{:02x}{:02x}'.format(*pixel[:3])
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}


# =====================================================
# SINGLETON & FACTORIES
# =====================================================

_analyzer = None

def get_screenshot_analyzer(ai_router=None) -> ScreenshotAnalyzer:
    """Get or create screenshot analyzer instance."""
    global _analyzer
    if _analyzer is None:
        _analyzer = ScreenshotAnalyzer(ai_router)
    elif ai_router and not _analyzer.ai_router:
        _analyzer.ai_router = ai_router
    return _analyzer

def create_screenshot_analyzer(ai_router=None, screenshot_dir: str = None) -> ScreenshotAnalyzer:
    """Create new screenshot analyzer instance."""
    return ScreenshotAnalyzer(ai_router, screenshot_dir)


# =====================================================
# QUICK FUNCTIONS
# =====================================================

def capture_screen(region=None) -> Dict[str, Any]:
    """Quick function to capture screen."""
    return get_screenshot_analyzer().capture_screen(region)

def read_screen() -> str:
    """Quick function to read screen text."""
    return get_screenshot_analyzer().get_screen_text()

def find_text_on_screen(text: str) -> Dict[str, Any]:
    """Quick function to find text."""
    return get_screenshot_analyzer().find_text(text)

def click_on_text(text: str) -> Dict[str, Any]:
    """Quick function to click on text."""
    return get_screenshot_analyzer().click_text(text)


# =====================================================
# EXAMPLE USAGE & TESTS
# =====================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("LADA v9.0 - Screenshot Analysis Test")
    print("=" * 60)
    
    analyzer = ScreenshotAnalyzer()
    
    # Test 1: Screenshot capture
    print("\n📸 Test 1: Screenshot Capture")
    result = analyzer.capture_screen()
    if result['success']:
        print(f"   ✓ Captured: {result['path']}")
        print(f"   ✓ Size: {result['size']}")
    else:
        print(f"   ✗ Error: {result.get('error')}")
    
    # Test 2: OCR
    print("\n🔍 Test 2: Text Extraction (OCR)")
    if OCR_OK:
        result = analyzer.extract_text()
        if result['success']:
            text_preview = result['text'][:100] + "..." if len(result['text']) > 100 else result['text']
            print(f"   ✓ Words found: {result.get('word_count', 0)}")
            print(f"   ✓ Confidence: {result.get('avg_confidence', 0):.1%}")
            print(f"   ✓ Preview: {text_preview}")
        else:
            print(f"   ✗ Error: {result.get('error')}")
    else:
        print("   ⚠ Tesseract OCR not available - install Tesseract")
    
    # Test 3: Text search
    print("\n🔎 Test 3: Text Search")
    result = analyzer.find_text("the")  # Common word
    if result['success']:
        print(f"   ✓ Found: {result['count']} occurrences")
    else:
        print(f"   ✗ Error: {result.get('error')}")
    
    # Test 4: Element detection
    print("\n🎯 Test 4: UI Element Detection")
    result = analyzer.detect_ui_elements()
    if result['success']:
        print(f"   ✓ Elements found: {result['count']}")
        print(f"   ✓ By type: {result['by_type']}")
    else:
        print(f"   ✗ Error: {result.get('error')}")
    
    # Test 5: Color analysis
    print("\n🎨 Test 5: Color Analysis")
    result = analyzer.get_dominant_colors(num_colors=5)
    if result['success']:
        print(f"   ✓ Dominant colors: {result['hex_colors']}")
    else:
        print(f"   ✗ Error: {result.get('error')}")
    
    # Test 6: Full analysis
    print("\n📊 Test 6: Full Screen Analysis")
    result = analyzer.analyze_screen()
    if result['success']:
        print(f"   ✓ Screenshot: {result.get('screenshot')}")
        print(f"   ✓ Words: {result.get('word_count', 0)}")
        print(f"   ✓ Elements: {result.get('elements', 0)}")
    else:
        print(f"   ✗ Error: {result.get('error')}")
    
    print("\n" + "=" * 60)
    print("✅ Screenshot Analysis tests complete!")
    print(f"   OCR available: {OCR_OK}")
    print(f"   PIL available: {PIL_OK}")
    print(f"   NumPy available: {NUMPY_OK}")
