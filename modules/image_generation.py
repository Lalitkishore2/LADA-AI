"""
LADA - Image Generation
AI image generation with multi-backend support.

Features:
- Stability AI integration
- Gemini Imagen support (when available)
- Image display in chat
- Prompt enhancement
"""

import os
import logging
import base64
import json
import requests
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class ImageGenerator:
    """
    Multi-backend image generation.
    Supports Stability AI and Gemini Imagen.
    """

    def __init__(self, output_dir: Optional[str] = None):
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path(os.path.dirname(os.path.dirname(__file__))) / 'data' / 'generated_images'

        self.output_dir.mkdir(parents=True, exist_ok=True)

        # API keys
        self.stability_key = os.getenv('STABILITY_API_KEY', '')
        self.gemini_key = os.getenv('GEMINI_API_KEY', '')

        # Gemini client
        self.gemini_client = None
        if self.gemini_key:
            try:
                import google.genai as genai
                self.gemini_client = genai.Client(api_key=self.gemini_key)
            except ImportError:
                pass

        backends = []
        if self.stability_key:
            backends.append("Stability AI")
        if self.gemini_client:
            backends.append("Gemini")
        logger.info(f"[ImageGen] Available backends: {backends or ['None']}")

    def generate(self, prompt: str, size: str = "1024x1024",
                 style: str = "natural") -> Optional[Dict[str, Any]]:
        """
        Generate an image from a text prompt.

        Returns:
            Dict with 'path', 'prompt', 'backend', 'size' or None on failure
        """
        # Try Stability AI first
        if self.stability_key:
            result = self._generate_stability(prompt, size)
            if result:
                return result

        # Try Gemini Imagen
        if self.gemini_client:
            result = self._generate_gemini(prompt, size)
            if result:
                return result

        logger.warning("[ImageGen] No backend available for image generation")
        return None

    def _generate_stability(self, prompt: str, size: str) -> Optional[Dict[str, Any]]:
        """Generate image using Stability AI API."""
        try:
            # Parse size
            w, h = size.split('x') if 'x' in size else ('1024', '1024')

            response = requests.post(
                "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image",
                headers={
                    "Authorization": f"Bearer {self.stability_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "text_prompts": [{"text": prompt, "weight": 1}],
                    "cfg_scale": 7,
                    "width": int(w),
                    "height": int(h),
                    "samples": 1,
                    "steps": 30,
                },
                timeout=60,
            )

            if response.status_code == 200:
                data = response.json()
                for i, image in enumerate(data.get("artifacts", [])):
                    image_data = base64.b64decode(image["base64"])
                    filename = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i}.png"
                    filepath = self.output_dir / filename

                    with open(filepath, 'wb') as f:
                        f.write(image_data)

                    return {
                        'path': str(filepath),
                        'prompt': prompt,
                        'backend': 'Stability AI',
                        'size': size,
                    }
            else:
                logger.warning(f"[ImageGen] Stability AI error: {response.status_code}")

        except Exception as e:
            logger.error(f"[ImageGen] Stability AI failed: {e}")

        return None

    def _generate_gemini(self, prompt: str, size: str) -> Optional[Dict[str, Any]]:
        """Generate image using Gemini Imagen API."""
        try:
            response = self.gemini_client.models.generate_content(
                model='gemini-2.0-flash-exp',
                contents=f"Generate an image: {prompt}",
            )

            # Check if response contains image parts
            if response and hasattr(response, 'candidates'):
                for candidate in response.candidates:
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                        for part in candidate.content.parts:
                            if hasattr(part, 'inline_data') and part.inline_data:
                                image_data = part.inline_data.data
                                filename = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                                filepath = self.output_dir / filename

                                with open(filepath, 'wb') as f:
                                    f.write(image_data)

                                return {
                                    'path': str(filepath),
                                    'prompt': prompt,
                                    'backend': 'Gemini Imagen',
                                    'size': size,
                                }

        except Exception as e:
            logger.error(f"[ImageGen] Gemini Imagen failed: {e}")

        return None

    def is_available(self) -> bool:
        """Check if any image generation backend is available."""
        return bool(self.stability_key or self.gemini_client)


# Singleton
_image_gen = None


def get_image_generator() -> ImageGenerator:
    global _image_gen
    if _image_gen is None:
        _image_gen = ImageGenerator()
    return _image_gen
