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
