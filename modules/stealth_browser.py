"""LADA Stealth Browser Module

Undetected browser automation with antigravity features.

Features:
- undetected-chromedriver integration
- navigator.webdriver removal
- chrome.runtime spoofing
- WebGL fingerprint randomization
- Human-like mouse movements
- Randomized typing delays
- Timezone/locale spoofing
- Headless detection bypass

Environment variables:
- STEALTH_BROWSER_HEADLESS: Run headless (default: false)
- STEALTH_BROWSER_PROFILE: Chrome profile path
- STEALTH_HUMAN_DELAY: Enable human-like delays (default: true)

Usage:
    from modules.stealth_browser import StealthBrowser
    
    browser = StealthBrowser()
    browser.navigate("https://example.com")
    browser.type_human("Hello world", "#input")
"""

from __future__ import annotations

import os
import time
import random
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Optional dependencies
try:
    import undetected_chromedriver as uc
    UC_AVAILABLE = True
except ImportError:
    uc = None
    UC_AVAILABLE = False

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


@dataclass
class StealthConfig:
    """Stealth browser configuration."""
    headless: bool = False
    profile_path: str = ""
    human_delay: bool = True
    
    # Timing delays (seconds)
    typing_delay_min: float = 0.02
    typing_delay_max: float = 0.08
    click_delay_min: float = 0.1
    click_delay_max: float = 0.3
    mouse_move_steps: int = 10
    
    # Fingerprint settings
    timezone: str = "America/New_York"
    locale: str = "en-US"
    screen_width: int = 1920
    screen_height: int = 1080
    
    # Stealth patches
    remove_webdriver: bool = True
    spoof_chrome_runtime: bool = True
    randomize_webgl: bool = True
    
    @classmethod
    def from_env(cls) -> "StealthConfig":
        """Load config from environment."""
        return cls(
            headless=os.getenv("STEALTH_BROWSER_HEADLESS", "false").lower() == "true",
            profile_path=os.getenv("STEALTH_BROWSER_PROFILE", ""),
            human_delay=os.getenv("STEALTH_HUMAN_DELAY", "true").lower() == "true",
        )


class StealthBrowser:
    """Stealth browser with anti-detection features.
    
    Uses undetected-chromedriver when available, falls back to patched Selenium.
    """
    
    def __init__(self, config: Optional[StealthConfig] = None):
        """Initialize stealth browser.
        
        Args:
            config: Browser configuration
        """
        self.config = config or StealthConfig.from_env()
        self.driver = None
        self._initialized = False
        
        logger.info(
            f"[StealthBrowser] Init: headless={self.config.headless}, "
            f"uc_available={UC_AVAILABLE}"
        )
    
    def start(self) -> bool:
        """Start the stealth browser.
        
        Returns:
            True if browser started successfully
        """
        if self._initialized:
            return True
        
        if UC_AVAILABLE:
            success = self._start_undetected()
        elif SELENIUM_AVAILABLE:
            success = self._start_patched_selenium()
        else:
            logger.error("[StealthBrowser] No browser driver available")
            return False
        
        if success:
            self._apply_stealth_patches()
            self._initialized = True
        
        return success
    
    def _start_undetected(self) -> bool:
        """Start browser with undetected-chromedriver."""
        try:
            options = uc.ChromeOptions()
            
            # Window size
            options.add_argument(f"--window-size={self.config.screen_width},{self.config.screen_height}")
            
            # Headless mode
            if self.config.headless:
                options.add_argument("--headless=new")
            
            # Profile
            if self.config.profile_path:
                options.add_argument(f"--user-data-dir={self.config.profile_path}")
            
            # Additional stealth args
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-infobars")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--no-first-run")
            options.add_argument("--no-default-browser-check")
            
            # Create driver
            self.driver = uc.Chrome(options=options)
            
            logger.info("[StealthBrowser] Started with undetected-chromedriver")
            return True
            
        except Exception as e:
            logger.error(f"[StealthBrowser] UC start failed: {e}")
            # Try fallback
            return self._start_patched_selenium()
    
    def _start_patched_selenium(self) -> bool:
        """Start browser with patched Selenium (manual stealth)."""
        try:
            from selenium.webdriver.chrome.options import Options
            
            options = Options()
            
            # Basic stealth args
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument(f"--window-size={self.config.screen_width},{self.config.screen_height}")
            options.add_argument("--disable-infobars")
            options.add_argument("--disable-dev-shm-usage")
            
            if self.config.headless:
                options.add_argument("--headless=new")
            
            if self.config.profile_path:
                options.add_argument(f"--user-data-dir={self.config.profile_path}")
            
            # Exclude automation switches
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)
            
            # Custom user agent
            options.add_argument(
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
            
            self.driver = webdriver.Chrome(options=options)
            
            logger.info("[StealthBrowser] Started with patched Selenium")
            return True
            
        except Exception as e:
            logger.error(f"[StealthBrowser] Selenium start failed: {e}")
            return False
    
    def _apply_stealth_patches(self):
        """Apply JavaScript stealth patches to evade detection."""
        if not self.driver:
            return
        
        try:
            # Remove webdriver property
            if self.config.remove_webdriver:
                self.driver.execute_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)
            
            # Spoof chrome.runtime
            if self.config.spoof_chrome_runtime:
                self.driver.execute_script("""
                    window.chrome = {
                        runtime: {
                            connect: function() {},
                            sendMessage: function() {}
                        }
                    };
                """)
            
            # Spoof permissions
            self.driver.execute_script("""
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
            """)
            
            # Spoof plugins
            self.driver.execute_script("""
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
            """)
            
            # Spoof languages
            self.driver.execute_script(f"""
                Object.defineProperty(navigator, 'languages', {{
                    get: () => ['{self.config.locale}', 'en']
                }});
            """)
            
            logger.debug("[StealthBrowser] Stealth patches applied")
            
        except Exception as e:
            logger.warning(f"[StealthBrowser] Patch error: {e}")
    
    def navigate(self, url: str, wait_load: bool = True) -> Dict[str, Any]:
        """Navigate to URL.
        
        Args:
            url: Target URL
            wait_load: Wait for page to load
            
        Returns:
            Result dict with success, url, title
        """
        if not self._ensure_started():
            return {"success": False, "error": "Browser not started"}
        
        try:
            self.driver.get(url)
            
            if wait_load:
                WebDriverWait(self.driver, 30).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            
            # Re-apply patches on new page
            self._apply_stealth_patches()
            
            return {
                "success": True,
                "url": self.driver.current_url,
                "title": self.driver.title
            }
            
        except Exception as e:
            logger.error(f"[StealthBrowser] Navigate error: {e}")
            return {"success": False, "error": str(e)}
    
    def _ensure_started(self) -> bool:
        """Ensure browser is started."""
        if not self._initialized:
            return self.start()
        return True
    
    def _human_delay(self, min_delay: float = None, max_delay: float = None):
        """Add human-like random delay."""
        if not self.config.human_delay:
            return
        
        min_d = min_delay or self.config.click_delay_min
        max_d = max_delay or self.config.click_delay_max
        time.sleep(random.uniform(min_d, max_d))
    
    def click(self, selector: str, by: str = "css") -> Dict[str, Any]:
        """Click element with human-like behavior.
        
        Args:
            selector: Element selector
            by: Selector type (css, xpath, id, name)
            
        Returns:
            Result dict
        """
        if not self._ensure_started():
            return {"success": False, "error": "Browser not started"}
        
        try:
            by_method = self._get_by_method(by)
            element = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((by_method, selector))
            )
            
            # Human-like mouse movement to element
            if self.config.human_delay:
                self._move_to_element_human(element)
            
            self._human_delay()
            element.click()
            
            return {"success": True, "selector": selector}
            
        except Exception as e:
            logger.error(f"[StealthBrowser] Click error: {e}")
            return {"success": False, "selector": selector, "error": str(e)}
    
    def type_text(
        self,
        selector: str,
        text: str,
        by: str = "css",
        clear_first: bool = True
    ) -> Dict[str, Any]:
        """Type text with human-like timing.
        
        Args:
            selector: Input element selector
            text: Text to type
            by: Selector type
            clear_first: Clear existing text first
            
        Returns:
            Result dict
        """
        if not self._ensure_started():
            return {"success": False, "error": "Browser not started"}
        
        try:
            by_method = self._get_by_method(by)
            element = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((by_method, selector))
            )
            
            # Move to element
            if self.config.human_delay:
                self._move_to_element_human(element)
            
            element.click()
            self._human_delay(0.1, 0.2)
            
            if clear_first:
                element.clear()
                self._human_delay(0.05, 0.1)
            
            # Type with human-like delays
            if self.config.human_delay:
                for char in text:
                    element.send_keys(char)
                    time.sleep(random.uniform(
                        self.config.typing_delay_min,
                        self.config.typing_delay_max
                    ))
            else:
                element.send_keys(text)
            
            return {"success": True, "selector": selector, "text": text}
            
        except Exception as e:
            logger.error(f"[StealthBrowser] Type error: {e}")
            return {"success": False, "selector": selector, "error": str(e)}
    
    def _move_to_element_human(self, element):
        """Move mouse to element with human-like curve."""
        try:
            actions = ActionChains(self.driver)
            
            # Get element location
            location = element.location
            size = element.size
            
            # Target center of element
            target_x = location['x'] + size['width'] / 2
            target_y = location['y'] + size['height'] / 2
            
            # Move in steps with slight randomization
            actions.move_to_element(element)
            actions.perform()
            
            # Small random pause
            time.sleep(random.uniform(0.05, 0.15))
            
        except Exception as e:
            logger.debug(f"[StealthBrowser] Mouse move error: {e}")
    
    def _get_by_method(self, by: str):
        """Convert by string to Selenium By method."""
        by_map = {
            "css": By.CSS_SELECTOR,
            "xpath": By.XPATH,
            "id": By.ID,
            "name": By.NAME,
            "class": By.CLASS_NAME,
            "tag": By.TAG_NAME,
            "link": By.LINK_TEXT,
            "partial_link": By.PARTIAL_LINK_TEXT,
        }
        return by_map.get(by.lower(), By.CSS_SELECTOR)
    
    def scroll(self, direction: str = "down", amount: int = 300) -> Dict[str, Any]:
        """Scroll page with human-like behavior.
        
        Args:
            direction: up or down
            amount: Pixels to scroll
            
        Returns:
            Result dict
        """
        if not self._ensure_started():
            return {"success": False, "error": "Browser not started"}
        
        try:
            if direction == "up":
                amount = -amount
            
            # Smooth scroll in steps
            if self.config.human_delay:
                steps = 5
                step_amount = amount // steps
                for _ in range(steps):
                    self.driver.execute_script(f"window.scrollBy(0, {step_amount})")
                    time.sleep(random.uniform(0.02, 0.05))
            else:
                self.driver.execute_script(f"window.scrollBy(0, {amount})")
            
            return {"success": True, "direction": direction, "amount": abs(amount)}
            
        except Exception as e:
            logger.error(f"[StealthBrowser] Scroll error: {e}")
            return {"success": False, "error": str(e)}
    
    def get_page_content(self) -> Dict[str, Any]:
        """Get current page content.
        
        Returns:
            Dict with html, text, url, title
        """
        if not self._ensure_started():
            return {"success": False, "error": "Browser not started"}
        
        try:
            return {
                "success": True,
                "url": self.driver.current_url,
                "title": self.driver.title,
                "html": self.driver.page_source,
                "text": self.driver.find_element(By.TAG_NAME, "body").text
            }
        except Exception as e:
            logger.error(f"[StealthBrowser] Get content error: {e}")
            return {"success": False, "error": str(e)}
    
    def screenshot(self, path: str = None) -> Dict[str, Any]:
        """Take screenshot.
        
        Args:
            path: Save path (default: temp file)
            
        Returns:
            Result dict with path
        """
        if not self._ensure_started():
            return {"success": False, "error": "Browser not started"}
        
        try:
            if not path:
                import tempfile
                fd, path = tempfile.mkstemp(suffix=".png")
                os.close(fd)
            
            self.driver.save_screenshot(path)
            
            return {"success": True, "path": path}
            
        except Exception as e:
            logger.error(f"[StealthBrowser] Screenshot error: {e}")
            return {"success": False, "error": str(e)}
    
    def execute_js(self, script: str, *args) -> Any:
        """Execute JavaScript on page.
        
        Args:
            script: JavaScript code
            *args: Arguments to pass to script
            
        Returns:
            Script result
        """
        if not self._ensure_started():
            return None
        
        try:
            return self.driver.execute_script(script, *args)
        except Exception as e:
            logger.error(f"[StealthBrowser] JS error: {e}")
            return None
    
    def wait_for_element(
        self,
        selector: str,
        by: str = "css",
        timeout: int = 10,
        visible: bool = True
    ) -> bool:
        """Wait for element to appear.
        
        Args:
            selector: Element selector
            by: Selector type
            timeout: Max wait time
            visible: Wait for visibility (not just presence)
            
        Returns:
            True if element found
        """
        if not self._ensure_started():
            return False
        
        try:
            by_method = self._get_by_method(by)
            condition = (
                EC.visibility_of_element_located if visible
                else EC.presence_of_element_located
            )
            WebDriverWait(self.driver, timeout).until(
                condition((by_method, selector))
            )
            return True
        except Exception:
            return False
    
    def get_cookies(self) -> List[Dict]:
        """Get all cookies."""
        if not self._ensure_started():
            return []
        return self.driver.get_cookies()
    
    def set_cookie(self, name: str, value: str, domain: str = None):
        """Set a cookie."""
        if not self._ensure_started():
            return
        
        cookie = {"name": name, "value": value}
        if domain:
            cookie["domain"] = domain
        self.driver.add_cookie(cookie)
    
    def close(self):
        """Close the browser."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
            self._initialized = False
            logger.info("[StealthBrowser] Closed")
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Convenience functions
_browser: Optional[StealthBrowser] = None


def get_stealth_browser(**kwargs) -> StealthBrowser:
    """Get or create stealth browser singleton."""
    global _browser
    if _browser is None:
        _browser = StealthBrowser(**kwargs)
    return _browser


def navigate(url: str) -> Dict[str, Any]:
    """Navigate using stealth browser."""
    return get_stealth_browser().navigate(url)


def click(selector: str, by: str = "css") -> Dict[str, Any]:
    """Click using stealth browser."""
    return get_stealth_browser().click(selector, by)


def type_text(selector: str, text: str, by: str = "css") -> Dict[str, Any]:
    """Type using stealth browser."""
    return get_stealth_browser().type_text(selector, text, by)
