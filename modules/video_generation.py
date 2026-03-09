"""
LADA - Video Generation
AI video generation with multi-backend support.

Features:
- Google Veo integration (via Gemini API)
- Stability AI video generation
- Video display/download support
- Prompt enhancement for better results
"""

import os
import logging
import base64
import json
import time
import requests
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class VideoGenerator:
    """
    Multi-backend video generation.
    Supports Google Veo and Stability AI.
    """

    def __init__(self, output_dir: Optional[str] = None):
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path(os.path.dirname(os.path.dirname(__file__))) / 'data' / 'generated_videos'

        self.output_dir.mkdir(parents=True, exist_ok=True)

        # API keys
        self.stability_key = os.getenv('STABILITY_API_KEY', '')
        self.gemini_key = os.getenv('GEMINI_API_KEY', '')

        # Gemini client for Veo
        self.gemini_client = None
        if self.gemini_key:
            try:
                import google.genai as genai
                self.gemini_client = genai.Client(api_key=self.gemini_key)
            except ImportError:
                pass

        backends = []
        if self.gemini_client:
            backends.append("Google Veo")
        if self.stability_key:
            backends.append("Stability AI")
        logger.info(f"[VideoGen] Available backends: {backends or ['None']}")

    def generate(self, prompt: str, duration: int = 5,
                 aspect_ratio: str = "16:9") -> Optional[Dict[str, Any]]:
        """
        Generate a video from a text prompt.

        Args:
            prompt: Text description of the video to generate
            duration: Video duration in seconds (default 5)
            aspect_ratio: Aspect ratio (16:9, 9:16, 1:1)

        Returns:
            Dict with 'path', 'prompt', 'backend', 'duration' or None on failure
        """
        # Try Google Veo first
        if self.gemini_client:
            result = self._generate_veo(prompt, duration, aspect_ratio)
            if result:
                return result

        # Try Stability AI
        if self.stability_key:
            result = self._generate_stability(prompt, duration)
            if result:
                return result

        logger.warning("[VideoGen] No backend available for video generation")
        return None

    def _generate_veo(self, prompt: str, duration: int,
                       aspect_ratio: str) -> Optional[Dict[str, Any]]:
        """Generate video using Google Veo via Gemini API."""
        try:
            # Google Veo uses the generative-video model
            # Note: Veo 2 may have specific model names like 'veo-2.0-generate-001'
            model_name = os.getenv('VEO_MODEL', 'veo-2.0-generate-001')

            # Try to generate video
            response = self.gemini_client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={
                    'response_modalities': ['VIDEO'],
                    'video_config': {
                        'aspect_ratio': aspect_ratio,
                        'duration_seconds': duration,
                    }
                }
            )

            # Check if response contains video
            if response and hasattr(response, 'candidates'):
                for candidate in response.candidates:
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                        for part in candidate.content.parts:
                            if hasattr(part, 'inline_data') and part.inline_data:
                                video_data = part.inline_data.data
                                mime_type = getattr(part.inline_data, 'mime_type', 'video/mp4')
                                ext = 'mp4' if 'mp4' in mime_type else 'webm'

                                filename = f"vid_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
                                filepath = self.output_dir / filename

                                with open(filepath, 'wb') as f:
                                    f.write(video_data)

                                return {
                                    'path': str(filepath),
                                    'prompt': prompt,
                                    'backend': 'Google Veo',
                                    'duration': duration,
                                    'aspect_ratio': aspect_ratio,
                                }

                            # Check for video file reference
                            if hasattr(part, 'file_data') and part.file_data:
                                file_uri = part.file_data.file_uri
                                # Download the video from the URI
                                video_data = self._download_file(file_uri)
                                if video_data:
                                    filename = f"vid_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
                                    filepath = self.output_dir / filename
                                    with open(filepath, 'wb') as f:
                                        f.write(video_data)
                                    return {
                                        'path': str(filepath),
                                        'prompt': prompt,
                                        'backend': 'Google Veo',
                                        'duration': duration,
                                        'aspect_ratio': aspect_ratio,
                                    }

            logger.warning("[VideoGen] Veo returned no video content")

        except Exception as e:
            logger.error(f"[VideoGen] Google Veo failed: {e}")

        return None

    def _generate_stability(self, prompt: str, duration: int) -> Optional[Dict[str, Any]]:
        """Generate video using Stability AI video generation API."""
        try:
            # Stability AI video generation endpoint
            # Using image-to-video or text-to-video endpoint
            response = requests.post(
                "https://api.stability.ai/v2beta/video/generate",
                headers={
                    "Authorization": f"Bearer {self.stability_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "text_prompts": [{"text": prompt, "weight": 1}],
                    "cfg_scale": 7,
                    "motion_bucket_id": 127,  # Amount of motion (1-255)
                    "seed": 0,
                },
                timeout=120,
            )

            if response.status_code == 200:
                data = response.json()

                # Check for generation ID (async generation)
                generation_id = data.get('id')
                if generation_id:
                    # Poll for result
                    video_data = self._poll_stability_video(generation_id)
                    if video_data:
                        filename = f"vid_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
                        filepath = self.output_dir / filename
                        with open(filepath, 'wb') as f:
                            f.write(video_data)
                        return {
                            'path': str(filepath),
                            'prompt': prompt,
                            'backend': 'Stability AI',
                            'duration': duration,
                        }

                # Check for direct video data
                if 'video' in data:
                    video_data = base64.b64decode(data['video'])
                    filename = f"vid_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
                    filepath = self.output_dir / filename
                    with open(filepath, 'wb') as f:
                        f.write(video_data)
                    return {
                        'path': str(filepath),
                        'prompt': prompt,
                        'backend': 'Stability AI',
                        'duration': duration,
                    }
            else:
                logger.warning(f"[VideoGen] Stability AI error: {response.status_code} - {response.text}")

        except Exception as e:
            logger.error(f"[VideoGen] Stability AI failed: {e}")

        return None

    def _poll_stability_video(self, generation_id: str, max_attempts: int = 60) -> Optional[bytes]:
        """Poll Stability AI for video generation result."""
        for _ in range(max_attempts):
            try:
                response = requests.get(
                    f"https://api.stability.ai/v2beta/video/result/{generation_id}",
                    headers={
                        "Authorization": f"Bearer {self.stability_key}",
                        "Accept": "video/*",
                    },
                    timeout=30,
                )

                if response.status_code == 200:
                    return response.content
                elif response.status_code == 202:
                    # Still processing
                    time.sleep(2)
                    continue
                else:
                    logger.warning(f"[VideoGen] Poll error: {response.status_code}")
                    return None

            except Exception as e:
                logger.error(f"[VideoGen] Poll failed: {e}")
                return None

        logger.warning("[VideoGen] Video generation timed out")
        return None

    def _download_file(self, uri: str) -> Optional[bytes]:
        """Download file from Google's file storage."""
        try:
            # Use the Gemini client to download
            if self.gemini_client and hasattr(self.gemini_client, 'files'):
                file_data = self.gemini_client.files.download(uri)
                return file_data
        except Exception as e:
            logger.error(f"[VideoGen] File download failed: {e}")
        return None

    def is_available(self) -> bool:
        """Check if any video generation backend is available."""
        return bool(self.stability_key or self.gemini_client)

    def get_backends(self) -> List[str]:
        """Get list of available backends."""
        backends = []
        if self.gemini_client:
            backends.append("Google Veo")
        if self.stability_key:
            backends.append("Stability AI")
        return backends


# Singleton
_video_gen = None


def get_video_generator() -> VideoGenerator:
    global _video_gen
    if _video_gen is None:
        _video_gen = VideoGenerator()
    return _video_gen
