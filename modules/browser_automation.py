"""
LADA v12.0 - Browser Automation Module
Comet-style browser control with Playwright async operations.
"""

import os
import re
import time
import logging
import asyncio
from typing import Optional, List, Dict, Tuple, Any
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CometBrowserAgent:
    """
    Comet-style browser automation agent.
    Uses Playwright Async API exclusively for autonomous navigation and cross-tab tasks.
    """
    
    def __init__(self, headless: bool = False, timeout: int = 30000):
        """
        Initialize browser agent.
        
        Args:
            headless: Run browser without visible window
            timeout: Default timeout in milliseconds
        """
        self.headless = headless
        self.timeout = timeout
        self.browser = None
        self.page = None
        self.context = None
        self.playwright = None
        self.history: List[Dict] = []
        self.screenshots_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'screenshots')
        os.makedirs(self.screenshots_dir, exist_ok=True)
        
    async def init_browser_async(self) -> bool:
        """Initialize Playwright browser (async version)."""
        try:
            from playwright.async_api import async_playwright
            
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=['--disable-blink-features=AutomationControlled']
            )
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            self.page = await self.context.new_page()
            self.page.set_default_timeout(self.timeout)
            
            logger.info("✅ Playwright browser initialized")
            self._log_action("init_browser", "playwright", True)
            return True
            
        except Exception as e:
            logger.error(f"❌ Playwright initialization failed: {e}")
            self._log_action("init_browser", str(e), False)
            return False

    async def new_tab(self, url: str = "") -> str:
        """Open a new tab and return its ID (page index)."""
        try:
            page = await self.context.new_page()
            page.set_default_timeout(self.timeout)
            self.page = page
            if url:
                await self.page.goto(url, wait_until='domcontentloaded')
            tab_id = str(len(self.context.pages) - 1)
            self._log_action("new_tab", f"Opened new tab: {url}", True)
            return tab_id
        except Exception as e:
            logger.error(f"❌ Failed to open new tab: {e}")
            self._log_action("new_tab", str(e), False)
            return ""

    async def switch_tab(self, index: int) -> bool:
        """Switch to a specific tab by index."""
        try:
            pages = self.context.pages
            if 0 <= index < len(pages):
                self.page = pages[index]
                await self.page.bring_to_front()
                self._log_action("switch_tab", f"Switched to tab {index}", True)
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to switch tab: {e}")
            return False

    async def close_tab(self, index: Optional[int] = None) -> bool:
        """Close current or specified tab."""
        try:
            pages = self.context.pages
            if index is None:
                await self.page.close()
            elif 0 <= index < len(pages):
                await pages[index].close()
            
            # Reset active page to last available or None
            pages = self.context.pages
            if pages:
                self.page = pages[-1]
            else:
                self.page = None
                
            self._log_action("close_tab", "Closed tab", True)
            return True
        except Exception as e:
            logger.error(f"❌ Failed to close tab: {e}")
            return False
            
    async def get_all_tabs(self) -> List[Dict[str, str]]:
        """Return information about all open tabs."""
        tabs = []
        try:
            if not self.context:
                return tabs
            for i, p in enumerate(self.context.pages):
                tabs.append({
                    "id": str(i),
                    "url": p.url,
                    "title": await p.title()
                })
        except Exception:
            pass
        return tabs

    async def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to a URL."""
        if not self.page:
            return {"success": False, "url": url, "error": "No active page"}
        try:
            await self.page.goto(url, wait_until='domcontentloaded')
            title = await self.page.title()
            
            result = {"success": True, "url": url, "title": title}
            self._log_action("navigate", url, True)
            logger.info(f"✅ Navigated to: {url}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Navigation failed: {e}")
            self._log_action("navigate", str(e), False)
            return {"success": False, "url": url, "error": str(e)}
    
    async def click_element(self, selector: str, wait: bool = True) -> Dict[str, Any]:
        """Click an element by CSS selector."""
        if not self.page:
            return {"success": False, "error": "No active page"}
        try:
            if wait:
                await self.page.wait_for_selector(selector, state='visible')
            await self.page.click(selector)
            
            self._log_action("click", selector, True)
            logger.info(f"✅ Clicked: {selector}")
            return {"success": True, "selector": selector}
            
        except Exception as e:
            logger.error(f"❌ Click failed on {selector}: {e}")
            self._log_action("click", str(e), False)
            return {"success": False, "selector": selector, "error": str(e)}
    
    async def fill_form(self, selector: str, value: str, clear_first: bool = True) -> Dict[str, Any]:
        """Fill a form field."""
        if not self.page:
            return {"success": False, "error": "No active page"}
        try:
            await self.page.wait_for_selector(selector)
            if clear_first:
                await self.page.fill(selector, '')
            await self.page.fill(selector, value)
            
            self._log_action("fill_form", f"{selector}={value}", True)
            logger.info(f"✅ Filled {selector} with: {value}")
            return {"success": True, "selector": selector, "value": value}
            
        except Exception as e:
            logger.error(f"❌ Fill failed on {selector}: {e}")
            self._log_action("fill_form", str(e), False)
            return {"success": False, "selector": selector, "error": str(e)}
    
    async def extract_text(self, selector: Optional[str] = None) -> str:
        """Extract text from page or element."""
        if not self.page:
            return ""
        try:
            if selector:
                text = await self.page.inner_text(selector)
            else:
                text = await self.page.inner_text('body')
            
            self._log_action("extract_text", selector or "body", True)
            return text
            
        except Exception as e:
            logger.error(f"❌ Extract text failed: {e}")
            self._log_action("extract_text", str(e), False)
            return ""
    
    async def get_all_links(self) -> List[Tuple[str, str]]:
        """Get all links on the page."""
        if not self.page:
            return []
        try:
            links = await self.page.eval_on_selector_all(
                'a[href]',
                'elements => elements.map(e => [e.innerText, e.href])'
            )
            self._log_action("get_all_links", f"found {len(links)}", True)
            return links
        except Exception as e:
            logger.error(f"❌ Get links failed: {e}")
            return []
            
    async def get_accessibility_tree(self) -> Dict[str, Any]:
        """Fetch the accessibility tree via CDP."""
        if not self.page or not self.context:
            return {}
        try:
            client = await self.context.new_cdp_session(self.page)
            await client.send('Accessibility.enable')
            tree = await client.send('Accessibility.getFullAXTree')
            
            self._log_action("get_accessibility_tree", f"fetched {len(tree.get('nodes', []))} nodes", True)
            return tree
        except Exception as e:
            logger.error(f"❌ Failed to fetch accessibility tree: {e}")
            self._log_action("get_accessibility_tree", str(e), False)
            return {}
    
    async def get_all_prices(self) -> List[Dict[str, Any]]:
        """Find all prices on the page using regex."""
        try:
            text = await self.extract_text()
            
            patterns = [
                r'₹\s*([\d,]+(?:\.\d{2})?)',  # Indian Rupee
                r'Rs\.?\s*([\d,]+(?:\.\d{2})?)',  # Rs format
                r'\$\s*([\d,]+(?:\.\d{2})?)',  # USD
                r'€\s*([\d,]+(?:\.\d{2})?)',  # Euro
                r'£\s*([\d,]+(?:\.\d{2})?)',  # GBP
            ]
            
            prices = []
            currency_map = {'₹': 'INR', 'Rs': 'INR', '$': 'USD', '€': 'EUR', '£': 'GBP'}
            
            for pattern in patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    amount = float(match.replace(',', ''))
                    currency = 'INR'  # Default
                    for symbol, curr in currency_map.items():
                        if symbol in pattern:
                            currency = curr
                            break
                    prices.append({
                        "text": match,
                        "amount": amount,
                        "currency": currency
                    })
            
            prices.sort(key=lambda x: x['amount'])
            self._log_action("get_all_prices", f"found {len(prices)}", True)
            return prices
            
        except Exception as e:
            logger.error(f"❌ Get prices failed: {e}")
            return []
    
    async def get_page_screenshot(self, filename: Optional[str] = None) -> str:
        """Take a screenshot of the page."""
        if not self.page:
            return ""
        try:
            if not filename:
                filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            
            filepath = os.path.join(self.screenshots_dir, filename)
            await self.page.screenshot(path=filepath, full_page=True)
            
            self._log_action("screenshot", filepath, True)
            logger.info(f"📸 Screenshot saved: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"❌ Screenshot failed: {e}")
            return ""
    
    async def execute_js(self, script: str) -> Any:
        """Execute JavaScript on the page."""
        if not self.page:
            return None
        try:
            result = await self.page.evaluate(script)
            self._log_action("execute_js", script[:50], True)
            return result
        except Exception as e:
            logger.error(f"❌ JS execution failed: {e}")
            return None
    
    async def wait_for_element(self, selector: str, timeout: Optional[int] = None) -> bool:
        """Wait for an element to appear."""
        if not self.page:
            return False
        try:
            wait_time = timeout or self.timeout
            await self.page.wait_for_selector(selector, timeout=wait_time)
            return True
        except Exception:
            return False
    
    async def get_current_url(self) -> str:
        """Get current page URL."""
        if not self.page:
            return ""
        try:
            return self.page.url
        except Exception:
            return ""

    async def get_current_title(self) -> str:
        """Get current page title."""
        if not self.page:
            return ""
        try:
            return await self.page.title()
        except Exception:
            return ""
    
    async def go_back(self) -> bool:
        """Navigate back in history."""
        if not self.page:
            return False
        try:
            await self.page.go_back()
            self._log_action("go_back", "", True)
            return True
        except Exception:
            return False
    
    async def refresh(self) -> bool:
        """Refresh the page."""
        if not self.page:
            return False
        try:
            await self.page.reload()
            self._log_action("refresh", "", True)
            return True
        except Exception:
            return False
    
    async def close(self):
        """Close the browser cleanly."""
        try:
            if self.browser:
                await self.browser.close()
                if self.playwright:
                    await self.playwright.stop()
                logger.info("✅ Playwright browser closed")
            
            self._log_action("close", "", True)
            
        except Exception as e:
            logger.error(f"⚠️ Error closing browser: {e}")
    
    def _log_action(self, action: str, details: str, success: bool):
        """Log action to history."""
        tab_id = "-1"
        try:
            if self.context and self.page:
                tab_id = str(self.context.pages.index(self.page))
        except Exception:
            pass

        self.history.append({
            "timestamp": datetime.now().isoformat(),
            "tab_id": tab_id,
            "action": action,
            "details": details,
            "success": success
        })
    
    def get_history(self) -> List[Dict]:
        """Get action history."""
        return self.history


# ============================================================
# EXAMPLE USAGE
# ============================================================
if __name__ == "__main__":
    async def test():
        print("🚀 Testing async CometBrowserAgent...")
        agent = CometBrowserAgent(headless=False)
        if await agent.init_browser_async():
            result = await agent.navigate("https://www.google.com")
            print(f"Navigation: {result}")
            text = await agent.extract_text()
            print(f"Page text length: {len(text)} chars")
            await asyncio.sleep(2)
            await agent.close()
            print("\n✅ All tests passed!")
        else:
            print("❌ Browser initialization failed")

    asyncio.run(test())
