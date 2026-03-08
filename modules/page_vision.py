"""
LADA v7.0 - Page Vision Module
Computer vision for web page understanding using Google Gemini Vision (free tier)
"""

import os
import sys
import json
import logging
import base64
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class PageVision:
    """
    Computer vision for analyzing web pages.
    Uses Google Gemini Vision API (free tier) to understand page layouts,
    identify elements, extract data, and make recommendations.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize page vision.
        
        Args:
            api_key: Google Gemini API key (uses env var if not provided)
        """
        self.api_key = api_key or os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
        self.model = None
        self.cache: Dict[str, Dict] = {}  # Cache analyzed results
        self._init_model()
    
    def _init_model(self):
        """Initialize Gemini Vision model."""
        if not self.api_key:
            logger.warning("No Gemini API key found. Vision features will be limited.")
            return
        
        try:
            # Try new google.genai SDK first
            try:
                from google import genai
                
                client = genai.Client(api_key=self.api_key)
                self.model = client
                self.model_name = "gemini-2.0-flash-exp"
                self.sdk_version = "new"
                logger.info("✅ Gemini Vision initialized (google.genai)")
                
            except ImportError:
                # Fall back to google.generativeai
                import google.generativeai as genai
                
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel('gemini-1.5-flash')
                self.sdk_version = "old"
                logger.info("✅ Gemini Vision initialized (google.generativeai)")
                
        except Exception as e:
            logger.error(f"Failed to initialize Gemini Vision: {e}")
            self.model = None
    
    def _load_image(self, image_path: str) -> Optional[bytes]:
        """Load image from file."""
        try:
            if not os.path.exists(image_path):
                logger.error(f"Image not found: {image_path}")
                return None
            
            with open(image_path, 'rb') as f:
                return f.read()
                
        except Exception as e:
            logger.error(f"Failed to load image: {e}")
            return None
    
    def analyze_page_layout(self, screenshot_path: str) -> Dict[str, Any]:
        """
        Analyze page layout and identify interactive elements.
        
        Args:
            screenshot_path: Path to screenshot image
            
        Returns:
            {
                "page_type": "search_results" | "product_page" | "form" | "other",
                "elements": [
                    {"type": "button", "text": "Search", "location": "top-right"},
                    {"type": "input", "placeholder": "Enter city", "location": "center"}
                ],
                "primary_action": "search" | "submit" | "select",
                "data_areas": ["price_list", "product_grid", "form_fields"]
            }
        """
        # Check cache
        cache_key = f"layout_{screenshot_path}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        if not self.model:
            return self._fallback_layout_analysis(screenshot_path)
        
        try:
            image_data = self._load_image(screenshot_path)
            if not image_data:
                return {"error": "Failed to load image"}
            
            prompt = """Analyze this webpage screenshot and identify:
1. Page type (search results, product page, form, booking page, other)
2. Interactive elements (buttons, inputs, dropdowns, links)
3. Data areas (product listings, prices, search results)
4. Primary action the user should take

Return JSON:
{
    "page_type": "search_results",
    "elements": [
        {"type": "button", "text": "Search", "location": "top-right", "purpose": "submit search"},
        {"type": "input", "placeholder": "City name", "location": "center"}
    ],
    "primary_action": "search",
    "data_areas": ["flight_results", "price_list"],
    "recommendations": ["Click search to see flights", "Enter destination first"]
}

Return ONLY valid JSON."""

            result = self._query_vision(image_data, prompt)
            
            # Parse JSON response
            try:
                json_start = result.find('{')
                json_end = result.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    parsed = json.loads(result[json_start:json_end])
                    self.cache[cache_key] = parsed
                    return parsed
            except json.JSONDecodeError:
                pass
            
            return {"raw_analysis": result}
            
        except Exception as e:
            logger.error(f"Layout analysis failed: {e}")
            return {"error": str(e)}
    
    def find_clickable_elements(self, screenshot_path: str, target: str) -> List[Dict]:
        """
        Find clickable elements matching a target description.
        
        Args:
            screenshot_path: Path to screenshot
            target: What to find (e.g., "search button", "cheapest flight")
            
        Returns:
            List of matching elements with approximate locations
        """
        if not self.model:
            return []
        
        try:
            image_data = self._load_image(screenshot_path)
            if not image_data:
                return []
            
            prompt = f"""Find clickable elements in this webpage that match: "{target}"

Return JSON array:
[
    {{"text": "Search", "type": "button", "location": "top-right", "confidence": 0.9}},
    {{"text": "Go", "type": "link", "location": "center", "confidence": 0.7}}
]

Return ONLY the JSON array, no other text."""

            result = self._query_vision(image_data, prompt)
            
            try:
                json_start = result.find('[')
                json_end = result.rfind(']') + 1
                if json_start >= 0 and json_end > json_start:
                    return json.loads(result[json_start:json_end])
            except json.JSONDecodeError:
                pass
            
            return []
            
        except Exception as e:
            logger.error(f"Find elements failed: {e}")
            return []
    
    def extract_prices(self, screenshot_path: str) -> List[Dict]:
        """
        Extract all prices visible in the screenshot.
        
        Args:
            screenshot_path: Path to screenshot
            
        Returns:
            List of {"amount": float, "currency": str, "context": str}
        """
        if not self.model:
            return []
        
        try:
            image_data = self._load_image(screenshot_path)
            if not image_data:
                return []
            
            prompt = """Extract ALL prices visible in this webpage screenshot.

Return JSON array:
[
    {"amount": 3500, "currency": "INR", "context": "Flight to Bangalore"},
    {"amount": 4200, "currency": "INR", "context": "Air India flight"}
]

Include every price you can see. Return ONLY the JSON array."""

            result = self._query_vision(image_data, prompt)
            
            try:
                json_start = result.find('[')
                json_end = result.rfind(']') + 1
                if json_start >= 0 and json_end > json_start:
                    return json.loads(result[json_start:json_end])
            except json.JSONDecodeError:
                pass
            
            return []
            
        except Exception as e:
            logger.error(f"Extract prices failed: {e}")
            return []
    
    def compare_products(self, screenshot_path: str) -> Dict[str, Any]:
        """
        Compare products visible in the screenshot.
        
        Args:
            screenshot_path: Path to screenshot
            
        Returns:
            {
                "products": [...],
                "best_value": {...},
                "recommendation": "..."
            }
        """
        if not self.model:
            return {"error": "Vision model not available"}
        
        try:
            image_data = self._load_image(screenshot_path)
            if not image_data:
                return {"error": "Failed to load image"}
            
            prompt = """Analyze products/options shown in this screenshot and compare them.

Return JSON:
{
    "products": [
        {"name": "Product A", "price": 29999, "rating": 4.5, "key_features": ["feature1", "feature2"]},
        {"name": "Product B", "price": 24999, "rating": 4.2, "key_features": ["feature1"]}
    ],
    "best_value": {"name": "Product B", "reason": "Best price-to-feature ratio"},
    "recommendation": "Product B offers the best value with essential features at a lower price"
}

Return ONLY valid JSON."""

            result = self._query_vision(image_data, prompt)
            
            try:
                json_start = result.find('{')
                json_end = result.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    return json.loads(result[json_start:json_end])
            except json.JSONDecodeError:
                pass
            
            return {"raw_analysis": result}
            
        except Exception as e:
            logger.error(f"Compare products failed: {e}")
            return {"error": str(e)}
    
    def describe_page(self, screenshot_path: str) -> str:
        """
        Get natural language description of the page.
        
        Args:
            screenshot_path: Path to screenshot
            
        Returns:
            Human-readable description
        """
        if not self.model:
            return "Vision model not available. Cannot describe page."
        
        try:
            image_data = self._load_image(screenshot_path)
            if not image_data:
                return "Failed to load image."
            
            prompt = """Describe this webpage in 2-3 sentences. 
Include: What type of page it is, main content visible, and what actions are available.
Be concise and informative."""

            return self._query_vision(image_data, prompt)
            
        except Exception as e:
            logger.error(f"Describe page failed: {e}")
            return f"Error: {e}"
    
    def _query_vision(self, image_data: bytes, prompt: str) -> str:
        """Query the vision model with an image."""
        try:
            if self.sdk_version == "new":
                # New google.genai SDK
                from google.genai import types
                
                response = self.model.models.generate_content(
                    model=self.model_name,
                    contents=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_bytes(data=image_data, mime_type="image/png"),
                                types.Part.from_text(text=prompt)
                            ]
                        )
                    ]
                )
                return response.text
                
            else:
                # Old google.generativeai SDK
                import PIL.Image
                import io
                
                image = PIL.Image.open(io.BytesIO(image_data))
                response = self.model.generate_content([prompt, image])
                return response.text
                
        except Exception as e:
            logger.error(f"Vision query failed: {e}")
            raise
    
    def _fallback_layout_analysis(self, screenshot_path: str) -> Dict[str, Any]:
        """Fallback analysis when vision model is not available."""
        return {
            "page_type": "unknown",
            "elements": [],
            "primary_action": "unknown",
            "data_areas": [],
            "note": "Vision model not available. Using basic analysis.",
            "screenshot": screenshot_path
        }
    
    def clear_cache(self):
        """Clear the analysis cache."""
        self.cache = {}


# ============================================================
# EXAMPLE USAGE
# ============================================================
if __name__ == "__main__":
    print("🚀 Testing PageVision...")
    
    vision = PageVision()
    
    if vision.model:
        print("✅ Vision model initialized")
        
        # Test with a sample screenshot if it exists
        test_screenshot = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'screenshots', 'test_google.png'
        )
        
        if os.path.exists(test_screenshot):
            print(f"\n📸 Analyzing: {test_screenshot}")
            
            # Test describe
            description = vision.describe_page(test_screenshot)
            print(f"\n📝 Description: {description}")
            
            # Test layout analysis
            layout = vision.analyze_page_layout(test_screenshot)
            print(f"\n📊 Layout: {json.dumps(layout, indent=2)}")
        else:
            print(f"\n⚠️ Test screenshot not found: {test_screenshot}")
            print("Run browser_automation.py first to create a test screenshot")
    else:
        print("⚠️ Vision model not initialized (no API key)")
        print("Set GEMINI_API_KEY or GOOGLE_API_KEY environment variable")
    
    print("\n✅ PageVision test complete!")
