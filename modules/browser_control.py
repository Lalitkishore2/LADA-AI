"""
Browser Control Module for LADA v5.0
Handles web browsing, searches, and browser automation
"""

import webbrowser
import subprocess
import time
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger('BrowserControl')

class BrowserControl:
    """Control web browser programmatically"""
    
    # Common browser paths (Windows)
    BROWSERS = {
        'chrome': [
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        ],
        'firefox': [
            r'C:\Program Files\Mozilla Firefox\firefox.exe',
            r'C:\Program Files (x86)\Mozilla Firefox\firefox.exe',
        ],
        'edge': [
            r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
            r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        ],
        'ie': [
            r'C:\Program Files\Internet Explorer\iexplore.exe',
            r'C:\Program Files (x86)\Internet Explorer\iexplore.exe',
        ]
    }
    
    @staticmethod
    def find_browser(browser_name: str = 'chrome') -> Optional[str]:
        """Find browser executable path"""
        paths = BrowserControl.BROWSERS.get(browser_name.lower(), [])
        
        for path in paths:
            if Path(path).exists():
                logger.debug(f"Found {browser_name} at: {path}")
                return path
        
        logger.warning(f"Browser {browser_name} not found in common locations")
        return None
    
    @staticmethod
    def open_browser(browser_name: str = 'chrome', url: str = 'https://google.com') -> bool:
        """Open browser and navigate to URL"""
        browser_path = BrowserControl.find_browser(browser_name)
        
        if not browser_path:
            # Fallback to webbrowser module
            logger.warning(f"Using fallback browser for {browser_name}")
            try:
                webbrowser.open(url)
                logger.info(f"[OK] Opened {browser_name} -> {url}")
                return True
            except:
                logger.error(f"[FAIL] Could not open {browser_name}")
                return False
        
        try:
            subprocess.Popen([browser_path, url])
            logger.info(f"[OK] Opened {browser_name} -> {url}")
            return True
        except Exception as e:
            logger.error(f"[FAIL] Could not open {browser_name}: {e}")
            return False
    
    @staticmethod
    def google_search(query: str) -> bool:
        """Perform Google search"""
        try:
            # Encode query for URL
            safe_query = query.replace(' ', '+')
            url = f'https://www.google.com/search?q={safe_query}'
            webbrowser.open(url)
            logger.info(f"[OK] Google search: {query}")
            return True
        except Exception as e:
            logger.error(f"[FAIL] Google search failed: {e}")
            return False
    
    @staticmethod
    def open_youtube(search: str = '') -> bool:
        """Open YouTube or search on YouTube"""
        try:
            if search:
                safe_query = search.replace(' ', '+')
                url = f'https://www.youtube.com/results?search_query={safe_query}'
            else:
                url = 'https://www.youtube.com'
            
            webbrowser.open(url)
            logger.info(f"[OK] YouTube: {search or 'home'}")
            return True
        except Exception as e:
            logger.error(f"[FAIL] YouTube failed: {e}")
            return False
    
    @staticmethod
    def open_website(url: str) -> bool:
        """Open any website"""
        try:
            if not url.startswith('http'):
                url = 'https://' + url
            
            webbrowser.open(url)
            logger.info(f"[OK] Opened: {url}")
            return True
        except Exception as e:
            logger.error(f"[FAIL] Could not open {url}: {e}")
            return False
    
    @staticmethod
    def open_github(username: str = '') -> bool:
        """Open GitHub profile or GitHub home"""
        try:
            if username:
                url = f'https://github.com/{username}'
            else:
                url = 'https://github.com'
            
            webbrowser.open(url)
            logger.info(f"[OK] GitHub: {username or 'home'}")
            return True
        except:
            return False
    
    @staticmethod
    def open_stackoverflow(query: str = '') -> bool:
        """Search Stack Overflow"""
        try:
            if query:
                safe_query = query.replace(' ', '+')
                url = f'https://stackoverflow.com/search?q={safe_query}'
            else:
                url = 'https://stackoverflow.com'
            
            webbrowser.open(url)
            logger.info(f"[OK] Stack Overflow: {query or 'home'}")
            return True
        except:
            return False
    
    @staticmethod
    def open_documentation(language: str = 'python') -> bool:
        """Open language documentation"""
        docs = {
            'python': 'https://docs.python.org/3/',
            'javascript': 'https://developer.mozilla.org/en-US/docs/Web/JavaScript',
            'html': 'https://developer.mozilla.org/en-US/docs/Web/HTML',
            'css': 'https://developer.mozilla.org/en-US/docs/Web/CSS',
            'react': 'https://react.dev',
            'django': 'https://docs.djangoproject.com/',
            'flask': 'https://flask.palletsprojects.com/',
            'nodejs': 'https://nodejs.org/en/docs/',
        }
        
        url = docs.get(language.lower())
        if url:
            webbrowser.open(url)
            logger.info(f"[OK] {language} docs opened")
            return True
        
        logger.warning(f"Documentation not found for: {language}")
        return False
    
    @staticmethod
    def get_browser_recommendation() -> str:
        """Recommend available browser"""
        for browser in ['chrome', 'firefox', 'edge']:
            if BrowserControl.find_browser(browser):
                return browser
        return 'chrome'  # Default fallback
    
    @staticmethod
    def web_search(query: str, num_results: int = 5) -> dict:
        """
        Perform a web search and return results (not just open browser)
        Uses DuckDuckGo Instant Answer API for quick answers
        
        Args:
            query: Search query
            num_results: Number of results to return
            
        Returns:
            {'success': True/False, 'answer': '...', 'results': [...]}
        """
        import requests
        
        try:
            # Try DuckDuckGo Instant Answer API first (no API key needed)
            ddg_url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1"
            response = requests.get(ddg_url, timeout=10)
            data = response.json()
            
            result = {
                'success': True,
                'query': query,
                'answer': None,
                'abstract': None,
                'results': []
            }
            
            # Check for instant answer
            if data.get('Answer'):
                result['answer'] = data['Answer']
            
            # Check for abstract
            if data.get('Abstract'):
                result['abstract'] = data['Abstract']
                result['source'] = data.get('AbstractSource', 'Unknown')
                result['source_url'] = data.get('AbstractURL', '')
            
            # Get related topics as results
            for topic in data.get('RelatedTopics', [])[:num_results]:
                if isinstance(topic, dict) and topic.get('Text'):
                    result['results'].append({
                        'text': topic.get('Text', ''),
                        'url': topic.get('FirstURL', '')
                    })
            
            return result
            
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'query': query
            }
    
    @staticmethod
    def search_and_summarize(query: str) -> str:
        """
        Search and return a formatted summary string
        Good for AI to use for answering questions
        """
        result = BrowserControl.web_search(query)
        
        if not result.get('success'):
            return f"Couldn't search for: {query}"
        
        parts = []
        
        if result.get('answer'):
            parts.append(f"Answer: {result['answer']}")
        
        if result.get('abstract'):
            parts.append(f"Summary: {result['abstract']}")
            if result.get('source'):
                parts.append(f"Source: {result['source']}")
        
        if result.get('results'):
            parts.append("Related:")
            for r in result['results'][:3]:
                parts.append(f"- {r['text'][:200]}")
        
        if not parts:
            return f"No instant results found for: {query}. Try a web search."
        
        return "\n".join(parts)


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Examples:
    # BrowserControl.open_browser('chrome', 'https://github.com')
    # BrowserControl.google_search('python machine learning')
    # BrowserControl.open_youtube('machine learning tutorial')
    # BrowserControl.open_github('your-username')
    # BrowserControl.open_documentation('python')
    
    print("Browser Control module loaded successfully")
