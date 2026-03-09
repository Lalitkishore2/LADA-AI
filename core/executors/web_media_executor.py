"""
LADA Web/Media Executor — Handles web search, YouTube, travel, shopping,
screenshots, screen vision/OCR, and media playback commands.

Extracted from JarvisCommandProcessor._handle_search, _handle_youtube,
_handle_website, _handle_travel, _handle_shopping, _take_screenshot,
_handle_read_screen, _handle_find_on_screen, _handle_click_text,
_handle_media_control.
"""

import re
import logging
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Tuple

from core.executors import BaseExecutor

logger = logging.getLogger(__name__)


class WebMediaExecutor(BaseExecutor):
    """Handles web browsing, search, screenshot, screen vision, and media commands."""

    def try_handle(self, cmd: str) -> Tuple[bool, str]:
        cmd_lower = cmd.lower().strip()

        # Deep research
        if any(x in cmd_lower for x in ['deep research', 'research in depth',
                                          'comprehensive search', 'detailed research']):
            return self._handle_deep_research(cmd_lower)

        # Weather briefing
        if any(x in cmd_lower for x in ['weather briefing', 'daily briefing',
                                          'today\'s forecast', 'morning briefing']):
            return self._handle_weather_briefing(cmd_lower)

        # Web search
        if any(x in cmd_lower for x in ['search for', 'google ', 'look up', 'search ']):
            return self._handle_search(cmd_lower)

        # YouTube
        if 'youtube' in cmd_lower and any(x in cmd_lower for x in ['play', 'search', 'open', 'watch']):
            return self._handle_youtube(cmd_lower)

        # Direct website navigation
        if any(x in cmd_lower for x in ['go to ', 'open website', 'browse to', 'navigate to']):
            return self._handle_website(cmd_lower)

        # Travel/flights
        if any(x in cmd_lower for x in ['flight', 'flights', 'book flight', 'plane ticket', 'travel to']):
            return self._handle_travel(cmd_lower)

        # Shopping
        if any(x in cmd_lower for x in ['buy ', 'shop for', 'order ', 'purchase']):
            return self._handle_shopping(cmd_lower)

        # Screenshot
        if any(x in cmd_lower for x in ['screenshot', 'screen shot', 'capture screen', 'take a screenshot']):
            return self._take_screenshot()

        # Screen reading / OCR
        if any(x in cmd_lower for x in ['read screen', 'read my screen', 'ocr', 'read text', 'what does the screen say', 'what is on screen', 'what is on my screen']):
            return self._handle_read_screen(cmd_lower)

        # Find on screen
        if any(x in cmd_lower for x in ['find on screen', 'find text', 'locate ', 'where is ']):
            return self._handle_find_on_screen(cmd_lower)

        # Click text on screen
        if any(x in cmd_lower for x in ['click on ', 'click text']):
            return self._handle_click_text(cmd_lower)

        # Media control
        if any(x in cmd_lower for x in ['play music', 'pause music', 'next song', 'previous song', 'stop music']):
            return self._handle_media_control(cmd_lower)

        return False, ""

    # ── Web Search ──────────────────────────────────────────

    def _handle_search(self, cmd: str) -> Tuple[bool, str]:
        """Handle web search commands.

        Option A (default): Return False to let AI answer with web context
        Option B: User explicitly wants to open browser
        """
        explicit_browser = any(x in cmd for x in [
            'open browser', 'open google', 'google it', 'open bing', 'in browser',
            'open and find', 'open and search', 'open amazon', 'open flipkart',
            'browse for', 'go to amazon', 'go to flipkart',
        ])

        if explicit_browser:
            for prefix in ['search for ', 'google ', 'look up ', 'search ',
                           'open browser and search for ', 'open browser and ',
                           'open and find ', 'open and search for ', 'open amazon and search ',
                           'open flipkart and search ', 'find ', 'browse for ']:
                if prefix in cmd:
                    query = cmd.split(prefix, 1)[-1].strip()
                    break
            else:
                query = cmd.replace('open browser', '').replace('open google', '').replace('google it', '')
                query = query.replace('open and find', '').replace('open and search', '').strip()

            if 'amazon' in cmd:
                url = f'https://www.amazon.in/s?k={query.replace(" ", "+")}' if query else 'https://www.amazon.in'
                webbrowser.open(url)
                return True, f"Opening Amazon to browse '{query}'." if query else "Opening Amazon."
            elif 'flipkart' in cmd:
                url = f'https://www.flipkart.com/search?q={query.replace(" ", "+")}' if query else 'https://www.flipkart.com'
                webbrowser.open(url)
                return True, f"Opening Flipkart to browse '{query}'." if query else "Opening Flipkart."
            else:
                if query:
                    url = f'https://www.google.com/search?q={query.replace(" ", "+")}'
                    webbrowser.open(url)
                    return True, f"Opening browser to search for '{query}'."
                else:
                    webbrowser.open('https://www.google.com')
                    return True, "Opening Google."

        return False, ""

    # ── YouTube ─────────────────────────────────────────────

    def _handle_youtube(self, cmd: str) -> Tuple[bool, str]:
        patterns = ['play ', 'search ', 'watch ', 'on youtube', 'youtube ']
        query = cmd
        for pattern in patterns:
            query = query.replace(pattern, ' ')
        query = query.replace('youtube', '').strip()

        if query and len(query) > 2:
            url = f'https://www.youtube.com/results?search_query={query.replace(" ", "+")}'
            webbrowser.open(url)
            return True, f"Searching YouTube for '{query}'."
        else:
            webbrowser.open('https://www.youtube.com')
            return True, "Opening YouTube."

    # ── Website Navigation ──────────────────────────────────

    def _handle_website(self, cmd: str) -> Tuple[bool, str]:
        patterns = ['go to ', 'open website ', 'browse to ', 'navigate to ', 'open ']
        url = cmd
        for pattern in patterns:
            if pattern in url:
                url = url.split(pattern, 1)[-1].strip()

        if url:
            if not url.startswith('http'):
                url = 'https://' + url
            webbrowser.open(url)
            return True, f"Opening {url}."

        return False, ""

    # ── Travel/Flights ──────────────────────────────────────

    def _handle_travel(self, cmd: str) -> Tuple[bool, str]:
        origin = ""
        destination = ""
        date = "tomorrow"

        if ' from ' in cmd and ' to ' in cmd:
            parts = cmd.split(' from ', 1)
            if len(parts) > 1:
                rest = parts[1]
                if ' to ' in rest:
                    from_to = rest.split(' to ', 1)
                    origin = from_to[0].strip()
                    destination = from_to[1].strip()
        elif ' to ' in cmd:
            parts = cmd.split(' to ', 1)
            destination = parts[-1].strip()

        for word in ['flight', 'flights', 'ticket', 'tickets', 'book', 'find', 'me', 'a', 'on', 'for']:
            destination = destination.replace(word, '').strip()
            if origin:
                origin = origin.replace(word, '').strip()

        for dp in ['tomorrow', 'today', 'next week', 'this weekend']:
            if dp in cmd:
                date = dp
                break

        # Try FlightAgent if available
        flight_agent = getattr(self.core, 'flight_agent', None)
        if flight_agent and destination:
            try:
                def progress(step, total, desc):
                    logger.info(f"[FlightAgent] Step {step}/{total}: {desc}")

                result = flight_agent.search_flights(
                    from_city=origin or "Your city", to_city=destination,
                    date=date, progress_callback=progress,
                )

                if result.get('status') == 'success':
                    flights = result.get('flights', [])
                    cheapest = result.get('cheapest')
                    recommendation = result.get('recommendation', '')
                    if cheapest:
                        response = f"Found {len(flights)} flights to {destination}!\n\n"
                        response += f"**Best Deal:** {cheapest.get('airline', 'Unknown')} - {cheapest.get('price', 'N/A')}\n"
                        response += f"Duration: {cheapest.get('duration', 'N/A')}\n"
                        if recommendation:
                            response += f"\n{recommendation}"
                        return True, response
                    elif flights:
                        return True, f"Found {len(flights)} flights to {destination}. Check the browser for details."
                elif result.get('status') == 'cancelled':
                    return True, "Flight search cancelled."
            except Exception as e:
                logger.error(f"FlightAgent error: {e}")

        if destination:
            url = f"https://www.google.com/travel/flights?q=flights+to+{destination.replace(' ', '+')}"
            webbrowser.open(url)
            return True, f"Opening Google Flights to search for flights to {destination.title()}."
        else:
            webbrowser.open("https://www.google.com/travel/flights")
            return True, "Opening Google Flights. You can search for any destination."

    # ── Shopping ────────────────────────────────────────────

    def _handle_shopping(self, cmd: str) -> Tuple[bool, str]:
        item = ""
        budget = None

        for prefix in ['buy ', 'shop for ', 'order ', 'purchase ', 'find ', 'search for ']:
            if prefix in cmd:
                item = cmd.split(prefix, 1)[-1].strip()
                break

        budget_match = re.search(r'under\s*(?:rs\.?|₹|inr)?\s*(\d+)', cmd)
        if budget_match:
            budget = int(budget_match.group(1))
            item = re.sub(r'under\s*(?:rs\.?|₹|inr)?\s*\d+', '', item).strip()

        product_agent = getattr(self.core, 'product_agent', None)
        if product_agent and item:
            try:
                def progress(step, total, desc):
                    logger.info(f"[ProductAgent] Step {step}/{total}: {desc}")

                result = product_agent.search_products(
                    query=item, max_price=budget, progress_callback=progress,
                )

                if result.get('status') == 'success':
                    products = result.get('products', [])
                    best_pick = result.get('best_pick')
                    if best_pick:
                        response = f"Found {len(products)} options for '{item}'!\n\n"
                        response += f"**Best Pick:** {best_pick.get('name', 'Unknown')}\n"
                        response += f"Price: {best_pick.get('price', 'N/A')}\n"
                        response += f"Rating: {best_pick.get('rating', 'N/A')}\n"
                        if best_pick.get('source'):
                            response += f"From: {best_pick['source']}\n"
                        return True, response
                    elif products:
                        return True, f"Found {len(products)} products matching '{item}'. Check the browser for details."
            except Exception as e:
                logger.error(f"ProductAgent error: {e}")

        if item:
            url = f"https://www.amazon.in/s?k={item.replace(' ', '+')}"
            webbrowser.open(url)
            return True, f"Opening Amazon to search for {item}."

        webbrowser.open("https://www.amazon.in")
        return True, "Opening Amazon."

    # ── Screenshot ──────────────────────────────────────────

    def _take_screenshot(self) -> Tuple[bool, str]:
        vision = getattr(self.core, 'vision', None)
        if vision:
            result = vision.capture_screen()
            if result['success']:
                return True, f"Screenshot saved to {result['path']}."
            return True, f"Couldn't take screenshot: {result.get('error', 'Unknown error')}"

        try:
            import pyautogui
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            screenshots_dir = Path('screenshots')
            screenshots_dir.mkdir(exist_ok=True)
            filepath = screenshots_dir / f'screenshot_{timestamp}.png'
            screenshot = pyautogui.screenshot()
            screenshot.save(str(filepath))
            return True, f"Screenshot saved to {filepath}."
        except ImportError:
            return True, "I need pyautogui to take screenshots. Install it with: pip install pyautogui"
        except Exception as e:
            return True, f"Couldn't take screenshot: {e}"

    # ── Screen Reading / OCR ────────────────────────────────

    def _handle_read_screen(self, cmd: str) -> Tuple[bool, str]:
        vision = getattr(self.core, 'vision', None)
        if not vision:
            return True, "Screen reading requires the screen_vision module."

        try:
            result = vision.read_screen()
            if result['success']:
                text = result['text']
                if len(text) > 500:
                    text = text[:500] + "..."
                word_count = result.get('word_count', 0)
                confidence = result.get('confidence', 0)
                response = f"Screen Text ({word_count} words, {confidence:.0%} confidence):\n\n{text}"
                if result.get('summary'):
                    response += f"\n\nSummary: {result['summary']}"
                return True, response
            return True, f"Couldn't read screen: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return True, f"Screen reading error: {e}"

    # ── Find on Screen ──────────────────────────────────────

    def _handle_find_on_screen(self, cmd: str) -> Tuple[bool, str]:
        vision = getattr(self.core, 'vision', None)
        if not vision:
            return True, "Screen vision requires the screen_vision module."

        for pattern in ['find on screen ', 'find text ', 'locate ', 'where is ']:
            if pattern in cmd:
                search_text = cmd.split(pattern, 1)[-1].strip()
                break
        else:
            return True, "What text should I look for on screen?"

        try:
            result = vision.find_text_on_screen(search_text)
            if result['success']:
                if result['found']:
                    count = result['count']
                    locs = result['locations'][:3]
                    response = f"Found '{search_text}' {count} time(s) on screen.\n"
                    for i, (x, y, w, h) in enumerate(locs, 1):
                        response += f"  {i}. Position: ({x}, {y})\n"
                    return True, response
                return True, f"Couldn't find '{search_text}' on the current screen."
            return True, f"Search failed: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return True, f"Search error: {e}"

    # ── Click Text on Screen ────────────────────────────────

    def _handle_click_text(self, cmd: str) -> Tuple[bool, str]:
        vision = getattr(self.core, 'vision', None)
        if not vision:
            return True, "Screen vision requires the screen_vision module."

        for pattern in ['click on ', 'click text ', 'click the ']:
            if pattern in cmd:
                target = cmd.split(pattern, 1)[-1].strip().rstrip('.,!?')
                break
        else:
            return True, "What text should I click on?"

        try:
            result = vision.click_on_text(target)
            if result['success']:
                if result.get('clicked'):
                    x, y = result['location']
                    return True, f"Clicked on '{target}' at position ({x}, {y})."
                return True, f"Couldn't find '{target}' on screen to click."
            return True, f"Click failed: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return True, f"Click error: {e}"

    # ── Media Control ───────────────────────────────────────

    def _handle_media_control(self, cmd: str) -> Tuple[bool, str]:
        try:
            import pyautogui

            if 'pause' in cmd or 'stop' in cmd:
                pyautogui.press('playpause')
                return True, "Paused."

            if 'play' in cmd and 'music' in cmd:
                pyautogui.press('playpause')
                return True, "Playing."

            if 'next' in cmd:
                pyautogui.press('nexttrack')
                return True, "Next track."

            if 'previous' in cmd or 'prev' in cmd:
                pyautogui.press('prevtrack')
                return True, "Previous track."

        except ImportError:
            return True, "Media control requires pyautogui. Install with: pip install pyautogui"

        return False, ""

    # ── Deep Research ─────────────────────────────────────────

    def _handle_deep_research(self, cmd: str) -> Tuple[bool, str]:
        try:
            from modules.deep_research import DeepResearchEngine
            engine = DeepResearchEngine()
        except (ImportError, Exception):
            return False, ""

        # Extract topic
        topic = cmd
        for prefix in ['deep research', 'research in depth', 'comprehensive search',
                        'detailed research', 'about ', 'on ']:
            topic = topic.replace(prefix, ' ')
        topic = topic.strip()

        if not topic or len(topic) < 3:
            return True, "What should I research? Example: 'deep research about quantum computing'"

        try:
            result = engine.research(topic)
            if isinstance(result, dict):
                summary = result.get('summary', result.get('report', str(result)))
                sources = result.get('sources', [])
                response = f"**Research: {topic}**\n\n{summary}"
                if sources:
                    response += "\n\n**Sources:**\n"
                    for s in sources[:5]:
                        response += f"- {s}\n"
                return True, response
            return True, f"**Research: {topic}**\n\n{result}"
        except Exception as e:
            logger.error(f"[WebMediaExecutor] Deep research error: {e}")
            return True, f"Research failed: {e}"

    # ── Weather Briefing ──────────────────────────────────────

    def _handle_weather_briefing(self, cmd: str) -> Tuple[bool, str]:
        try:
            from modules.weather_briefing import WeatherBriefing
            wb = WeatherBriefing()
        except (ImportError, Exception):
            return False, ""

        try:
            briefing = wb.get_briefing() if hasattr(wb, 'get_briefing') else wb.generate()
            if briefing:
                return True, briefing
            return True, "Could not generate weather briefing. Check your weather API configuration."
        except Exception as e:
            logger.error(f"[WebMediaExecutor] Weather briefing error: {e}")
            return True, f"Weather briefing error: {e}"
