"""
LADA - YouTube Summarizer (Comet-style)
Extracts transcripts from YouTube videos and generates AI summaries.

Features:
- Get video transcript (auto-generated or manual captions)
- AI-powered video summarization (key points, timestamps, TL;DR)
- Extract video metadata (title, channel, duration, views)
- Timestamp-based navigation suggestions
"""

import re
import logging
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

# Conditional imports
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    TRANSCRIPT_OK = True
except ImportError:
    TRANSCRIPT_OK = False

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

try:
    from bs4 import BeautifulSoup
    BS4_OK = True
except ImportError:
    BS4_OK = False


@dataclass
class VideoInfo:
    """YouTube video metadata."""
    video_id: str
    url: str
    title: str = ""
    channel: str = ""
    duration: str = ""
    views: str = ""
    description: str = ""
    error: str = ""


@dataclass
class TranscriptSegment:
    """A single transcript segment with timestamp."""
    text: str
    start: float  # seconds
    duration: float

    @property
    def timestamp(self) -> str:
        """Format start time as HH:MM:SS or MM:SS."""
        total = int(self.start)
        hours = total // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"


@dataclass
class VideoSummary:
    """AI-generated summary of a YouTube video."""
    video_id: str
    title: str = ""
    channel: str = ""
    tldr: str = ""
    key_points: List[str] = field(default_factory=list)
    timestamps: List[Dict[str, str]] = field(default_factory=list)
    detailed_summary: str = ""
    transcript_length: int = 0
    error: str = ""


class YouTubeSummarizer:
    """
    Extracts YouTube transcripts and generates AI summaries.

    Usage:
        yt = YouTubeSummarizer(ai_router=router)
        summary = yt.summarize("https://youtube.com/watch?v=xyz")
        print(summary.key_points)
        print(summary.timestamps)
    """

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'en-US,en;q=0.5',
    }

    def __init__(self, ai_router=None):
        self.ai_router = ai_router

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        """Extract video ID from various YouTube URL formats."""
        # Standard: youtube.com/watch?v=ID
        parsed = urlparse(url)
        if 'youtube.com' in parsed.hostname or 'www.youtube.com' in parsed.hostname:
            qs = parse_qs(parsed.query)
            if 'v' in qs:
                return qs['v'][0]
            # Embedded: youtube.com/embed/ID
            if '/embed/' in parsed.path:
                return parsed.path.split('/embed/')[1].split('/')[0]

        # Short: youtu.be/ID
        if 'youtu.be' in parsed.hostname:
            return parsed.path.strip('/')

        # Direct ID (11 chars)
        if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
            return url

        return None

    def get_video_info(self, url: str) -> VideoInfo:
        """Fetch video metadata by scraping the YouTube page."""
        video_id = self.extract_video_id(url)
        if not video_id:
            return VideoInfo(video_id="", url=url, error="Invalid YouTube URL")

        info = VideoInfo(video_id=video_id, url=f"https://youtube.com/watch?v={video_id}")

        if not REQUESTS_OK:
            return info

        try:
            page_url = f"https://www.youtube.com/watch?v={video_id}"
            resp = requests.get(page_url, headers=self.HEADERS, timeout=10)
            html = resp.text

            # Extract title
            title_match = re.search(r'<title>(.*?)</title>', html)
            if title_match:
                info.title = title_match.group(1).replace(' - YouTube', '').strip()

            # Extract from meta tags if BeautifulSoup available
            if BS4_OK:
                soup = BeautifulSoup(html, 'html.parser')

                og_title = soup.find('meta', property='og:title')
                if og_title:
                    info.title = og_title.get('content', info.title)

                channel_tag = soup.find('link', itemprop='name')
                if channel_tag:
                    info.channel = channel_tag.get('content', '')

                desc_tag = soup.find('meta', property='og:description')
                if desc_tag:
                    info.description = desc_tag.get('content', '')[:500]

        except Exception as e:
            logger.warning(f"[YTSummarizer] Could not fetch metadata: {e}")

        return info

    def get_transcript(self, url: str, language: str = 'en') -> List[TranscriptSegment]:
        """
        Get the transcript for a YouTube video.

        Tries the simple fetch shortcut first, then falls back to
        listing transcripts and picking the best available one.
        """
        video_id = self.extract_video_id(url)
        if not video_id:
            return []

        if not TRANSCRIPT_OK:
            logger.warning("[YTSummarizer] youtube-transcript-api not installed")
            return []

        # New API (v1.x+): instantiate, then call .fetch() or .list()
        api = YouTubeTranscriptApi()

        # Strategy 1: Quick fetch with preferred languages
        try:
            fetched = api.fetch(video_id, languages=[language, 'en'])
            raw = fetched.to_raw_data()
            return [
                TranscriptSegment(
                    text=seg['text'],
                    start=seg['start'],
                    duration=seg.get('duration', 0),
                )
                for seg in raw
            ]
        except Exception as e1:
            logger.debug(f"[YTSummarizer] Quick fetch failed: {e1}")

        # Strategy 2: List all transcripts and pick best match
        try:
            transcript_list = api.list(video_id)

            transcript = None
            try:
                transcript = transcript_list.find_manually_created_transcript([language, 'en'])
            except Exception:
                try:
                    transcript = transcript_list.find_generated_transcript([language, 'en'])
                except Exception:
                    for t in transcript_list:
                        transcript = t
                        break

            if not transcript:
                return []

            fetched = transcript.fetch()
            raw = fetched.to_raw_data()
            return [
                TranscriptSegment(
                    text=seg['text'],
                    start=seg['start'],
                    duration=seg.get('duration', 0),
                )
                for seg in raw
            ]

        except Exception as e2:
            logger.error(f"[YTSummarizer] Transcript error: {e2}")
            return []

    def summarize(self, url: str, mode: str = "key_points") -> VideoSummary:
        """
        Summarize a YouTube video.

        Args:
            url: YouTube video URL
            mode: "tldr", "key_points", "detailed", "timestamps"
        """
        video_id = self.extract_video_id(url)
        if not video_id:
            return VideoSummary(video_id="", error="Invalid YouTube URL")

        # Get metadata
        info = self.get_video_info(url)

        # Get transcript
        segments = self.get_transcript(url)
        if not segments:
            return VideoSummary(
                video_id=video_id,
                title=info.title,
                channel=info.channel,
                error="Could not get transcript. The video may not have captions.",
            )

        # Build full transcript text with timestamps
        full_text = ""
        timestamped_text = ""
        for seg in segments:
            full_text += seg.text + " "
            timestamped_text += f"[{seg.timestamp}] {seg.text}\n"

        full_text = full_text.strip()

        summary = VideoSummary(
            video_id=video_id,
            title=info.title,
            channel=info.channel,
            transcript_length=len(full_text.split()),
        )

        if not self.ai_router:
            return self._fallback_summary(summary, segments, full_text)

        return self._ai_summarize(summary, info, full_text, timestamped_text, mode)

    def _ai_summarize(self, summary: VideoSummary, info: VideoInfo,
                      full_text: str, timestamped_text: str,
                      mode: str) -> VideoSummary:
        """Generate AI-powered summary."""

        # Truncate for context window
        text_for_ai = full_text[:12000]
        ts_text_for_ai = timestamped_text[:12000]

        if mode == "tldr":
            prompt = (
                f"Summarize this YouTube video in 1-2 sentences:\n\n"
                f"Title: {info.title}\n"
                f"Channel: {info.channel}\n\n"
                f"Transcript:\n{text_for_ai}"
            )
        elif mode == "timestamps":
            prompt = (
                f"Create a chapter-style breakdown of this video with timestamps.\n"
                f"Format each section as: [TIMESTAMP] Topic/description\n\n"
                f"Title: {info.title}\n\n"
                f"Timestamped transcript:\n{ts_text_for_ai}"
            )
        elif mode == "detailed":
            prompt = (
                f"Provide a detailed summary of this YouTube video including:\n"
                f"- Main topic and thesis\n- Key arguments/points\n"
                f"- Important examples or data\n- Conclusion\n\n"
                f"Title: {info.title}\n"
                f"Channel: {info.channel}\n\n"
                f"Transcript:\n{text_for_ai}"
            )
        else:  # key_points
            prompt = (
                f"Summarize this YouTube video as 5-8 bullet points. "
                f"Include the most important takeaways:\n\n"
                f"Title: {info.title}\n"
                f"Channel: {info.channel}\n\n"
                f"Transcript:\n{text_for_ai}"
            )

        try:
            response = self.ai_router.query(prompt)
            if response:
                summary.detailed_summary = response

                # Extract key points from bullet-point responses
                points = []
                for line in response.split('\n'):
                    line = line.strip()
                    if line and (line.startswith('-') or line.startswith('*') or
                                 line.startswith('•') or re.match(r'^\d+\.', line)):
                        clean = re.sub(r'^[-*•\d.)\s]+', '', line).strip()
                        if clean:
                            points.append(clean)
                if points:
                    summary.key_points = points

                # Auto-generate TL;DR
                if mode == "tldr":
                    summary.tldr = response.strip()
                else:
                    first = response.split('.')[0].strip()
                    if first:
                        summary.tldr = first + '.'

                # Extract timestamps from response
                ts_pattern = re.compile(r'\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*[-–:]\s*(.+)')
                for line in response.split('\n'):
                    match = ts_pattern.match(line.strip())
                    if match:
                        summary.timestamps.append({
                            'time': match.group(1),
                            'topic': match.group(2).strip(),
                        })

                return summary
        except Exception as e:
            logger.error(f"[YTSummarizer] AI summary error: {e}")

        return self._fallback_summary(summary, [], response if 'response' in dir() else "")

    def _fallback_summary(self, summary: VideoSummary,
                          segments: List[TranscriptSegment],
                          full_text: str) -> VideoSummary:
        """Simple extractive summary when AI is not available."""
        sentences = re.split(r'[.!?]+', full_text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

        summary.tldr = sentences[0] + '.' if sentences else "No summary available."
        summary.key_points = sentences[:5]
        summary.detailed_summary = ' '.join(sentences[:15])

        # Generate basic timestamps (every 2 minutes)
        if segments:
            interval = max(1, len(segments) // 6)
            for i in range(0, len(segments), interval):
                seg = segments[i]
                summary.timestamps.append({
                    'time': seg.timestamp,
                    'topic': seg.text[:60],
                })

        return summary

    def get_key_moments(self, url: str) -> List[Dict[str, str]]:
        """Get key moments/chapters from a video (timestamps + topics)."""
        summary = self.summarize(url, mode="timestamps")
        return summary.timestamps


# Singleton
_summarizer = None


def get_youtube_summarizer(ai_router=None) -> YouTubeSummarizer:
    """Get or create singleton YouTube summarizer."""
    global _summarizer
    if _summarizer is None:
        _summarizer = YouTubeSummarizer(ai_router=ai_router)
    return _summarizer
