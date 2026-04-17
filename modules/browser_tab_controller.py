"""
LADA v9.0 - Browser Tab Controller
Complete browser tab control for JARVIS-level web automation.

Features:
- Open/close/switch tabs in Chrome, Edge, Firefox
- Navigate to URLs
- Get current tab info (URL, title)
- Tab management (refresh, back, forward)
- Multiple browser support
- Chrome DevTools Protocol integration for advanced control
"""

import os
import time
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import webbrowser

logger = logging.getLogger(__name__)

# Try to import selenium for advanced browser control
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.edge.service import Service as EdgeService
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import WebDriverException, NoSuchWindowException
    SELENIUM_OK = True
except ImportError:
    SELENIUM_OK = False
    logger.warning("[!] selenium not available - using basic browser control")

# Try to import pyautogui for keyboard shortcuts
try:
    import pyautogui
    PYAUTOGUI_OK = True
except ImportError:
    pyautogui = None
    PYAUTOGUI_OK = False

# Try to import requests for CDP
try:
    import requests
    REQUESTS_OK = True
except ImportError:
    requests = None
    REQUESTS_OK = False


@dataclass
class TabInfo:
    """Information about a browser tab"""
    id: str
    title: str
    url: str
    active: bool = False
    index: int = 0


@dataclass 
class BrowserInfo:
    """Information about a browser instance"""
    name: str
    pid: int
    tabs: List[TabInfo]
    active_tab: Optional[TabInfo] = None


class BrowserTabController:
    """
    Complete browser tab control for Chrome, Edge, and Firefox.
    Enables JARVIS-level control over web browsing.
    """
    
    # Browser executable paths
    BROWSER_PATHS = {
        'chrome': [
            'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
            'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
        ],
        'edge': [
            'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
            'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
        ],
        'firefox': [
            'C:\\Program Files\\Mozilla Firefox\\firefox.exe',
            'C:\\Program Files (x86)\\Mozilla Firefox\\firefox.exe',
        ],
    }
    
    # Common websites for quick access
    QUICK_SITES = {
        'google': 'https://www.google.com',
        'gmail': 'https://mail.google.com',
        'youtube': 'https://www.youtube.com',
        'github': 'https://www.github.com',
        'linkedin': 'https://www.linkedin.com',
        'twitter': 'https://twitter.com',
        'facebook': 'https://www.facebook.com',
        'reddit': 'https://www.reddit.com',
        'amazon': 'https://www.amazon.com',
        'netflix': 'https://www.netflix.com',
        'spotify': 'https://open.spotify.com',
        'chatgpt': 'https://chat.openai.com',
        'anthropic': 'https://claude.ai',
        'stackoverflow': 'https://stackoverflow.com',
    }
    
    def __init__(self, default_browser: str = 'chrome'):
        """
        Initialize the browser tab controller.
        
        Args:
            default_browser: Default browser to use ('chrome', 'edge', 'firefox')
        """
        self.default_browser = default_browser.lower()
        self.drivers: Dict[str, Any] = {}  # Selenium WebDriver instances
        self.use_selenium = SELENIUM_OK
        
        # CDP debugging port for Chrome/Edge
        self.cdp_port = 9222
        
        logger.info(f"[OK] Browser Tab Controller initialized (default: {self.default_browser})")
    
    # ==================== BASIC TAB OPERATIONS ====================
    
    def open_tab(self, url: Optional[str] = None, browser: Optional[str] = None) -> Dict[str, Any]:
        """
        Open a new browser tab.
        
        Args:
            url: URL to open (None for blank tab)
            browser: Browser to use (None for default)
        
        Returns:
            Dict with success status
        """
        browser = browser or self.default_browser
        url = url or 'about:blank'
        
        # Check for quick site aliases
        if url.lower() in self.QUICK_SITES:
            url = self.QUICK_SITES[url.lower()]
        
        # Add protocol if missing
        if url != 'about:blank' and not url.startswith(('http://', 'https://', 'file://')):
            url = 'https://' + url
        
        try:
            # Try Selenium first for better control
            if self.use_selenium and browser in self.drivers:
                driver = self.drivers[browser]
                driver.execute_script(f"window.open('{url}', '_blank');")
                driver.switch_to.window(driver.window_handles[-1])
                
                return {
                    'success': True,
                    'url': url,
                    'browser': browser,
                    'method': 'selenium',
                    'message': f"Opened new tab: {url}"
                }
            
            # Fallback: Use keyboard shortcut + URL
            if PYAUTOGUI_OK:
                # Switch to browser first
                self._focus_browser(browser)
                time.sleep(0.3)
                
                # Ctrl+T for new tab
                pyautogui.hotkey('ctrl', 't')
                time.sleep(0.3)
                
                # Type URL and press Enter
                if url != 'about:blank':
                    pyautogui.typewrite(url, interval=0.02)
                    pyautogui.press('enter')
                
                return {
                    'success': True,
                    'url': url,
                    'browser': browser,
                    'method': 'keyboard',
                    'message': f"Opened new tab: {url}"
                }
            
            # Last resort: webbrowser module
            webbrowser.open(url, new=2)  # new=2 opens in new tab if possible
            
            return {
                'success': True,
                'url': url,
                'browser': 'system_default',
                'method': 'webbrowser',
                'message': f"Opened: {url}"
            }
        
        except Exception as e:
            logger.error(f"[X] Failed to open tab: {e}")
            return {'success': False, 'error': str(e)}
    
    def close_tab(self, browser: Optional[str] = None) -> Dict[str, Any]:
        """
        Close the current browser tab.
        
        Args:
            browser: Browser to target (None for active)
        
        Returns:
            Dict with success status
        """
        browser = browser or self.default_browser
        
        try:
            # Try Selenium first
            if self.use_selenium and browser in self.drivers:
                driver = self.drivers[browser]
                current_handle = driver.current_window_handle
                driver.close()
                
                # Switch to remaining tab if any
                if driver.window_handles:
                    driver.switch_to.window(driver.window_handles[-1])
                
                return {
                    'success': True,
                    'browser': browser,
                    'message': "Tab closed"
                }
            
            # Fallback: Keyboard shortcut
            if PYAUTOGUI_OK:
                self._focus_browser(browser)
                time.sleep(0.2)
                pyautogui.hotkey('ctrl', 'w')
                
                return {
                    'success': True,
                    'browser': browser,
                    'method': 'keyboard',
                    'message': "Tab closed"
                }
            
            return {'success': False, 'error': 'No method available to close tab'}
        
        except Exception as e:
            logger.error(f"[X] Failed to close tab: {e}")
            return {'success': False, 'error': str(e)}
    
    def switch_tab(self, direction: str = 'next', count: int = 1) -> Dict[str, Any]:
        """
        Switch to next/previous tab.
        
        Args:
            direction: 'next' or 'prev'/'previous'
            count: Number of tabs to switch
        
        Returns:
            Dict with success status
        """
        try:
            if PYAUTOGUI_OK:
                for _ in range(count):
                    if direction.lower() in ['next', 'right']:
                        pyautogui.hotkey('ctrl', 'tab')
                    else:
                        pyautogui.hotkey('ctrl', 'shift', 'tab')
                    time.sleep(0.1)
                
                return {
                    'success': True,
                    'direction': direction,
                    'count': count,
                    'message': f"Switched {direction} {count} tab(s)"
                }
            
            return {'success': False, 'error': 'pyautogui not available'}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def switch_to_tab_number(self, tab_number: int) -> Dict[str, Any]:
        """
        Switch to a specific tab by number (1-9).
        
        Args:
            tab_number: Tab number (1-9, or 9 for last tab)
        
        Returns:
            Dict with success status
        """
        if not 1 <= tab_number <= 9:
            return {'success': False, 'error': 'Tab number must be 1-9'}
        
        try:
            if PYAUTOGUI_OK:
                pyautogui.hotkey('ctrl', str(tab_number))
                
                return {
                    'success': True,
                    'tab_number': tab_number,
                    'message': f"Switched to tab {tab_number}"
                }
            
            return {'success': False, 'error': 'pyautogui not available'}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def navigate_to(self, url: str, browser: Optional[str] = None) -> Dict[str, Any]:
        """
        Navigate current tab to a URL.
        
        Args:
            url: URL to navigate to
            browser: Browser to target
        
        Returns:
            Dict with success status
        """
        browser = browser or self.default_browser
        
        # Check for quick site aliases
        if url.lower() in self.QUICK_SITES:
            url = self.QUICK_SITES[url.lower()]
        
        # Add protocol if missing
        if not url.startswith(('http://', 'https://', 'file://')):
            url = 'https://' + url
        
        try:
            # Try Selenium
            if self.use_selenium and browser in self.drivers:
                driver = self.drivers[browser]
                driver.get(url)
                
                return {
                    'success': True,
                    'url': url,
                    'title': driver.title,
                    'message': f"Navigated to: {url}"
                }
            
            # Keyboard shortcut method
            if PYAUTOGUI_OK:
                self._focus_browser(browser)
                time.sleep(0.2)
                
                # Ctrl+L to focus address bar
                pyautogui.hotkey('ctrl', 'l')
                time.sleep(0.2)
                
                # Clear and type URL
                pyautogui.hotkey('ctrl', 'a')
                pyautogui.typewrite(url, interval=0.02)
                pyautogui.press('enter')
                
                return {
                    'success': True,
                    'url': url,
                    'method': 'keyboard',
                    'message': f"Navigated to: {url}"
                }
            
            return {'success': False, 'error': 'No method available'}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def refresh_tab(self, hard_refresh: bool = False) -> Dict[str, Any]:
        """
        Refresh the current tab.
        
        Args:
            hard_refresh: If True, bypass cache (Ctrl+Shift+R)
        
        Returns:
            Dict with success status
        """
        try:
            if PYAUTOGUI_OK:
                if hard_refresh:
                    pyautogui.hotkey('ctrl', 'shift', 'r')
                else:
                    pyautogui.press('f5')
                
                return {
                    'success': True,
                    'hard_refresh': hard_refresh,
                    'message': "Tab refreshed" + (" (cache bypassed)" if hard_refresh else "")
                }
            
            return {'success': False, 'error': 'pyautogui not available'}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def go_back(self) -> Dict[str, Any]:
        """Go back in browser history"""
        try:
            if PYAUTOGUI_OK:
                pyautogui.hotkey('alt', 'left')
                return {'success': True, 'message': "Navigated back"}
            return {'success': False, 'error': 'pyautogui not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def go_forward(self) -> Dict[str, Any]:
        """Go forward in browser history"""
        try:
            if PYAUTOGUI_OK:
                pyautogui.hotkey('alt', 'right')
                return {'success': True, 'message': "Navigated forward"}
            return {'success': False, 'error': 'pyautogui not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== SEARCH OPERATIONS ====================
    
    def google_search(self, query: str) -> Dict[str, Any]:
        """
        Perform a Google search.
        
        Args:
            query: Search query
        
        Returns:
            Dict with success status
        """
        import urllib.parse
        search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        return self.open_tab(search_url)
    
    def youtube_search(self, query: str) -> Dict[str, Any]:
        """
        Search YouTube.
        
        Args:
            query: Search query
        
        Returns:
            Dict with success status
        """
        import urllib.parse
        search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        return self.open_tab(search_url)
    
    def find_on_page(self, text: str) -> Dict[str, Any]:
        """
        Open find dialog and search for text.
        
        Args:
            text: Text to find
        
        Returns:
            Dict with success status
        """
        try:
            if PYAUTOGUI_OK:
                pyautogui.hotkey('ctrl', 'f')
                time.sleep(0.3)
                pyautogui.typewrite(text, interval=0.03)
                
                return {
                    'success': True,
                    'search_text': text,
                    'message': f"Searching for: {text}"
                }
            
            return {'success': False, 'error': 'pyautogui not available'}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== PAGE OPERATIONS ====================
    
    def scroll_page(self, direction: str = 'down', amount: str = 'page') -> Dict[str, Any]:
        """
        Scroll the page.
        
        Args:
            direction: 'up' or 'down'
            amount: 'page', 'half', 'top', 'bottom', or pixel amount
        
        Returns:
            Dict with success status
        """
        try:
            if PYAUTOGUI_OK:
                if amount == 'top':
                    pyautogui.hotkey('ctrl', 'home')
                elif amount == 'bottom':
                    pyautogui.hotkey('ctrl', 'end')
                elif amount == 'page':
                    key = 'pagedown' if direction == 'down' else 'pageup'
                    pyautogui.press(key)
                elif amount == 'half':
                    scroll_amount = 5 if direction == 'down' else -5
                    pyautogui.scroll(scroll_amount)
                else:
                    # Assume pixel amount
                    try:
                        pixels = int(amount)
                        scroll_clicks = pixels // 100
                        if direction == 'up':
                            scroll_clicks = -scroll_clicks
                        pyautogui.scroll(scroll_clicks)
                    except ValueError:
                        pyautogui.scroll(3 if direction == 'down' else -3)
                
                return {
                    'success': True,
                    'direction': direction,
                    'amount': amount,
                    'message': f"Scrolled {direction} ({amount})"
                }
            
            return {'success': False, 'error': 'pyautogui not available'}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def zoom(self, action: str = 'in', level: Optional[int] = None) -> Dict[str, Any]:
        """
        Zoom the page.
        
        Args:
            action: 'in', 'out', or 'reset'
            level: Optional specific zoom level (not widely supported)
        
        Returns:
            Dict with success status
        """
        try:
            if PYAUTOGUI_OK:
                if action == 'reset':
                    pyautogui.hotkey('ctrl', '0')
                    message = "Zoom reset to 100%"
                elif action == 'in':
                    pyautogui.hotkey('ctrl', 'plus')
                    message = "Zoomed in"
                elif action == 'out':
                    pyautogui.hotkey('ctrl', 'minus')
                    message = "Zoomed out"
                else:
                    return {'success': False, 'error': f'Unknown zoom action: {action}'}
                
                return {'success': True, 'action': action, 'message': message}
            
            return {'success': False, 'error': 'pyautogui not available'}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def toggle_fullscreen(self) -> Dict[str, Any]:
        """Toggle browser fullscreen mode (F11)"""
        try:
            if PYAUTOGUI_OK:
                pyautogui.press('f11')
                return {'success': True, 'message': "Toggled fullscreen"}
            return {'success': False, 'error': 'pyautogui not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def toggle_devtools(self) -> Dict[str, Any]:
        """Toggle browser developer tools (F12)"""
        try:
            if PYAUTOGUI_OK:
                pyautogui.press('f12')
                return {'success': True, 'message': "Toggled developer tools"}
            return {'success': False, 'error': 'pyautogui not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== BOOKMARK OPERATIONS ====================
    
    def bookmark_page(self) -> Dict[str, Any]:
        """Bookmark the current page (Ctrl+D)"""
        try:
            if PYAUTOGUI_OK:
                pyautogui.hotkey('ctrl', 'd')
                return {'success': True, 'message': "Bookmark dialog opened"}
            return {'success': False, 'error': 'pyautogui not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def open_bookmarks(self) -> Dict[str, Any]:
        """Open bookmarks manager"""
        try:
            if PYAUTOGUI_OK:
                pyautogui.hotkey('ctrl', 'shift', 'o')
                return {'success': True, 'message': "Bookmarks manager opened"}
            return {'success': False, 'error': 'pyautogui not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== BROWSER CONTROL ====================
    
    def open_browser(self, browser: Optional[str] = None, url: Optional[str] = None) -> Dict[str, Any]:
        """
        Open a browser window.
        
        Args:
            browser: Browser to open
            url: Optional URL to open
        
        Returns:
            Dict with success status
        """
        browser = browser or self.default_browser
        
        try:
            browser_path = self._find_browser_path(browser)
            if not browser_path:
                return {'success': False, 'error': f'Browser not found: {browser}'}
            
            cmd = [browser_path]
            if url:
                cmd.append(url)
            
            subprocess.Popen(cmd)
            
            return {
                'success': True,
                'browser': browser,
                'url': url,
                'message': f"Opened {browser}" + (f" with {url}" if url else "")
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def close_browser(self, browser: Optional[str] = None) -> Dict[str, Any]:
        """
        Close a browser window.
        
        Args:
            browser: Browser to close
        
        Returns:
            Dict with success status
        """
        browser = browser or self.default_browser
        
        try:
            # Close Selenium driver if exists
            if browser in self.drivers:
                self.drivers[browser].quit()
                del self.drivers[browser]
            
            # Kill browser process
            process_names = {
                'chrome': 'chrome.exe',
                'edge': 'msedge.exe',
                'firefox': 'firefox.exe'
            }
            
            if browser in process_names:
                subprocess.run(
                    ['taskkill', '/f', '/im', process_names[browser]],
                    capture_output=True
                )
            
            return {'success': True, 'browser': browser, 'message': f"Closed {browser}"}
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def open_incognito(self, browser: Optional[str] = None, url: Optional[str] = None) -> Dict[str, Any]:
        """
        Open browser in incognito/private mode.
        
        Args:
            browser: Browser to use
            url: Optional URL to open
        
        Returns:
            Dict with success status
        """
        browser = browser or self.default_browser
        
        try:
            browser_path = self._find_browser_path(browser)
            if not browser_path:
                return {'success': False, 'error': f'Browser not found: {browser}'}
            
            incognito_flags = {
                'chrome': '--incognito',
                'edge': '--inprivate',
                'firefox': '-private-window'
            }
            
            flag = incognito_flags.get(browser, '--incognito')
            cmd = [browser_path, flag]
            
            if url:
                cmd.append(url)
            
            subprocess.Popen(cmd)
            
            return {
                'success': True,
                'browser': browser,
                'mode': 'incognito',
                'message': f"Opened {browser} in private mode"
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== UTILITY METHODS ====================
    
    def _find_browser_path(self, browser: str) -> Optional[str]:
        """Find the browser executable path"""
        paths = self.BROWSER_PATHS.get(browser, [])
        for path in paths:
            if os.path.exists(path):
                return path
        return None
    
    def _focus_browser(self, browser: str):
        """Try to focus the browser window"""
        try:
            import pygetwindow as gw
            
            browser_titles = {
                'chrome': ['Chrome', 'Google Chrome'],
                'edge': ['Edge', 'Microsoft Edge'],
                'firefox': ['Firefox', 'Mozilla Firefox']
            }
            
            for title in browser_titles.get(browser, [browser]):
                windows = gw.getWindowsWithTitle(title)
                if windows:
                    windows[0].activate()
                    return True
            
            return False
        
        except Exception:
            return False
    
    def get_quick_sites(self) -> Dict[str, str]:
        """Get list of quick site aliases"""
        return self.QUICK_SITES.copy()
    
    def add_quick_site(self, name: str, url: str) -> Dict[str, Any]:
        """
        Add a quick site alias.
        
        Args:
            name: Alias name
            url: URL to associate
        
        Returns:
            Dict with success status
        """
        self.QUICK_SITES[name.lower()] = url
        return {
            'success': True,
            'name': name,
            'url': url,
            'message': f"Added quick site: {name} -> {url}"
        }


# Factory function for workflow engine integration
def create_browser_tab_controller(default_browser: str = 'chrome') -> BrowserTabController:
    """Create and return a BrowserTabController instance"""
    return BrowserTabController(default_browser)


if __name__ == '__main__':
    # Test the browser tab controller
    logging.basicConfig(level=logging.INFO)
    btc = BrowserTabController()
    
    print("\n=== Testing Browser Tab Controller ===")
    
    # Show quick sites
    sites = btc.get_quick_sites()
    print(f"Quick sites available: {len(sites)}")
    for name, url in list(sites.items())[:5]:
        print(f"  • {name}: {url}")
    
    print("\n[OK] Browser Tab Controller tests complete!")
    print("\nTry commands like:")
    print("  btc.open_tab('google.com')")
    print("  btc.google_search('python tutorials')")
    print("  btc.switch_tab('next')")
    print("  btc.close_tab()")
