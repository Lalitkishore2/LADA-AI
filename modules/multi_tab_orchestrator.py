"""
LADA v9.0 - Multi-Tab Orchestrator
Orchestrate multiple browser tabs simultaneously for JARVIS-level automation.

Features:
- Manage multiple tabs across browsers
- Parallel operations on multiple tabs
- Tab groups and workspaces
- Save and restore tab sessions
- Monitor tab states
- Cross-tab data extraction
"""

import os
import time
import json
import logging
import threading
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
import concurrent.futures

logger = logging.getLogger(__name__)

# Try to import browser tab controller
try:
    from modules.browser_tab_controller import BrowserTabController, TabInfo
    BROWSER_TAB_OK = True
except ImportError:
    try:
        from browser_tab_controller import BrowserTabController, TabInfo
        BROWSER_TAB_OK = True
    except ImportError:
        BrowserTabController = None
        TabInfo = None
        BROWSER_TAB_OK = False


@dataclass
class TabGroup:
    """A group of related tabs"""
    name: str
    tabs: List[Dict[str, str]]  # List of {url, title}
    created: datetime = field(default_factory=datetime.now)
    color: str = 'blue'
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'tabs': self.tabs,
            'created': self.created.isoformat(),
            'color': self.color
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TabGroup':
        return cls(
            name=data['name'],
            tabs=data['tabs'],
            created=datetime.fromisoformat(data['created']),
            color=data.get('color', 'blue')
        )


@dataclass
class TabSession:
    """A saved browser session with multiple tabs"""
    name: str
    groups: List[TabGroup]
    created: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'groups': [g.to_dict() for g in self.groups],
            'created': self.created.isoformat(),
            'last_used': self.last_used.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TabSession':
        return cls(
            name=data['name'],
            groups=[TabGroup.from_dict(g) for g in data['groups']],
            created=datetime.fromisoformat(data['created']),
            last_used=datetime.fromisoformat(data['last_used'])
        )


class MultiTabOrchestrator:
    """
    Orchestrate multiple browser tabs for complex web automation.
    Enables JARVIS-level control over multiple web pages simultaneously.
    """
    
    # Predefined workspace templates
    WORKSPACE_TEMPLATES = {
        'research': {
            'name': 'Research',
            'tabs': [
                {'url': 'https://www.google.com', 'title': 'Google Search'},
                {'url': 'https://scholar.google.com', 'title': 'Google Scholar'},
                {'url': 'https://www.wikipedia.org', 'title': 'Wikipedia'},
            ]
        },
        'development': {
            'name': 'Development',
            'tabs': [
                {'url': 'https://github.com', 'title': 'GitHub'},
                {'url': 'https://stackoverflow.com', 'title': 'Stack Overflow'},
                {'url': 'https://docs.python.org', 'title': 'Python Docs'},
            ]
        },
        'social': {
            'name': 'Social Media',
            'tabs': [
                {'url': 'https://twitter.com', 'title': 'Twitter'},
                {'url': 'https://linkedin.com', 'title': 'LinkedIn'},
                {'url': 'https://reddit.com', 'title': 'Reddit'},
            ]
        },
        'productivity': {
            'name': 'Productivity',
            'tabs': [
                {'url': 'https://mail.google.com', 'title': 'Gmail'},
                {'url': 'https://calendar.google.com', 'title': 'Calendar'},
                {'url': 'https://drive.google.com', 'title': 'Drive'},
            ]
        },
        'entertainment': {
            'name': 'Entertainment',
            'tabs': [
                {'url': 'https://www.youtube.com', 'title': 'YouTube'},
                {'url': 'https://www.netflix.com', 'title': 'Netflix'},
                {'url': 'https://open.spotify.com', 'title': 'Spotify'},
            ]
        },
    }
    
    def __init__(self, default_browser: str = 'chrome'):
        """
        Initialize the multi-tab orchestrator.
        
        Args:
            default_browser: Default browser to use
        """
        self.default_browser = default_browser
        self.tab_controller = BrowserTabController(default_browser) if BROWSER_TAB_OK else None
        
        # Session storage
        self.sessions_dir = Path("data/tab_sessions")
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        
        # Current groups
        self.active_groups: Dict[str, TabGroup] = {}
        
        # Load saved sessions
        self.saved_sessions: Dict[str, TabSession] = {}
        self._load_sessions()
        
        logger.info("[OK] Multi-Tab Orchestrator initialized")
    
    # ==================== TAB GROUP OPERATIONS ====================
    
    def create_group(self, name: str, urls: List[str], 
                     open_now: bool = True) -> Dict[str, Any]:
        """
        Create a new tab group.
        
        Args:
            name: Group name
            urls: List of URLs to include
            open_now: Whether to open tabs immediately
        
        Returns:
            Dict with success status
        """
        try:
            tabs = [{'url': url, 'title': url.split('//')[-1].split('/')[0]} for url in urls]
            group = TabGroup(name=name, tabs=tabs)
            self.active_groups[name] = group
            
            if open_now and self.tab_controller:
                opened = 0
                for url in urls:
                    result = self.tab_controller.open_tab(url)
                    if result.get('success'):
                        opened += 1
                    time.sleep(0.3)
                
                return {
                    'success': True,
                    'group_name': name,
                    'tabs_opened': opened,
                    'total_tabs': len(urls),
                    'message': f"Created group '{name}' with {opened} tabs"
                }
            
            return {
                'success': True,
                'group_name': name,
                'tabs_count': len(urls),
                'message': f"Created group '{name}' (not opened)"
            }
        
        except Exception as e:
            logger.error(f"[X] Failed to create group: {e}")
            return {'success': False, 'error': str(e)}
    
    def open_group(self, name: str) -> Dict[str, Any]:
        """
        Open all tabs in a group.
        
        Args:
            name: Group name
        
        Returns:
            Dict with success status
        """
        if name not in self.active_groups:
            return {'success': False, 'error': f"Group '{name}' not found"}
        
        group = self.active_groups[name]
        
        if not self.tab_controller:
            return {'success': False, 'error': 'Tab controller not available'}
        
        opened = 0
        for tab in group.tabs:
            result = self.tab_controller.open_tab(tab['url'])
            if result.get('success'):
                opened += 1
            time.sleep(0.3)
        
        return {
            'success': True,
            'group_name': name,
            'tabs_opened': opened,
            'message': f"Opened {opened} tabs from group '{name}'"
        }
    
    def close_group(self, name: str) -> Dict[str, Any]:
        """
        Close all tabs in a group (removes from active groups).
        
        Args:
            name: Group name
        
        Returns:
            Dict with success status
        """
        if name in self.active_groups:
            del self.active_groups[name]
            return {
                'success': True,
                'group_name': name,
                'message': f"Closed group '{name}'"
            }
        
        return {'success': False, 'error': f"Group '{name}' not found"}
    
    def list_groups(self) -> Dict[str, Any]:
        """List all active tab groups"""
        groups = []
        for name, group in self.active_groups.items():
            groups.append({
                'name': name,
                'tabs_count': len(group.tabs),
                'color': group.color,
                'created': group.created.isoformat()
            })
        
        return {
            'success': True,
            'groups': groups,
            'count': len(groups)
        }
    
    # ==================== WORKSPACE TEMPLATES ====================
    
    def open_workspace(self, template_name: str) -> Dict[str, Any]:
        """
        Open a predefined workspace template.
        
        Args:
            template_name: Name of the workspace template
        
        Returns:
            Dict with success status
        """
        template_name = template_name.lower()
        
        if template_name not in self.WORKSPACE_TEMPLATES:
            available = ', '.join(self.WORKSPACE_TEMPLATES.keys())
            return {
                'success': False,
                'error': f"Unknown workspace: {template_name}. Available: {available}"
            }
        
        template = self.WORKSPACE_TEMPLATES[template_name]
        urls = [tab['url'] for tab in template['tabs']]
        
        return self.create_group(template['name'], urls, open_now=True)
    
    def list_workspaces(self) -> Dict[str, Any]:
        """List available workspace templates"""
        workspaces = []
        for name, template in self.WORKSPACE_TEMPLATES.items():
            workspaces.append({
                'name': name,
                'display_name': template['name'],
                'tabs_count': len(template['tabs']),
                'tabs': [t['title'] for t in template['tabs']]
            })
        
        return {
            'success': True,
            'workspaces': workspaces,
            'count': len(workspaces)
        }
    
    def add_workspace_template(self, name: str, display_name: str, 
                               tabs: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Add a custom workspace template.
        
        Args:
            name: Template key name
            display_name: Display name
            tabs: List of {url, title} dicts
        
        Returns:
            Dict with success status
        """
        self.WORKSPACE_TEMPLATES[name.lower()] = {
            'name': display_name,
            'tabs': tabs
        }
        
        return {
            'success': True,
            'name': name,
            'tabs_count': len(tabs),
            'message': f"Added workspace template: {display_name}"
        }
    
    # ==================== SESSION MANAGEMENT ====================
    
    def save_session(self, name: str, groups: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Save current tab groups as a session.
        
        Args:
            name: Session name
            groups: Specific groups to save (None for all)
        
        Returns:
            Dict with success status
        """
        try:
            if groups:
                session_groups = [self.active_groups[g] for g in groups if g in self.active_groups]
            else:
                session_groups = list(self.active_groups.values())
            
            session = TabSession(name=name, groups=session_groups)
            self.saved_sessions[name] = session
            
            # Save to disk
            filepath = self.sessions_dir / f"{name}.json"
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(session.to_dict(), f, indent=2)
            
            return {
                'success': True,
                'session_name': name,
                'groups_count': len(session_groups),
                'message': f"Saved session '{name}' with {len(session_groups)} groups"
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def load_session(self, name: str, open_tabs: bool = True) -> Dict[str, Any]:
        """
        Load a saved session.
        
        Args:
            name: Session name
            open_tabs: Whether to open the tabs
        
        Returns:
            Dict with success status
        """
        if name not in self.saved_sessions:
            return {'success': False, 'error': f"Session '{name}' not found"}
        
        session = self.saved_sessions[name]
        session.last_used = datetime.now()
        
        # Restore groups
        for group in session.groups:
            self.active_groups[group.name] = group
            
            if open_tabs:
                self.open_group(group.name)
        
        return {
            'success': True,
            'session_name': name,
            'groups_restored': len(session.groups),
            'message': f"Loaded session '{name}'"
        }
    
    def delete_session(self, name: str) -> Dict[str, Any]:
        """
        Delete a saved session.
        
        Args:
            name: Session name
        
        Returns:
            Dict with success status
        """
        if name in self.saved_sessions:
            del self.saved_sessions[name]
            
            # Delete file
            filepath = self.sessions_dir / f"{name}.json"
            if filepath.exists():
                filepath.unlink()
            
            return {'success': True, 'message': f"Deleted session '{name}'"}
        
        return {'success': False, 'error': f"Session '{name}' not found"}
    
    def list_sessions(self) -> Dict[str, Any]:
        """List all saved sessions"""
        sessions = []
        for name, session in self.saved_sessions.items():
            sessions.append({
                'name': name,
                'groups_count': len(session.groups),
                'created': session.created.isoformat(),
                'last_used': session.last_used.isoformat()
            })
        
        return {
            'success': True,
            'sessions': sessions,
            'count': len(sessions)
        }
    
    def _load_sessions(self):
        """Load saved sessions from disk"""
        try:
            for filepath in self.sessions_dir.glob("*.json"):
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    session = TabSession.from_dict(data)
                    self.saved_sessions[session.name] = session
            
            logger.info(f"[OK] Loaded {len(self.saved_sessions)} saved sessions")
        
        except Exception as e:
            logger.error(f"[X] Failed to load sessions: {e}")
    
    # ==================== PARALLEL OPERATIONS ====================
    
    def open_multiple_tabs(self, urls: List[str], 
                           parallel: bool = False) -> Dict[str, Any]:
        """
        Open multiple tabs at once.
        
        Args:
            urls: List of URLs to open
            parallel: Whether to open in parallel threads
        
        Returns:
            Dict with success status
        """
        if not self.tab_controller:
            return {'success': False, 'error': 'Tab controller not available'}
        
        results = []
        
        if parallel:
            # Open tabs in parallel (faster but may overwhelm browser)
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = {
                    executor.submit(self.tab_controller.open_tab, url): url 
                    for url in urls
                }
                for future in concurrent.futures.as_completed(futures):
                    url = futures[future]
                    try:
                        result = future.result()
                        results.append({'url': url, 'success': result.get('success', False)})
                    except Exception as e:
                        results.append({'url': url, 'success': False, 'error': str(e)})
        else:
            # Open tabs sequentially
            for url in urls:
                result = self.tab_controller.open_tab(url)
                results.append({'url': url, 'success': result.get('success', False)})
                time.sleep(0.3)
        
        successful = sum(1 for r in results if r['success'])
        
        return {
            'success': successful > 0,
            'tabs_opened': successful,
            'total_requested': len(urls),
            'results': results,
            'message': f"Opened {successful}/{len(urls)} tabs"
        }
    
    def close_all_tabs(self, keep_one: bool = True) -> Dict[str, Any]:
        """
        Close all browser tabs.
        
        Args:
            keep_one: Keep at least one tab open
        
        Returns:
            Dict with success status
        """
        if not self.tab_controller:
            return {'success': False, 'error': 'Tab controller not available'}
        
        try:
            import pyautogui
            
            # Close tabs repeatedly
            closed = 0
            max_attempts = 50  # Safety limit
            
            while closed < max_attempts:
                pyautogui.hotkey('ctrl', 'w')
                closed += 1
                time.sleep(0.1)
                
                # Stop early if we detect only one tab
                if keep_one and closed > 2:
                    # Check if browser is still open
                    break
            
            return {
                'success': True,
                'tabs_closed': closed,
                'message': f"Closed approximately {closed} tabs"
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def refresh_all_tabs(self) -> Dict[str, Any]:
        """Refresh all open tabs by cycling through them"""
        if not self.tab_controller:
            return {'success': False, 'error': 'Tab controller not available'}
        
        try:
            import pyautogui
            
            refreshed = 0
            max_tabs = 20
            
            for i in range(max_tabs):
                # Refresh current tab
                pyautogui.press('f5')
                time.sleep(0.3)
                
                # Move to next tab
                pyautogui.hotkey('ctrl', 'tab')
                time.sleep(0.2)
                
                refreshed += 1
                
                # Could add logic to detect when we've cycled back
            
            return {
                'success': True,
                'tabs_refreshed': refreshed,
                'message': f"Refreshed up to {refreshed} tabs"
            }
        
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    # ==================== QUICK ACTIONS ====================
    
    def research_topic(self, topic: str) -> Dict[str, Any]:
        """
        Open research tabs for a topic.
        
        Args:
            topic: Topic to research
        
        Returns:
            Dict with success status
        """
        import urllib.parse
        encoded_topic = urllib.parse.quote(topic)
        
        urls = [
            f"https://www.google.com/search?q={encoded_topic}",
            f"https://en.wikipedia.org/wiki/Special:Search?search={encoded_topic}",
            f"https://scholar.google.com/scholar?q={encoded_topic}",
        ]
        
        result = self.open_multiple_tabs(urls)
        result['topic'] = topic
        result['message'] = f"Opened research tabs for '{topic}'"
        
        return result
    
    def compare_products(self, product: str) -> Dict[str, Any]:
        """
        Open product comparison tabs.
        
        Args:
            product: Product to compare
        
        Returns:
            Dict with success status
        """
        import urllib.parse
        encoded = urllib.parse.quote(product)
        
        urls = [
            f"https://www.amazon.com/s?k={encoded}",
            f"https://www.google.com/search?q={encoded}+reviews",
            f"https://www.reddit.com/search/?q={encoded}",
        ]
        
        result = self.open_multiple_tabs(urls)
        result['product'] = product
        result['message'] = f"Opened comparison tabs for '{product}'"
        
        return result
    
    def quick_social_check(self) -> Dict[str, Any]:
        """Open all social media tabs quickly"""
        return self.open_workspace('social')
    
    def quick_productivity(self) -> Dict[str, Any]:
        """Open productivity workspace"""
        return self.open_workspace('productivity')


# Factory function for workflow engine integration
def create_multi_tab_orchestrator(default_browser: str = 'chrome') -> MultiTabOrchestrator:
    """Create and return a MultiTabOrchestrator instance"""
    return MultiTabOrchestrator(default_browser)


if __name__ == '__main__':
    # Test the multi-tab orchestrator
    logging.basicConfig(level=logging.INFO)
    mto = MultiTabOrchestrator()
    
    print("\n=== Testing Multi-Tab Orchestrator ===")
    
    # List workspaces
    result = mto.list_workspaces()
    print(f"Available workspaces: {result['count']}")
    for ws in result['workspaces']:
        print(f"  • {ws['name']}: {ws['tabs_count']} tabs")
    
    # List sessions
    result = mto.list_sessions()
    print(f"\nSaved sessions: {result['count']}")
    
    print("\n[OK] Multi-Tab Orchestrator tests complete!")
    print("\nTry commands like:")
    print("  mto.open_workspace('research')")
    print("  mto.research_topic('machine learning')")
    print("  mto.save_session('work_session')")
