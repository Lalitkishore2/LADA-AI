import os
import base64
import logging
from typing import Dict, Union, Optional
from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext

logger = logging.getLogger(__name__)

class BrowserControl:
    """
    Browser automation class using Playwright.
    Supports isolated "openclaw" profiles and attaching to user profiles via CDP.
    """
    def __init__(self, profile: str = "openclaw", cdp_url: str = "http://localhost:9222"):
        self.profile = profile
        self.cdp_url = cdp_url
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
        self._start_browser()

    def _start_browser(self):
        """Initialize playwright and launch or connect to browser."""
        self.playwright = sync_playwright().start()
        
        if self.profile == "user":
            try:
                # Attempt to connect to existing Chrome instance running with --remote-debugging-port=9222
                logger.info(f"Connecting to existing browser via CDP at {self.cdp_url}")
                self.browser = self.playwright.chromium.connect_over_cdp(self.cdp_url)
                self.context = self.browser.contexts[0]
                if self.context.pages:
                    self.page = self.context.pages[0]
                else:
                    self.page = self.context.new_page()
            except Exception as e:
                logger.warning(f"Could not connect to CDP, falling back to isolated profile. Error: {e}")
                self._launch_isolated()
        else:
            self._launch_isolated()

    def _launch_isolated(self):
        """Launch an isolated browser instance."""
        user_data_dir = os.path.join(os.path.expanduser("~"), ".lada_browser_data")
        os.makedirs(user_data_dir, exist_ok=True)
        
        logger.info(f"Launching isolated browser profile at {user_data_dir}")
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            args=["--window-size=1280,800"]
        )
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()

    def _ensure_page(self):
        """Make sure a page is open before executing commands."""
        if not self.page or self.page.is_closed():
            if self.context:
                self.page = self.context.new_page()

    def close(self):
        """Cleanup playwright resources."""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def open(self, url: str) -> Dict[str, Union[bool, str]]:
        self._ensure_page()
        try:
            if not url.startswith('http'):
                url = 'https://' + url
            self.page.goto(url, wait_until="domcontentloaded")
            return {"success": True, "action": f"opened {url}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def click(self, selector: str) -> Dict[str, Union[bool, str]]:
        self._ensure_page()
        try:
            self.page.click(selector, timeout=5000)
            return {"success": True, "action": f"clicked '{selector}'"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def click_coords(self, x: int, y: int) -> Dict[str, Union[bool, str]]:
        self._ensure_page()
        try:
            self.page.mouse.click(x, y)
            return {"success": True, "action": f"clicked at ({x}, {y})"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def type(self, selector: str, text: str) -> Dict[str, Union[bool, str]]:
        self._ensure_page()
        try:
            self.page.fill(selector, text, timeout=5000)
            return {"success": True, "action": f"typed text into '{selector}'"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def press(self, key: str) -> Dict[str, Union[bool, str]]:
        self._ensure_page()
        try:
            self.page.keyboard.press(key)
            return {"success": True, "action": f"pressed '{key}'"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def scroll(self, direction: str, amount: int = 500) -> Dict[str, Union[bool, str]]:
        self._ensure_page()
        try:
            y_delta = amount if direction.lower() == 'down' else -amount
            self.page.mouse.wheel(0, y_delta)
            return {"success": True, "action": f"scrolled {direction} {amount}px"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def screenshot(self) -> Dict[str, Union[bool, str]]:
        self._ensure_page()
        try:
            image_bytes = self.page.screenshot(type="png", full_page=False)
            b64 = base64.b64encode(image_bytes).decode('utf-8')
            return {"success": True, "image_b64": b64}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_page_text(self) -> Dict[str, Union[bool, str]]:
        self._ensure_page()
        try:
            text = self.page.evaluate("document.body.innerText")
            return {"success": True, "text": text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def evaluate(self, js_code: str) -> Dict[str, Union[bool, str]]:
        self._ensure_page()
        try:
            result = self.page.evaluate(js_code)
            return {"success": True, "result": str(result)}
        except Exception as e:
            return {"success": False, "error": str(e)}
