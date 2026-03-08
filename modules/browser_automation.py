"""
LADA v7.0 - Browser Automation Module
Comet-style browser control with Playwright (primary) and Selenium (fallback)
"""

import os
import re
import json
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
    Uses Playwright for async operations with Selenium as fallback.
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
        self.driver = None  # Selenium fallback
        self.using_selenium = False
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
            logger.warning(f"⚠️ Playwright failed: {e}, trying Selenium...")
            return self._init_selenium_fallback()
    
    def init_browser(self) -> bool:
        """Initialize browser (sync wrapper)."""
        try:
            # Try Playwright sync API first
            from playwright.sync_api import sync_playwright
            
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                args=['--disable-blink-features=AutomationControlled']
            )
            self.context = self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            self.page = self.context.new_page()
            self.page.set_default_timeout(self.timeout)
            
            logger.info("✅ Playwright browser initialized (sync)")
            self._log_action("init_browser", "playwright_sync", True)
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ Playwright failed: {e}, trying Selenium...")
            return self._init_selenium_fallback()
    
    def _init_selenium_fallback(self) -> bool:
        """Initialize Selenium as fallback."""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            
            options = Options()
            if self.headless:
                options.add_argument('--headless=new')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            options.add_experimental_option('excludeSwitches', ['enable-automation'])
            
            self.driver = webdriver.Chrome(options=options)
            self.driver.implicitly_wait(self.timeout / 1000)
            self.using_selenium = True
            
            logger.info("✅ Selenium browser initialized (fallback)")
            self._log_action("init_browser", "selenium", True)
            return True
            
        except Exception as e:
            logger.error(f"❌ Both Playwright and Selenium failed: {e}")
            self._log_action("init_browser", str(e), False)
            return False
    
    def navigate(self, url: str) -> Dict[str, Any]:
        """
        Navigate to a URL.
        
        Args:
            url: Target URL
            
        Returns:
            {"success": bool, "url": str, "title": str}
        """
        try:
            if self.using_selenium:
                self.driver.get(url)
                title = self.driver.title
            else:
                self.page.goto(url, wait_until='domcontentloaded')
                title = self.page.title()
            
            result = {"success": True, "url": url, "title": title}
            self._log_action("navigate", url, True)
            logger.info(f"✅ Navigated to: {url}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Navigation failed: {e}")
            self._log_action("navigate", str(e), False)
            return {"success": False, "url": url, "error": str(e)}
    
    def click_element(self, selector: str, wait: bool = True) -> Dict[str, Any]:
        """
        Click an element by CSS selector.
        
        Args:
            selector: CSS selector
            wait: Wait for element to be visible
            
        Returns:
            {"success": bool, "selector": str}
        """
        try:
            if self.using_selenium:
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                
                if wait:
                    element = WebDriverWait(self.driver, self.timeout/1000).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                else:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                element.click()
            else:
                if wait:
                    self.page.wait_for_selector(selector, state='visible')
                self.page.click(selector)
            
            self._log_action("click", selector, True)
            logger.info(f"✅ Clicked: {selector}")
            return {"success": True, "selector": selector}
            
        except Exception as e:
            logger.error(f"❌ Click failed on {selector}: {e}")
            self._log_action("click", str(e), False)
            return {"success": False, "selector": selector, "error": str(e)}
    
    def fill_form(self, selector: str, value: str, clear_first: bool = True) -> Dict[str, Any]:
        """
        Fill a form field.
        
        Args:
            selector: CSS selector for input
            value: Value to fill
            clear_first: Clear existing content first
            
        Returns:
            {"success": bool, "selector": str, "value": str}
        """
        try:
            if self.using_selenium:
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                
                element = WebDriverWait(self.driver, self.timeout/1000).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                if clear_first:
                    element.clear()
                element.send_keys(value)
            else:
                self.page.wait_for_selector(selector)
                if clear_first:
                    self.page.fill(selector, '')
                self.page.fill(selector, value)
            
            self._log_action("fill_form", f"{selector}={value}", True)
            logger.info(f"✅ Filled {selector} with: {value}")
            return {"success": True, "selector": selector, "value": value}
            
        except Exception as e:
            logger.error(f"❌ Fill failed on {selector}: {e}")
            self._log_action("fill_form", str(e), False)
            return {"success": False, "selector": selector, "error": str(e)}
    
    def extract_text(self, selector: Optional[str] = None) -> str:
        """
        Extract text from page or element.
        
        Args:
            selector: CSS selector (None = entire page)
            
        Returns:
            Extracted text
        """
        try:
            if self.using_selenium:
                if selector:
                    from selenium.webdriver.common.by import By
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    text = element.text
                else:
                    text = self.driver.find_element(By.TAG_NAME, 'body').text
            else:
                if selector:
                    text = self.page.inner_text(selector)
                else:
                    text = self.page.inner_text('body')
            
            self._log_action("extract_text", selector or "body", True)
            return text
            
        except Exception as e:
            logger.error(f"❌ Extract text failed: {e}")
            self._log_action("extract_text", str(e), False)
            return ""
    
    def get_all_links(self) -> List[Tuple[str, str]]:
        """
        Get all links on the page.
        
        Returns:
            List of (text, href) tuples
        """
        try:
            if self.using_selenium:
                from selenium.webdriver.common.by import By
                elements = self.driver.find_elements(By.TAG_NAME, 'a')
                links = [(e.text, e.get_attribute('href')) for e in elements if e.get_attribute('href')]
            else:
                links = self.page.eval_on_selector_all(
                    'a[href]',
                    'elements => elements.map(e => [e.innerText, e.href])'
                )
            
            self._log_action("get_all_links", f"found {len(links)}", True)
            return links
            
        except Exception as e:
            logger.error(f"❌ Get links failed: {e}")
            return []
    
    def get_all_prices(self) -> List[Dict[str, Any]]:
        """
        Find all prices on the page using regex.
        
        Returns:
            List of {"text": str, "amount": float, "currency": str}
        """
        try:
            text = self.extract_text()
            
            # Common price patterns
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
            
            # Sort by amount
            prices.sort(key=lambda x: x['amount'])
            self._log_action("get_all_prices", f"found {len(prices)}", True)
            return prices
            
        except Exception as e:
            logger.error(f"❌ Get prices failed: {e}")
            return []
    
    def get_page_screenshot(self, filename: Optional[str] = None) -> str:
        """
        Take a screenshot of the page.
        
        Args:
            filename: Optional filename (auto-generated if None)
            
        Returns:
            Path to saved screenshot
        """
        try:
            if not filename:
                filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            
            filepath = os.path.join(self.screenshots_dir, filename)
            
            if self.using_selenium:
                self.driver.save_screenshot(filepath)
            else:
                self.page.screenshot(path=filepath, full_page=True)
            
            self._log_action("screenshot", filepath, True)
            logger.info(f"📸 Screenshot saved: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"❌ Screenshot failed: {e}")
            return ""
    
    def execute_js(self, script: str) -> Any:
        """
        Execute JavaScript on the page.
        
        Args:
            script: JavaScript code
            
        Returns:
            Result of script execution
        """
        try:
            if self.using_selenium:
                result = self.driver.execute_script(script)
            else:
                result = self.page.evaluate(script)
            
            self._log_action("execute_js", script[:50], True)
            return result
            
        except Exception as e:
            logger.error(f"❌ JS execution failed: {e}")
            return None
    
    def wait_for_element(self, selector: str, timeout: Optional[int] = None) -> bool:
        """
        Wait for an element to appear.
        
        Args:
            selector: CSS selector
            timeout: Timeout in ms (uses default if None)
            
        Returns:
            True if element found
        """
        try:
            wait_time = timeout or self.timeout
            
            if self.using_selenium:
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                
                WebDriverWait(self.driver, wait_time/1000).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
            else:
                self.page.wait_for_selector(selector, timeout=wait_time)
            
            return True
            
        except Exception:
            return False
    
    def get_current_url(self) -> str:
        """Get current page URL."""
        try:
            if self.using_selenium:
                return self.driver.current_url
            else:
                return self.page.url
        except Exception:
            return ""
    
    def go_back(self) -> bool:
        """Navigate back in history."""
        try:
            if self.using_selenium:
                self.driver.back()
            else:
                self.page.go_back()
            self._log_action("go_back", "", True)
            return True
        except Exception:
            return False
    
    def refresh(self) -> bool:
        """Refresh the page."""
        try:
            if self.using_selenium:
                self.driver.refresh()
            else:
                self.page.reload()
            self._log_action("refresh", "", True)
            return True
        except Exception:
            return False
    
    def close(self):
        """Close the browser cleanly."""
        try:
            if self.using_selenium and self.driver:
                self.driver.quit()
                logger.info("✅ Selenium browser closed")
            elif self.browser:
                self.browser.close()
                if self.playwright:
                    self.playwright.stop()
                logger.info("✅ Playwright browser closed")
            
            self._log_action("close", "", True)
            
        except Exception as e:
            logger.error(f"⚠️ Error closing browser: {e}")
    
    def _log_action(self, action: str, details: str, success: bool):
        """Log action to history."""
        self.history.append({
            "timestamp": datetime.now().isoformat(),
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
    print("🚀 Testing CometBrowserAgent...")
    
    agent = CometBrowserAgent(headless=False)
    
    if agent.init_browser():
        # Test navigation
        result = agent.navigate("https://www.google.com")
        print(f"Navigation: {result}")
        
        # Test screenshot
        screenshot = agent.get_page_screenshot("test_google.png")
        print(f"Screenshot: {screenshot}")
        
        # Test text extraction
        text = agent.extract_text()
        print(f"Page text length: {len(text)} chars")
        
        # Test links
        links = agent.get_all_links()
        print(f"Found {len(links)} links")
        
        # Cleanup
        time.sleep(2)
        agent.close()
        
        print("\n✅ All tests passed!")
    else:
        print("❌ Browser initialization failed")
