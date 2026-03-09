"""
LADA - Visual Grounding
AI-powered screen understanding using multimodal models (Gemini Vision).
Sends screenshots to vision AI for element identification and coordinate extraction.

Features:
- Screenshot-based UI element identification
- Natural language element finding with bounding boxes
- Screen description for autonomous agent context
- Fallback to OCR when vision API unavailable
"""

import os
import logging
import json
import re
import base64
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Try Gemini Vision
try:
    import google.genai as genai
    GEMINI_VISION_OK = True
except ImportError:
    GEMINI_VISION_OK = False

# Fallback OCR
try:
    from modules.screenshot_analysis import ScreenshotAnalyzer
    OCR_OK = True
except ImportError:
    OCR_OK = False


@dataclass
class UIElement:
    """A detected UI element with location"""
    label: str
    element_type: str  # button, input, link, text, icon, menu, etc.
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    confidence: float = 0.0
    text: str = ""

    @property
    def center(self) -> Tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)


@dataclass
class ScreenDescription:
    """Structured description of what's on screen"""
    summary: str = ""
    elements: List[UIElement] = field(default_factory=list)
    active_app: str = ""
    visible_text: str = ""
    layout: str = ""  # e.g., "navigation bar at top, content area, sidebar on right"


class VisualGrounder:
    """
    AI-powered visual grounding for screen understanding.

    Uses Gemini Vision or similar multimodal models to analyze screenshots
    and identify UI elements, their positions, and their functions.
    """

    def __init__(self):
        self.gemini_client = None
        self.model_name = 'gemini-2.0-flash'
        self.ocr_fallback = None

        # Initialize Gemini Vision
        api_key = os.getenv('GEMINI_API_KEY', '')
        if GEMINI_VISION_OK and api_key:
            try:
                self.gemini_client = genai.Client(api_key=api_key)
                logger.info("[VisualGrounding] Gemini Vision initialized")
            except Exception as e:
                logger.warning(f"[VisualGrounding] Gemini init failed: {e}")

        # OCR fallback
        if OCR_OK:
            try:
                self.ocr_fallback = ScreenshotAnalyzer()
            except Exception:
                pass

    def _load_image_as_base64(self, image_path: str) -> Optional[str]:
        """Load an image file and encode as base64."""
        try:
            with open(image_path, 'rb') as f:
                return base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"[VisualGrounding] Failed to load image: {e}")
            return None

    def _query_vision(self, image_path: str, prompt: str) -> Optional[str]:
        """Send image + prompt to Gemini Vision API."""
        if not self.gemini_client:
            return None

        try:
            # Upload the image file
            with open(image_path, 'rb') as f:
                image_data = f.read()

            from google.genai import types
            image_part = types.Part.from_bytes(data=image_data, mime_type='image/png')

            response = self.gemini_client.models.generate_content(
                model=self.model_name,
                contents=[prompt, image_part],
            )

            if response and response.text:
                return response.text.strip()
        except Exception as e:
            logger.error(f"[VisualGrounding] Vision query failed: {e}")

        return None

    def describe_screen(self, screenshot_path: str) -> ScreenDescription:
        """
        Get a structured description of what's visible on screen.
        """
        desc = ScreenDescription()

        # Try vision AI first
        result = self._query_vision(screenshot_path, (
            "Describe this screenshot of a computer screen. Include:\n"
            "1. What application/website is open\n"
            "2. Main content visible\n"
            "3. Notable UI elements (buttons, menus, inputs)\n"
            "4. Overall layout structure\n"
            "Be concise and factual."
        ))

        if result:
            desc.summary = result
            return desc

        # Fallback to OCR
        if self.ocr_fallback:
            try:
                analysis = self.ocr_fallback.analyze_screenshot(screenshot_path)
                if analysis:
                    desc.visible_text = analysis.get('text', '')
                    desc.summary = f"Screen text: {desc.visible_text[:300]}"
            except Exception:
                pass

        return desc

    def find_element(self, screenshot_path: str, element_description: str) -> Optional[UIElement]:
        """
        Find a specific UI element by description and return its location.

        Args:
            screenshot_path: Path to screenshot
            element_description: Natural language description of element to find

        Returns:
            UIElement with approximate coordinates, or None
        """
        result = self._query_vision(screenshot_path, (
            f"Find this UI element in the screenshot: '{element_description}'\n\n"
            f"Return a JSON object with:\n"
            f'- "found": true/false\n'
            f'- "label": element text/description\n'
            f'- "type": button/input/link/text/icon/menu\n'
            f'- "x": approximate x coordinate (pixels from left)\n'
            f'- "y": approximate y coordinate (pixels from top)\n'
            f'- "width": approximate width\n'
            f'- "height": approximate height\n'
            f'- "confidence": 0.0-1.0\n\n'
            f"Return ONLY valid JSON."
        ))

        if not result:
            return None

        try:
            json_match = re.search(r'\{[^}]+\}', result, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                if data.get('found', False):
                    return UIElement(
                        label=data.get('label', element_description),
                        element_type=data.get('type', 'unknown'),
                        x=int(data.get('x', 0)),
                        y=int(data.get('y', 0)),
                        width=int(data.get('width', 50)),
                        height=int(data.get('height', 30)),
                        confidence=float(data.get('confidence', 0.5)),
                    )
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug(f"[VisualGrounding] Parse error: {e}")

        return None

    def identify_elements(self, screenshot_path: str, task_description: str = "") -> List[UIElement]:
        """
        Identify all interactive UI elements in a screenshot.

        Args:
            screenshot_path: Path to screenshot
            task_description: Optional task context for relevance filtering

        Returns:
            List of UIElement objects with locations
        """
        task_ctx = f"\nTask context: {task_description}" if task_description else ""
        result = self._query_vision(screenshot_path, (
            f"Identify all interactive UI elements (buttons, links, inputs, menus) "
            f"in this screenshot.{task_ctx}\n\n"
            f"Return a JSON array of objects, each with:\n"
            f'- "label": element text\n'
            f'- "type": button/input/link/dropdown/checkbox/tab\n'
            f'- "x": x coordinate\n'
            f'- "y": y coordinate\n'
            f'- "width": width\n'
            f'- "height": height\n\n'
            f"Return ONLY valid JSON array. Limit to 15 most important elements."
        ))

        if not result:
            return []

        elements = []
        try:
            json_match = re.search(r'\[.*\]', result, re.DOTALL)
            if json_match:
                items = json.loads(json_match.group())
                for item in items[:15]:
                    elements.append(UIElement(
                        label=item.get('label', ''),
                        element_type=item.get('type', 'unknown'),
                        x=int(item.get('x', 0)),
                        y=int(item.get('y', 0)),
                        width=int(item.get('width', 50)),
                        height=int(item.get('height', 30)),
                    ))
        except (json.JSONDecodeError, ValueError):
            pass

        return elements

    def get_click_target(self, screenshot_path: str, description: str) -> Optional[Tuple[int, int]]:
        """
        Convenience method: find element and return click coordinates.

        Returns:
            (x, y) center coordinates or None
        """
        element = self.find_element(screenshot_path, description)
        if element:
            return element.center
        return None

    # =========================================================
    # SET-OF-MARK (SoM) VISUAL GROUNDING - SeeAct Style
    # =========================================================

    def _annotate_screenshot_with_markers(
        self, image_path: str, output_path: Optional[str] = None
    ) -> Tuple[Optional[str], Dict[int, Dict[str, int]]]:
        """
        Annotate a screenshot with numbered markers on detected interactive regions.

        Uses edge detection and contour finding to identify UI elements,
        then draws numbered boxes around each one.

        Args:
            image_path: Path to original screenshot
            output_path: Optional path for annotated image (auto-generated if None)

        Returns:
            Tuple of (annotated_image_path, marker_map)
            marker_map: {marker_number: {"x": int, "y": int, "width": int, "height": int}}
        """
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageFilter
        except ImportError:
            logger.warning("[VisualGrounding] Pillow not available for SoM")
            return None, {}

        try:
            img = Image.open(image_path)
            width, height = img.size

            # Convert to grayscale for edge detection
            gray = img.convert('L')

            # Apply edge detection using Pillow's built-in filters
            edges = gray.filter(ImageFilter.FIND_EDGES)

            # Find candidate regions using a grid-based approach
            # This is a simplified approach - production would use OpenCV contours
            marker_map: Dict[int, Dict[str, int]] = {}
            draw = ImageDraw.Draw(img)

            # Try to load a font, fall back to default
            try:
                font = ImageFont.truetype("arial.ttf", 14)
            except:
                font = ImageFont.load_default()

            # Detect potential interactive regions by scanning for edge clusters
            marker_num = 1
            cell_width = max(100, width // 20)
            cell_height = max(50, height // 20)
            min_edge_density = 0.05  # Minimum edge density to consider a region

            # Scan grid cells for high edge density (indicates UI elements)
            for row in range(0, height - cell_height, cell_height // 2):
                for col in range(0, width - cell_width, cell_width // 2):
                    # Check edge density in this cell
                    edge_crop = edges.crop((col, row, col + cell_width, row + cell_height))
                    pixels = list(edge_crop.getdata())
                    edge_count = sum(1 for p in pixels if p > 100)
                    density = edge_count / len(pixels) if pixels else 0

                    if density > min_edge_density:
                        # Check if overlapping with existing marker
                        overlaps = False
                        for existing in marker_map.values():
                            if (abs(col - existing['x']) < cell_width // 2 and
                                abs(row - existing['y']) < cell_height // 2):
                                overlaps = True
                                break

                        if not overlaps and marker_num <= 50:  # Max 50 markers
                            # Draw marker box
                            box_color = (255, 0, 0)  # Red
                            bg_color = (255, 255, 0)  # Yellow background for number

                            # Draw rectangle around element
                            draw.rectangle(
                                [col, row, col + cell_width, row + cell_height],
                                outline=box_color, width=2
                            )

                            # Draw marker number with background
                            text = str(marker_num)
                            text_bbox = draw.textbbox((col + 2, row + 2), text, font=font)
                            draw.rectangle(text_bbox, fill=bg_color)
                            draw.text((col + 2, row + 2), text, fill=(0, 0, 0), font=font)

                            # Store marker info
                            marker_map[marker_num] = {
                                'x': col,
                                'y': row,
                                'width': cell_width,
                                'height': cell_height,
                                'center_x': col + cell_width // 2,
                                'center_y': row + cell_height // 2,
                            }
                            marker_num += 1

            # Save annotated image
            if output_path is None:
                output_path = str(Path(image_path).with_suffix('.marked.png'))

            img.save(output_path)
            logger.info(f"[VisualGrounding] SoM: Annotated {marker_num - 1} markers")

            return output_path, marker_map

        except Exception as e:
            logger.error(f"[VisualGrounding] SoM annotation failed: {e}")
            return None, {}

    def find_element_som(
        self, screenshot_path: str, element_description: str
    ) -> Optional[UIElement]:
        """
        Find a UI element using Set-of-Mark (SoM) prompting.

        This is more accurate than direct coordinate estimation because:
        1. We detect candidate regions and number them
        2. Vision model only needs to identify which NUMBER corresponds to the element
        3. We use the pre-computed coordinates of that numbered region

        Args:
            screenshot_path: Path to screenshot
            element_description: Natural language description of element to find

        Returns:
            UIElement with precise coordinates, or None
        """
        # Step 1: Annotate screenshot with markers
        annotated_path, marker_map = self._annotate_screenshot_with_markers(screenshot_path)

        if not annotated_path or not marker_map:
            # Fall back to standard method
            logger.debug("[VisualGrounding] SoM failed, using standard find_element")
            return self.find_element(screenshot_path, element_description)

        # Step 2: Ask vision model which marker corresponds to the target
        marker_list = ', '.join(str(n) for n in sorted(marker_map.keys()))
        result = self._query_vision(annotated_path, (
            f"This screenshot has numbered red boxes marking different UI elements.\n"
            f"Available markers: {marker_list}\n\n"
            f"Find the marker number that best matches: '{element_description}'\n\n"
            f"Return JSON: {{\"marker\": <number>, \"confidence\": 0.0-1.0, \"reason\": \"why this marker\"}}\n"
            f"If no marker matches, return {{\"marker\": null, \"confidence\": 0.0}}\n"
            f"Return ONLY valid JSON."
        ))

        if not result:
            return None

        # Step 3: Parse response and return element with marker coordinates
        try:
            json_match = re.search(r'\{[^}]+\}', result, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                marker_num = data.get('marker')
                confidence = float(data.get('confidence', 0.0))

                if marker_num is not None and marker_num in marker_map:
                    m = marker_map[marker_num]
                    return UIElement(
                        label=element_description,
                        element_type='detected',
                        x=m['x'],
                        y=m['y'],
                        width=m['width'],
                        height=m['height'],
                        confidence=confidence,
                    )
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.debug(f"[VisualGrounding] SoM parse error: {e}")

        return None

    def identify_elements_som(
        self, screenshot_path: str, task_description: str = ""
    ) -> List[UIElement]:
        """
        Identify all interactive UI elements using Set-of-Mark prompting.

        Args:
            screenshot_path: Path to screenshot
            task_description: Optional task context

        Returns:
            List of UIElement objects with precise locations
        """
        # Step 1: Annotate screenshot with markers
        annotated_path, marker_map = self._annotate_screenshot_with_markers(screenshot_path)

        if not annotated_path or not marker_map:
            return self.identify_elements(screenshot_path, task_description)

        # Step 2: Ask vision model to describe each marker
        task_ctx = f"\nTask context: {task_description}" if task_description else ""
        marker_list = ', '.join(str(n) for n in sorted(marker_map.keys()))

        result = self._query_vision(annotated_path, (
            f"This screenshot has numbered red boxes marking UI elements.\n"
            f"Markers: {marker_list}{task_ctx}\n\n"
            f"For each marker that contains an interactive element (button, link, input, etc.), "
            f"describe what it is.\n\n"
            f"Return JSON array: [{{\"marker\": <number>, \"label\": \"text\", \"type\": \"button/link/input/etc\"}}]\n"
            f"Only include markers with actual interactive elements. Return ONLY valid JSON."
        ))

        if not result:
            return []

        elements = []
        try:
            json_match = re.search(r'\[.*\]', result, re.DOTALL)
            if json_match:
                items = json.loads(json_match.group())
                for item in items:
                    marker_num = item.get('marker')
                    if marker_num in marker_map:
                        m = marker_map[marker_num]
                        elements.append(UIElement(
                            label=item.get('label', f'Marker {marker_num}'),
                            element_type=item.get('type', 'unknown'),
                            x=m['x'],
                            y=m['y'],
                            width=m['width'],
                            height=m['height'],
                            confidence=0.8,  # SoM generally more confident
                        ))
        except (json.JSONDecodeError, ValueError):
            pass

        return elements

    def get_click_target_som(
        self, screenshot_path: str, description: str
    ) -> Optional[Tuple[int, int]]:
        """
        Get click coordinates using SoM-enhanced element finding.

        Returns:
            (x, y) center coordinates or None
        """
        element = self.find_element_som(screenshot_path, description)
        if element:
            return element.center
        return None

