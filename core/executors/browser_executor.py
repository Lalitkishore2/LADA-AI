"""
LADA Browser Executor — Handles smart browser, browser tabs, YouTube/page
summarization, and multi-tab orchestrator commands.

Extracted from JarvisCommandProcessor.process() browser-related blocks.

Security Features (Perplexity Comet-style hard boundaries):
- isInternalPage: Blocks navigation to chrome://, about:, devtools:// pages
- isUrlBlocked: Blocks file:// URIs and other dangerous schemes
"""

import re
import os
import logging
from typing import Tuple, Set
from urllib.parse import urlparse

from core.executors import BaseExecutor

logger = logging.getLogger(__name__)


# ============================================================================
# HARD BOUNDARIES - Security constraints for browser automation
# ============================================================================

# Internal Chrome pages that the agent must NEVER navigate to
_INTERNAL_PAGE_PREFIXES: Set[str] = {
    'chrome://',
    'chrome-extension://',
    'chrome-devtools://',
    'devtools://',
    'about:',
    'edge://',
    'brave://',
    'opera://',
    'vivaldi://',
}

# URL schemes that are blocked for security
_BLOCKED_SCHEMES: Set[str] = {
    'file',          # Local filesystem access
    'javascript',    # XSS vector
    'data',          # Can encode malicious content
    'vbscript',      # Windows scripting
    'blob',          # Can access local data
}

# Specific paths that should never be automated
_BLOCKED_PATHS: Set[str] = {
    '/settings',
    '/password',
    '/passwords',
    '/payment-methods',
    '/addresses',
    '/sync',
    '/extensions',
    '/flags',
    '/net-internals',
    '/inspect',
}


def is_internal_page(url: str) -> bool:
    """
    Check if URL is an internal browser page (chrome://, about:, etc.).
    
    These pages should NEVER be navigated to by the AI agent as they
    can expose sensitive settings and system information.
    
    Args:
        url: The URL to check
        
    Returns:
        True if this is an internal page that should be blocked
    """
    if not url:
        return False
    
    url_lower = url.lower().strip()
    
    for prefix in _INTERNAL_PAGE_PREFIXES:
        if url_lower.startswith(prefix):
            logger.warning(f"[HardBoundary] Blocked internal page: {url}")
            return True
    
    return False


def is_url_blocked(url: str) -> bool:
    """
    Check if URL uses a blocked scheme or accesses dangerous paths.
    
    Blocks:
    - file:// URIs (local filesystem access)
    - javascript: URIs (XSS vector)
    - data: URIs (can encode malicious content)
    - Sensitive browser paths (/settings, /passwords, etc.)
    
    Args:
        url: The URL to check
        
    Returns:
        True if this URL should be blocked
    """
    if not url:
        return False
    
    url_lower = url.lower().strip()
    
    # Check internal pages first
    if is_internal_page(url_lower):
        return True
    
    try:
        parsed = urlparse(url_lower)
        
        # Check scheme
        if parsed.scheme in _BLOCKED_SCHEMES:
            logger.warning(f"[HardBoundary] Blocked scheme '{parsed.scheme}': {url}")
            return True
        
        # Check for sensitive paths on any domain
        for blocked_path in _BLOCKED_PATHS:
            if blocked_path in parsed.path.lower():
                logger.warning(f"[HardBoundary] Blocked sensitive path '{blocked_path}': {url}")
                return True
        
    except Exception as e:
        # If we can't parse it, be conservative and block
        logger.warning(f"[HardBoundary] Could not parse URL, blocking: {url} ({e})")
        return True
    
    return False


def validate_navigation_url(url: str) -> Tuple[bool, str]:
    """
    Validate a URL for safe navigation.
    
    Returns:
        Tuple of (is_safe, error_message)
    """
    if not url:
        return False, "Empty URL"
    
    if is_url_blocked(url):
        return False, f"Navigation blocked: {url} (security policy)"
    
    # Ensure it has a valid scheme
    if not url.startswith(('http://', 'https://', 'www.')):
        # Could be a domain without scheme, prepend https://
        url = f"https://{url}"
    
    return True, ""


class BrowserExecutor(BaseExecutor):
    """Handles browser control, tab management, summarization, and multi-tab commands."""

    def try_handle(self, cmd: str) -> Tuple[bool, str]:
        # Browser compatibility aliases (shared core path for CLI/API/Desktop)
        handled, resp = self._handle_browser_compat(cmd)
        if handled:
            return True, resp

        # "computer" command -> Comet agent (desktop-computer tool style)
        if cmd.lower().startswith('computer ') or cmd.lower().startswith('computer,'):
            task = cmd[9:].strip().lstrip(',').strip()
            if task and self.core.comet_agent:
                return self._execute_comet_task(task)

        # Comet autonomous agent (browser/GUI tasks)
        handled, resp = self._handle_comet(cmd)
        if handled:
            return True, resp

        # Stealth browser mode (anti-bot, undetected)
        handled, resp = self._handle_stealth(cmd)
        if handled:
            return True, resp

        # Smart browser control
        if self.core.smart_browser:
            handled, resp = self._handle_smart_browser(cmd)
            if handled:
                return True, resp

        # Browser tab controller
        if self.core.browser_tabs:
            handled, resp = self._handle_browser_tabs(cmd)
            if handled:
                return True, resp

        # YouTube summarizer (check before page summarizer)
        if self.core.youtube_summarizer:
            handled, resp = self._handle_youtube_summarizer(cmd)
            if handled:
                return True, resp

        # Page summarizer
        if self.core.page_summarizer:
            handled, resp = self._handle_page_summarizer(cmd)
            if handled:
                return True, resp

        # Multi-tab orchestrator
        if self.core.multi_tab:
            handled, resp = self._handle_multi_tab(cmd)
            if handled:
                return True, resp

        return False, ""

    # -- Browser Compatibility Aliases ----------------------

    def _handle_browser_compat(self, cmd: str) -> Tuple[bool, str]:
        stripped = cmd.strip()
        lowered = stripped.lower()
        if not lowered.startswith("lada browser"):
            return False, ""

        command = lowered
        display_name = "LADA browser"
        adapter = None

        try:
            from integrations.lada_browser_adapter import get_lada_browser_adapter
            adapter = get_lada_browser_adapter()
        except Exception as e:
            logger.debug(f"[BrowserExecutor] Browser adapter unavailable: {e}")

        if command in {"lada browser", "lada browser help"}:
            return True, (
                "LADA browser commands:\n"
                "- lada browser status\n"
                "- lada browser connect\n"
                "- lada browser disconnect\n"
                "- lada browser navigate <url>\n"
                "- lada browser snapshot\n"
                "- lada browser click <selector>\n"
                "- lada browser type <selector> :: <text>\n"
                "- lada browser scroll <up|down> [pixels]\n"
                "- lada browser extract [selector]"
            )

        if command == "lada browser status":
            lines = ["LADA browser compatibility status:"]
            if adapter:
                status = adapter.status()
                lines.append(f"- adapter enabled: {status.get('enabled', False)}")
                lines.append(f"- adapter state: {status.get('state', 'unknown')}")
                lines.append(f"- adapter connected: {status.get('connected', False)}")
                if status.get('url'):
                    lines.append(f"- gateway: {status.get('url')}")
            else:
                lines.append("- adapter: disabled (set LADA_BROWSER_ADAPTER_ENABLED=true to enable gateway mode)")
            return True, "\n".join(lines)

        if command == "lada browser connect":
            if not adapter:
                return True, f"{display_name} adapter is disabled. Set LADA_BROWSER_ADAPTER_ENABLED=true and restart."
            ok = adapter.connect()
            return True, f"{display_name} adapter connected." if ok else f"{display_name} adapter connection failed."

        if command == "lada browser disconnect":
            if not adapter:
                return True, f"{display_name} adapter is not active."
            adapter.disconnect()
            return True, f"{display_name} adapter disconnected."

        if command.startswith("lada browser navigate "):
            prefix = "lada browser navigate "
            url = command[len(prefix):].strip()
            if not url:
                return True, "Usage: lada browser navigate <url>"
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"

            if adapter and adapter.navigate(url):
                return True, f"{display_name} adapter navigated to {url}."

            try:
                from modules.stealth_browser import get_stealth_browser
                browser = get_stealth_browser()
                result = browser.navigate(url)
                if result.get('success'):
                    return True, f"Stealth navigation successful: {result.get('url', url)}"
            except Exception:
                pass

            if getattr(self.core, 'browser_tabs', None):
                result = self.core.browser_tabs.navigate_to(url)
                if result.get('success'):
                    return True, f"Navigated to {url}"

            return True, f"Tried native navigation to {url}, but could not complete it."

        if command == "lada browser snapshot":
            if adapter:
                snapshot = adapter.snapshot_summary()
                if snapshot:
                    return True, (
                        "LADA browser snapshot summary:\n"
                        f"- URL: {snapshot.get('url', '')}\n"
                        f"- Title: {snapshot.get('title', '')}\n"
                        f"- Interactive elements: {snapshot.get('interactive_elements', 0)}\n"
                        f"- Text chars: {snapshot.get('text_chars', 0)}"
                    )

            try:
                from modules.stealth_browser import get_stealth_browser
                browser = get_stealth_browser()
                page = browser.get_page_content()
                if page.get('success'):
                    shot = browser.screenshot()
                    msg = (
                        "Native snapshot summary:\n"
                        f"- URL: {page.get('url', '')}\n"
                        f"- Title: {page.get('title', '')}\n"
                        f"- Text chars: {len(str(page.get('text', '')))}"
                    )
                    if shot.get('success'):
                        msg += f"\n- Screenshot: {shot.get('path', '')}"
                    return True, msg
            except Exception:
                pass

            return True, "Native snapshot command is currently unavailable."

        if command.startswith("lada browser click "):
            prefix = "lada browser click "
            selector = command[len(prefix):].strip()
            if not selector:
                return True, "Usage: lada browser click <selector>"

            if adapter and adapter.click(selector):
                return True, f"{display_name} adapter clicked: {selector}"

            try:
                from modules.stealth_browser import get_stealth_browser
                browser = get_stealth_browser()
                result = browser.click(selector=selector)
                if result.get('success'):
                    return True, f"Stealth click successful: {selector}"
            except Exception:
                pass

            return True, f"Could not click selector: {selector}"

        if command.startswith("lada browser type "):
            prefix = "lada browser type "
            payload = command[len(prefix):].strip()
            separator = "::" if "::" in payload else "|" if "|" in payload else ""
            if not separator:
                return True, "Usage: lada browser type <selector> :: <text>"

            selector, typed = [p.strip() for p in payload.split(separator, 1)]
            if not selector:
                return True, "Usage: lada browser type <selector> :: <text>"

            if adapter and adapter.type_text(selector, typed):
                return True, f"{display_name} adapter typed into {selector}."

            try:
                from modules.stealth_browser import get_stealth_browser
                browser = get_stealth_browser()
                result = browser.type_text(selector=selector, text=typed)
                if result.get('success'):
                    return True, f"Stealth typed into {selector}."
            except Exception:
                pass

            return True, f"Could not type into selector: {selector}"

        if command.startswith("lada browser scroll "):
            prefix = "lada browser scroll "
            payload = command[len(prefix):].strip().split()
            direction = payload[0].lower() if payload else "down"
            if direction not in {"up", "down"}:
                direction = "down"

            amount = 500
            if len(payload) > 1:
                try:
                    amount = int(payload[1])
                except Exception:
                    amount = 500

            if adapter and adapter.scroll(direction=direction, amount=amount):
                return True, f"{display_name} adapter scrolled {direction} by {amount}px."

            try:
                from modules.stealth_browser import get_stealth_browser
                browser = get_stealth_browser()
                result = browser.scroll(direction=direction, amount=amount)
                if result.get('success'):
                    return True, f"Stealth scrolled {direction} by {amount}px."
            except Exception:
                pass

            return True, f"Could not scroll {direction}."

        if command.startswith("lada browser extract"):
            prefix = "lada browser extract"
            selector = command[len(prefix):].strip()

            if adapter:
                text_out = adapter.extract_text(selector=selector or None)
                if text_out:
                    return True, text_out[:4000]

            try:
                from modules.stealth_browser import get_stealth_browser
                browser = get_stealth_browser()
                if selector:
                    result = browser.execute_js(
                        "const el=document.querySelector(arguments[0]); return el ? el.innerText : '';",
                        selector,
                    )
                    if result:
                        return True, str(result)[:4000]

                page = browser.get_page_content()
                if page.get('success'):
                    return True, str(page.get('text', ''))[:4000]
            except Exception:
                pass

            return True, "Could not extract page content."

        return True, (
            "LADA browser command not recognized. "
            "Use 'lada browser help' for supported commands."
        )

    # ── Stealth Browser ─────────────────────────────────────

    def _handle_stealth(self, cmd: str) -> Tuple[bool, str]:
        if not any(x in cmd for x in ['stealth', 'undetected', 'anti-bot', 'antibot']):
            return False, ""

        try:
            from modules.stealth_browser import get_stealth_browser
            browser = get_stealth_browser()
        except Exception as e:
            return True, f"Stealth browser is unavailable: {e}"

        # Navigate/open URL
        nav_match = re.search(r'(?:go to|navigate to|open)\s+(\S+)', cmd)
        if nav_match:
            url = nav_match.group(1).strip()
            if not url.startswith(('http://', 'https://')):
                url = f"https://{url}"
            
            # HARD BOUNDARY CHECK
            is_safe, error_msg = validate_navigation_url(url)
            if not is_safe:
                return True, f"🚫 {error_msg}"
            
            result = browser.navigate(url)
            if result.get('success'):
                return True, f"Stealth navigation successful: {result.get('url', url)}"
            return True, result.get('error', 'Stealth navigation failed')

        # Click selector
        click_match = re.search(r'click\s+(.+)$', cmd)
        if click_match:
            selector = click_match.group(1).strip()
            result = browser.click(selector=selector)
            if result.get('success'):
                return True, f"Stealth click successful: {selector}"
            return True, result.get('error', f"Stealth click failed: {selector}")

        # Type text into selector: "type <text> into <selector>"
        type_match = re.search(r'type\s+(.+?)\s+(?:into|in|to)\s+(.+)$', cmd)
        if type_match:
            typed = type_match.group(1).strip().strip('"\'')
            selector = type_match.group(2).strip()
            result = browser.type_text(selector=selector, text=typed)
            if result.get('success'):
                return True, f"Stealth typed into {selector}"
            return True, result.get('error', f"Stealth typing failed: {selector}")

        # Scroll
        if 'scroll' in cmd:
            direction = 'up' if 'up' in cmd else 'down'
            amount_match = re.search(r'(\d+)', cmd)
            amount = int(amount_match.group(1)) if amount_match else 300
            result = browser.scroll(direction=direction, amount=amount)
            if result.get('success'):
                return True, f"Stealth scrolled {direction} by {amount}px"
            return True, result.get('error', 'Stealth scroll failed')

        # Extract text
        if any(x in cmd for x in ['extract', 'read page', 'page text', 'content']):
            page = browser.get_page_content()
            if page.get('success'):
                text = str(page.get('text', ''))
                return True, text[:700] if text else "No text content extracted."
            return True, page.get('error', 'Stealth extract failed')

        return True, "Stealth mode is ready. Try: 'stealth go to <url>' or 'stealth click <selector>'."

    # ── Comet Autonomous Agent ───────────────────────────────

    def _handle_comet(self, cmd: str) -> Tuple[bool, str]:
        if not self.core.comet_agent:
            return False, ""

        # Explicit autonomous triggers
        if any(x in cmd for x in ['autonomously', 'automatically do', 'do this for me', 'take over', 'auto complete']):
            task_match = re.search(r'(?:autonomously|automatically|auto)\s+(.+)', cmd)
            task = task_match.group(1) if task_match else cmd
            return self._execute_comet_task(task)

        # Multi-step browser/GUI tasks
        if self._is_autonomous_task(cmd):
            return self._execute_comet_task(cmd)

        # Quick actions via comet
        quick_actions = getattr(self.core, 'quick_actions', None)
        if quick_actions:
            if ('search' in cmd and any(x in cmd for x in ['google', 'in browser', 'on google', 'on the browser'])):
                query_match = re.search(r'search\s+(?:for\s+|google\s+for\s+|on google\s+for\s+)?(.+?)(?:\s+on google|\s+in browser|\s+on the browser)?$', cmd)
                if query_match:
                    query = query_match.group(1).strip()
                    return self._execute_comet_task(f"open Google Chrome, go to google.com and search for {query}")

            if any(x in cmd for x in ['go to', 'navigate to', 'open website']):
                url_match = re.search(r'(?:go to|navigate to|open website)\s+(\S+)', cmd)
                if url_match:
                    url = url_match.group(1).strip()
                    rest = cmd[url_match.end():].strip()
                    if rest and any(x in rest for x in ['and ', 'then ', 'search', 'click', 'type', 'find']):
                        return self._execute_comet_task(cmd)
                    if self.core.browser_tabs:
                        result = self.core.browser_tabs.navigate_to(url)
                        if result.get('success'):
                            return True, f"Navigated to {url}"

        return False, ""

    def _execute_comet_task(self, task: str) -> Tuple[bool, str]:
        """Delegate task to the Comet autonomous agent."""
        try:
            result = self.core.comet_agent.execute_task(task)
            if isinstance(result, dict):
                if result.get('success'):
                    return True, result.get('message', f"Task completed: {task}")
                return True, result.get('error', f"Task failed: {task}")
            return True, str(result)
        except Exception as e:
            logger.error(f"Comet agent error: {e}")
            return True, f"Autonomous task failed: {e}"

    def _is_autonomous_task(self, cmd: str) -> bool:
        """Check if command needs autonomous agent (multi-step browser/GUI)."""
        indicators = [
            'and then', 'after that', 'and search', 'and click',
            'and type', 'and fill', 'and submit', 'step by step',
        ]
        return any(x in cmd for x in indicators)

    # ── Smart Browser ────────────────────────────────────────

    def _handle_smart_browser(self, cmd: str) -> Tuple[bool, str]:
        sb = self.core.smart_browser

        # Engine-specific searches
        engine_patterns = {
            'youtube': (['search youtube for', 'search on youtube', 'youtube search'], r'(?:search youtube for|search on youtube|youtube search)\s+(.+)'),
            'amazon': (['search amazon for', 'search on amazon', 'amazon search', 'find on amazon', 'buy on amazon'], r'(?:search|find|buy)\s+(?:on\s+)?amazon\s+(?:for\s+)?(.+)'),
            'flipkart': (['search flipkart', 'find on flipkart', 'flipkart search'], r'(?:search|find)\s+(?:on\s+)?flipkart\s+(?:for\s+)?(.+)'),
            'github': (['search github for', 'search on github', 'find on github', 'github search'], r'(?:search|find)\s+(?:on\s+)?github\s+(?:for\s+)?(.+)'),
            'maps': (['search maps for', 'search on maps', 'find on maps', 'show on map', 'directions to'], r'(?:search maps for|search on maps|find on maps|show on map|directions to)\s+(.+)'),
            'images': (['search images', 'find images of', 'image search', 'google images'], r'(?:search images|find images of|image search|google images)\s+(?:of\s+|for\s+)?(.+)'),
            'news': (['search news', 'find news about', 'news about', 'latest news'], r'(?:search news|find news about|news about|latest news)\s+(?:about\s+|on\s+)?(.+)'),
            'wikipedia': (['search wikipedia', 'wiki', 'look up on wikipedia'], r'(?:search wikipedia|wiki|look up on wikipedia)\s+(?:for\s+)?(.+)'),
            'stackoverflow': (['search stackoverflow', 'stackoverflow', 'find on stackoverflow'], r'(?:search stackoverflow|stackoverflow|find on stackoverflow)\s+(?:for\s+)?(.+)'),
        }

        for engine, (triggers, pattern) in engine_patterns.items():
            if any(x in cmd for x in triggers):
                match = re.search(pattern, cmd)
                if match:
                    query = match.group(1).strip()
                    result = sb.search_web(query, engine)
                    return True, result.get('message', f'Searching {engine} for {query}')

        # Incognito
        if any(x in cmd for x in ['incognito', 'private browsing', 'private window', 'incognito mode']):
            url_match = re.search(r'(?:incognito|private)\s+(?:mode\s+)?(?:with\s+|open\s+)?(\S+)', cmd)
            url = url_match.group(1) if url_match and '.' in url_match.group(1) else None
            result = sb.open_incognito(url)
            return True, result.get('message', 'Opened incognito')

        # Read page
        if any(x in cmd for x in ['read this page', 'read page', 'read page content', 'page text',
                                   'what does this page say', 'read website']):
            result = sb.read_page_text()
            if result.get('success'):
                text = result.get('text', '')[:500]
                return True, f"Page content ({result.get('length', 0)} chars):\n{text}..."
            return True, "Could not read page content."

        # Find in page
        if any(x in cmd for x in ['find in page', 'find on page', 'search this page', 'ctrl f']):
            match = re.search(r'(?:find in page|find on page|search this page|ctrl f)\s+(?:for\s+)?(.+)', cmd)
            if match:
                text = match.group(1).strip()
                result = sb.find_in_page(text)
                return True, result.get('message', f'Searching for {text}')
            return True, "What should I find? Say 'find in page [text]'."

        # Zoom
        if any(x in cmd for x in ['zoom in', 'make bigger', 'increase zoom']):
            result = sb.zoom_in()
            return True, result.get('message', 'Zoomed in')

        if any(x in cmd for x in ['zoom out', 'make smaller', 'decrease zoom']):
            result = sb.zoom_out()
            return True, result.get('message', 'Zoomed out')

        if any(x in cmd for x in ['reset zoom', 'zoom 100', 'normal zoom', 'default zoom']):
            result = sb.reset_zoom()
            return True, result.get('message', 'Zoom reset')

        # Bookmark
        if any(x in cmd for x in ['bookmark this', 'bookmark page', 'save bookmark', 'add bookmark']):
            result = sb.bookmark_page()
            return True, result.get('message', 'Bookmark dialog opened')

        # Print
        if any(x in cmd for x in ['print this page', 'print page', 'print this']):
            result = sb.print_page()
            return True, result.get('message', 'Print dialog opened')

        # Save page
        if any(x in cmd for x in ['save this page', 'save page', 'save website']):
            result = sb.save_page()
            return True, result.get('message', 'Save dialog opened')

        # Clear browsing data
        if any(x in cmd for x in ['clear browsing data', 'clear browser history', 'clear browser cache', 'delete history']):
            result = sb.clear_browsing_data()
            return True, result.get('message', 'Clear browsing data dialog opened')

        # Dev tools
        if any(x in cmd for x in ['developer tools', 'dev tools', 'open console', 'inspect element']):
            result = sb.open_dev_tools()
            return True, result.get('message', 'Developer tools opened')

        return False, ""

    # ── Browser Tabs ─────────────────────────────────────────

    def _handle_browser_tabs(self, cmd: str) -> Tuple[bool, str]:
        bt = self.core.browser_tabs

        if any(x in cmd for x in ['new tab', 'open tab', 'open new tab']):
            match = re.search(r'(?:new tab|open tab|open new tab)\s*(?:with|to|for)?\s*(.+)?', cmd)
            url = match.group(1).strip() if match and match.group(1) else None
            
            # HARD BOUNDARY CHECK for new tab with URL
            if url:
                is_safe, error_msg = validate_navigation_url(url)
                if not is_safe:
                    return True, f"🚫 {error_msg}"
            
            result = bt.open_tab(url)
            if result.get('success'):
                return True, f"✅ Opened new tab" + (f": {url}" if url else "")
            return True, "Couldn't open new tab"

        if any(x in cmd for x in ['close tab', 'close this tab']):
            result = bt.close_tab()
            return True, "✅ Tab closed" if result.get('success') else "Couldn't close tab"

        if any(x in cmd for x in ['next tab', 'switch tab', 'previous tab', 'prev tab']):
            direction = 'prev' if 'prev' in cmd else 'next'
            result = bt.switch_tab(direction)
            return True, f"✅ Switched to {direction} tab" if result.get('success') else "Couldn't switch tab"

        if 'tab' in cmd and any(str(i) in cmd for i in range(1, 10)):
            match = re.search(r'tab\s*(\d)', cmd)
            if match:
                tab_num = int(match.group(1))
                result = bt.switch_to_tab_number(tab_num)
                return True, f"✅ Switched to tab {tab_num}" if result.get('success') else "Couldn't switch"

        if any(x in cmd for x in ['go to', 'navigate to', 'open website']):
            match = re.search(r'(?:go to|navigate to|open website)\s+(.+)', cmd)
            if match:
                url = match.group(1).strip()
                
                # HARD BOUNDARY CHECK
                is_safe, error_msg = validate_navigation_url(url)
                if not is_safe:
                    return True, f"🚫 {error_msg}"
                
                result = bt.navigate_to(url)
                return True, f"✅ Navigated to {url}" if result.get('success') else "Couldn't navigate"

        if any(x in cmd for x in ['refresh', 'reload', 'refresh page', 'reload page']):
            hard = 'hard' in cmd or 'force' in cmd
            result = bt.refresh_tab(hard)
            return True, "✅ Page refreshed" if result.get('success') else "Couldn't refresh"

        if 'go back' in cmd or 'back' == cmd:
            result = bt.go_back()
            return True, "✅ Went back" if result.get('success') else "Couldn't go back"

        if 'go forward' in cmd or 'forward' == cmd:
            result = bt.go_forward()
            return True, "✅ Went forward" if result.get('success') else "Couldn't go forward"

        if 'youtube' in cmd and 'search' in cmd:
            match = re.search(r'youtube\s+(?:search\s+)?(?:for\s+)?(.+)', cmd)
            if match:
                query = match.group(1).strip()
                result = bt.youtube_search(query)
                return True, f"✅ Searching YouTube for: {query}" if result.get('success') else "Couldn't search"

        if any(x in cmd for x in ['incognito', 'private mode', 'private browsing']):
            result = bt.open_incognito()
            return True, "Opened private browsing" if result.get('success') else "Couldn't open"

        return False, ""

    # ── YouTube Summarizer ───────────────────────────────────

    def _handle_youtube_summarizer(self, cmd: str) -> Tuple[bool, str]:
        is_youtube = 'youtube' in cmd or 'youtu.be' in cmd
        is_summarize = any(x in cmd for x in ['summarize', 'summarise', 'summary', 'explain video', 'key points'])

        if is_youtube and is_summarize:
            # Use original (non-lowered) command to preserve video ID case
            # We only have the lowered cmd here; URL extraction still works for matching
            url_match = re.search(r'(https?://\S+)', cmd, re.IGNORECASE)
            if url_match:
                url = url_match.group(1)
                mode = "timestamps" if 'timestamp' in cmd else "key_points"
                summary = self.core.youtube_summarizer.summarize(url, mode=mode)
                if summary.error:
                    return True, f"Could not summarize video: {summary.error}"
                response = f"Video: {summary.title}\n"
                if summary.channel:
                    response += f"Channel: {summary.channel}\n\n"
                if summary.key_points:
                    response += "Key Points:\n"
                    response += '\n'.join(f"  - {p}" for p in summary.key_points)
                elif summary.detailed_summary:
                    response += summary.detailed_summary[:600]
                if summary.timestamps:
                    response += "\n\nTimestamps:\n"
                    response += '\n'.join(f"  [{t['time']}] {t['topic']}" for t in summary.timestamps[:10])
                return True, response

        if is_youtube and any(x in cmd for x in ['summarize', 'what is this video about']):
            return True, "Paste the YouTube URL: 'summarize https://youtube.com/watch?v=...'"

        return False, ""

    # ── Page Summarizer ──────────────────────────────────────

    def _handle_page_summarizer(self, cmd: str) -> Tuple[bool, str]:
        ps = self.core.page_summarizer

        if any(x in cmd for x in ['summarize', 'summarise', 'summary of', 'tldr']):
            url_match = re.search(r'(https?://\S+)', cmd, re.IGNORECASE)
            if url_match:
                url = url_match.group(1)
                # Skip YouTube URLs (handled by YouTube summarizer)
                if 'youtube.com' not in url and 'youtu.be' not in url:
                    mode = "tldr" if 'tldr' in cmd else "key_points"
                    summary = ps.summarize_url(url, mode=mode)
                    if summary.key_points:
                        points = '\n'.join(f"  - {p}" for p in summary.key_points)
                        return True, f"Summary of {summary.title}:\n\n{points}"
                    elif summary.tldr:
                        return True, f"TL;DR: {summary.tldr}"
                    else:
                        return True, f"Summary: {summary.detailed_summary[:500]}"

            if any(x in cmd for x in ['this page', 'this article', 'current page']):
                return True, "To summarize a page, paste the URL: 'summarize https://example.com/article'"

        if any(x in cmd for x in ['compare pages', 'compare these', 'compare urls', 'compare websites']):
            urls = re.findall(r'(https?://\S+)', cmd, re.IGNORECASE)
            if len(urls) >= 2:
                result = ps.compare_pages(urls)
                return True, result
            return True, "Provide 2+ URLs to compare: 'compare https://url1.com https://url2.com'"

        return False, ""

    # ── Multi-Tab Orchestrator ───────────────────────────────

    def _handle_multi_tab(self, cmd: str) -> Tuple[bool, str]:
        mt = self.core.multi_tab

        if any(x in cmd for x in ['open workspace', 'workspace', 'open research', 'open development', 'open social', 'open productivity']):
            for ws in ['research', 'development', 'social', 'productivity', 'entertainment']:
                if ws in cmd:
                    result = mt.open_workspace(ws)
                    if result.get('success'):
                        return True, f"✅ Opened {ws} workspace with {result.get('tabs_opened', 0)} tabs"
                    return True, f"Couldn't open {ws} workspace"
            return True, "Available workspaces: research, development, social, productivity, entertainment"

        if 'research' in cmd and any(x in cmd for x in ['topic', 'about', 'on']):
            match = re.search(r'research\s+(?:topic|about|on)?\s*(.+)', cmd)
            if match:
                topic = match.group(1).strip()
                result = mt.research_topic(topic)
                return True, f"✅ Opened research tabs for '{topic}'" if result.get('success') else "Couldn't research"

        if 'compare' in cmd:
            match = re.search(r'compare\s+(.+)', cmd)
            if match:
                product = match.group(1).strip()
                result = mt.compare_products(product)
                return True, f"✅ Opened comparison tabs for '{product}'" if result.get('success') else "Couldn't compare"

        if any(x in cmd for x in ['list workspaces', 'show workspaces', 'available workspaces']):
            result = mt.list_workspaces()
            if result.get('success'):
                ws_list = ', '.join([w['name'] for w in result['workspaces']])
                return True, f"Available workspaces: {ws_list}"

        if 'save session' in cmd:
            from datetime import datetime
            match = re.search(r'save session\s+(?:as\s+)?(.+)', cmd)
            name = match.group(1).strip() if match else f"session_{datetime.now().strftime('%H%M')}"
            result = mt.save_session(name)
            return True, f"✅ Session saved as '{name}'" if result.get('success') else "Couldn't save session"

        if 'load session' in cmd:
            match = re.search(r'load session\s+(.+)', cmd)
            if match:
                name = match.group(1).strip()
                result = mt.load_session(name)
                return True, f"✅ Session '{name}' loaded" if result.get('success') else f"Couldn't load session '{name}'"

        return False, ""
