"""
LADA - Page Summarizer (Comet-style)
Extracts content from web pages and summarizes them using AI.

Features:
- Scrape page content from URL or active browser tab
- Clean HTML to readable text (remove ads, nav, boilerplate)
- AI-powered summarization (key points, TL;DR, detailed)
- Extract metadata (title, author, date, word count)
- Compare multiple pages side-by-side
"""

import os
import re
import logging
import time
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Conditional imports
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
class PageContent:
    """Extracted content from a web page."""
    url: str
    title: str = ""
    text: str = ""
    author: str = ""
    date: str = ""
    word_count: int = 0
    links: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    meta_description: str = ""
    error: str = ""

    @property
    def is_valid(self) -> bool:
        return bool(self.text) and not self.error


@dataclass
class PageSummary:
    """AI-generated summary of a page."""
    url: str
    title: str = ""
    tldr: str = ""
    key_points: List[str] = field(default_factory=list)
    detailed_summary: str = ""
    word_count_original: int = 0
    word_count_summary: int = 0


class PageSummarizer:
    """
    Scrapes web pages and generates AI summaries.

    Usage:
        summarizer = PageSummarizer(ai_router=router)
        summary = summarizer.summarize_url("https://example.com/article")
        print(summary.key_points)
    """

    # Tags to remove (ads, navigation, scripts, etc.)
    REMOVE_TAGS = [
        'script', 'style', 'nav', 'header', 'footer',
        'aside', 'iframe', 'noscript', 'svg', 'form',
    ]

    # CSS classes/IDs commonly used for ads and non-content
    REMOVE_CLASSES = [
        'ad', 'ads', 'advertisement', 'sidebar', 'nav',
        'menu', 'footer', 'header', 'cookie', 'popup',
        'social', 'share', 'comment', 'related',
    ]

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }

    def __init__(self, ai_router=None):
        self.ai_router = ai_router

    def extract_page(self, url: str) -> PageContent:
        """Scrape and extract clean text content from a URL."""
        if not REQUESTS_OK:
            return PageContent(url=url, error="requests library not installed")
        if not BS4_OK:
            return PageContent(url=url, error="beautifulsoup4 not installed")

        try:
            response = requests.get(url, headers=self.HEADERS, timeout=15)
            response.raise_for_status()
            return self._parse_html(url, response.text)
        except requests.RequestException as e:
            return PageContent(url=url, error=f"Failed to fetch: {str(e)}")

    # Regex for word-boundary class/id matching (avoid 'nav' matching 'navigation')
    _REMOVE_RE = re.compile(
        r'(?:^|[\s_-])(?:' + '|'.join([
            'ad', 'ads', 'advert', 'advertisement', 'sidebar',
            'nav', 'menu', 'footer', 'header', 'cookie', 'popup',
            'social', 'share', 'comment', 'related', 'banner',
        ]) + r')(?:[\s_-]|$)', re.I,
    )

    def _parse_html(self, url: str, html: str) -> PageContent:
        """Parse HTML and extract clean text content."""
        soup = BeautifulSoup(html, 'html.parser')

        # Extract metadata FIRST (before any decompose calls)
        title = ""
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True)

        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title = og_title['content']

        author = ""
        author_meta = soup.find('meta', attrs={'name': 'author'})
        if author_meta:
            author = author_meta.get('content', '')

        date = ""
        for attr in ['datePublished', 'date', 'article:published_time']:
            date_tag = soup.find('meta', attrs={'property': attr}) or soup.find('meta', attrs={'name': attr})
            if date_tag and date_tag.get('content'):
                date = date_tag['content'][:10]
                break
        if not date:
            time_tag = soup.find('time')
            if time_tag and time_tag.get('datetime'):
                date = time_tag['datetime'][:10]

        meta_desc = ""
        desc_tag = soup.find('meta', attrs={'name': 'description'})
        if desc_tag:
            meta_desc = desc_tag.get('content', '')

        # STEP 1: Find the main content area BEFORE any cleanup
        main_content = (
            soup.find('article') or
            soup.find('main') or
            soup.find(attrs={'role': 'main'}) or
            soup.find(id=re.compile(r'^(?:content|article|post|entry|body)', re.I)) or
            soup.find(class_=re.compile(r'(?:^|[\s-])(?:article|post|entry)(?:[\s-]|$)', re.I)) or
            soup.find('body')
        )
        if not main_content:
            main_content = soup

        # STEP 2: Remove unwanted tags WITHIN the main content area only
        for tag_name in self.REMOVE_TAGS:
            for tag in main_content.find_all(tag_name):
                tag.decompose()

        # STEP 3: Remove ad/nav elements using word-boundary matching
        # Collect elements to remove first, then decompose (avoid modifying tree during iteration)
        to_remove = []
        for element in main_content.find_all(True):
            try:
                classes = ' '.join(element.get('class', []) or [])
                id_val = element.get('id', '') or ''
                combined = classes + ' ' + id_val
                if self._REMOVE_RE.search(combined):
                    to_remove.append(element)
            except Exception:
                continue

        for element in to_remove:
            try:
                element.decompose()
            except Exception:
                pass

        # STEP 4: Extract text
        text = main_content.get_text(separator='\n', strip=True)

        # Clean up: remove excessive whitespace and very short lines
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        text = '\n'.join(lines)

        # Extract links
        links = []
        for a_tag in main_content.find_all('a', href=True):
            href = a_tag['href']
            if href.startswith('http'):
                links.append(href)

        # Extract images
        images = []
        for img_tag in main_content.find_all('img', src=True):
            src = img_tag['src']
            if src.startswith('http'):
                images.append(src)

        return PageContent(
            url=url,
            title=title,
            text=text[:15000],
            author=author,
            date=date,
            word_count=len(text.split()),
            links=links[:20],
            images=images[:10],
            meta_description=meta_desc,
        )

    def summarize_url(self, url: str, mode: str = "key_points") -> PageSummary:
        """
        Summarize a web page by URL.

        Args:
            url: The page URL
            mode: "tldr" (1-2 sentences), "key_points" (bullet points), "detailed" (full summary)
        """
        page = self.extract_page(url)
        if not page.is_valid:
            return PageSummary(url=url, title=page.title,
                               tldr=f"Could not summarize: {page.error}")

        return self._summarize_content(page, mode)

    def summarize_html(self, html: str, url: str = "", mode: str = "key_points") -> PageSummary:
        """Summarize from raw HTML content (e.g., from active browser tab)."""
        if not BS4_OK:
            return PageSummary(url=url, tldr="beautifulsoup4 not installed")

        page = self._parse_html(url, html)
        if not page.is_valid:
            return PageSummary(url=url, title=page.title,
                               tldr="Could not extract content from page")

        return self._summarize_content(page, mode)

    def summarize_text(self, text: str, title: str = "", url: str = "",
                       mode: str = "key_points") -> PageSummary:
        """Summarize plain text content directly."""
        page = PageContent(url=url, title=title, text=text,
                           word_count=len(text.split()))
        return self._summarize_content(page, mode)

    def _summarize_content(self, page: PageContent, mode: str) -> PageSummary:
        """Generate AI summary from extracted page content."""
        if not self.ai_router:
            return self._fallback_summary(page)

        if mode == "tldr":
            prompt = (
                f"Summarize this article in 1-2 sentences (TL;DR):\n\n"
                f"Title: {page.title}\n\n"
                f"{page.text[:8000]}"
            )
        elif mode == "detailed":
            prompt = (
                f"Provide a detailed summary of this article. Include:\n"
                f"- Main argument/topic\n- Key facts and data\n- Conclusions\n\n"
                f"Title: {page.title}\n\n"
                f"{page.text[:12000]}"
            )
        else:  # key_points
            prompt = (
                f"Summarize this article as bullet points (5-8 key points):\n\n"
                f"Title: {page.title}\n\n"
                f"{page.text[:10000]}"
            )

        try:
            response = self.ai_router.query(prompt)
            if response:
                summary = PageSummary(
                    url=page.url,
                    title=page.title,
                    detailed_summary=response,
                    word_count_original=page.word_count,
                    word_count_summary=len(response.split()),
                )

                # Extract key points from bullet response
                if mode == "key_points":
                    points = []
                    for line in response.split('\n'):
                        line = line.strip()
                        if line and (line.startswith('-') or line.startswith('*') or
                                     line.startswith('•') or re.match(r'^\d+\.', line)):
                            clean = re.sub(r'^[-*•\d.)\s]+', '', line).strip()
                            if clean:
                                points.append(clean)
                    summary.key_points = points

                if mode == "tldr":
                    summary.tldr = response.strip()
                else:
                    # Auto-generate TLDR from first sentence
                    first_sentence = response.split('.')[0].strip()
                    if first_sentence:
                        summary.tldr = first_sentence + '.'

                return summary
        except Exception as e:
            logger.error(f"[PageSummarizer] AI error: {e}")

        return self._fallback_summary(page)

    def _fallback_summary(self, page: PageContent) -> PageSummary:
        """Simple extractive summary when AI is not available."""
        sentences = re.split(r'[.!?]+', page.text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 30]

        tldr = sentences[0] + '.' if sentences else page.meta_description
        key_points = sentences[:5]

        return PageSummary(
            url=page.url,
            title=page.title,
            tldr=tldr,
            key_points=key_points,
            detailed_summary='\n'.join(sentences[:10]),
            word_count_original=page.word_count,
            word_count_summary=sum(len(s.split()) for s in sentences[:10]),
        )

    def compare_pages(self, urls: List[str]) -> str:
        """
        Compare content from multiple pages (multi-tab comparison).

        Returns AI-generated comparison of the pages.
        """
        pages = []
        for url in urls[:5]:  # Limit to 5 pages
            page = self.extract_page(url)
            if page.is_valid:
                pages.append(page)

        if not pages:
            return "Could not extract content from any of the provided URLs."

        if not self.ai_router:
            return "AI router not available for comparison."

        # Build comparison prompt
        page_texts = []
        for i, page in enumerate(pages, 1):
            page_texts.append(
                f"--- Page {i}: {page.title} ---\n"
                f"URL: {page.url}\n"
                f"{page.text[:3000]}\n"
            )

        prompt = (
            f"Compare these {len(pages)} web pages and highlight:\n"
            f"- Key similarities\n"
            f"- Key differences\n"
            f"- Which source is more comprehensive\n"
            f"- Unique information in each\n\n"
            + '\n'.join(page_texts)
        )

        try:
            response = self.ai_router.query(prompt)
            return response or "Comparison failed."
        except Exception as e:
            return f"Comparison error: {str(e)}"


# Singleton
_summarizer = None


def get_page_summarizer(ai_router=None) -> PageSummarizer:
    """Get or create singleton page summarizer."""
    global _summarizer
    if _summarizer is None:
        _summarizer = PageSummarizer(ai_router=ai_router)
    return _summarizer
