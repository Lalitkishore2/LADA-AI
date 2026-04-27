"""
LADA v7.0 - Web Search Module
Comet-style intelligent web search for real-time data

Features:
- DuckDuckGo Instant Answer API (free, no key required)
- Auto-detect queries needing real-time data
- Search result parsing and summarization
- Fallback chain for reliability
"""

import requests
import logging
import re
from typing import Optional, Dict, Any, List
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


class WebSearchEngine:
    """
    Intelligent web search with auto-detection for real-time queries
    Like Comet browser - automatically searches when AI doesn't have current info
    """
    
    # Triggers that indicate query needs real-time data
    REALTIME_TRIGGERS = [
        # Time-sensitive
        'today', 'now', 'current', 'latest', 'recent', 'new', 'this week', 'this month',
        'yesterday', 'tomorrow', '2024', '2025', '2026',
        
        # Real-time data
        'weather', 'temperature', 'forecast', 'rain', 'sunny',
        'stock', 'price', 'cost', 'rate', 'exchange',
        'news', 'update', 'happening', 'trending',
        
        # Live info
        'flight', 'flights', 'ticket', 'booking', 'schedule',
        'open', 'closed', 'hours', 'available', 'in stock',
        'score', 'match', 'game', 'live',
        
        # Comparisons often need current data
        'best', 'top', 'compare', 'vs', 'versus', 'review', 'rating',
        
        # Location-based
        'near me', 'nearby', 'directions', 'how to get',
        
        # Knowledge queries that need real data
        'college', 'university', 'school', 'institute', 'admission',
        'phone', 'laptop', 'computer', 'device', 'model',
        'company', 'brand', 'product', 'service',
        'city', 'country', 'place', 'location', 'state',
        'movie', 'song', 'actor', 'actress', 'celebrity',
        'sports', 'team', 'player', 'tournament',
        'about', 'tell me', 'information', 'details',
    ]
    
    # Triggers that indicate query needs high-quality research (Tavily)
    RESEARCH_TRIGGERS = [
        'news', 'latest', 'recent', 'happening', 'trending', 'update',
        'compare', 'vs', 'versus', 'review', 'rating', 'best', 'top',
        'research', 'explain', 'impact', 'why', 'how did', 'analysis',
        'future', 'prediction', 'innovation', 'technology', 'market',
        'company', 'brand', 'product', 'service',
    ]
    
    def __init__(self):
        """Initialize web search engine"""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes
        
    def needs_web_search(self, query: str) -> bool:
        """
        Detect if a query needs real-time web data
        Enhanced detection for better local model support
        """
        query_lower = query.lower()
        
        # Always search for questions (starts with question word)
        question_starters = ['what', 'who', 'where', 'when', 'how', 'why', 'which', 'is', 'are', 'can', 'does', 'do', 'tell']
        first_word = query_lower.split()[0] if query_lower.split() else ''
        if first_word in question_starters:
            logger.info(f"[WebSearch] Question detected: '{first_word}...'")
            return True
        
        # Check for real-time triggers
        for trigger in self.REALTIME_TRIGGERS:
            if trigger in query_lower:
                logger.info(f"[WebSearch] Real-time trigger found: '{trigger}'")
                return True
        
        # If query is short (likely needs context), search anyway
        if len(query.split()) <= 5 and len(query) > 3:
            logger.info(f"[WebSearch] Short query, searching for context")
            return True
        
        return False
    
    def search(self, query: str) -> Dict[str, Any]:
        """Main search method - routes to configured provider with smart routing option"""
        import os
        provider = os.getenv('SEARCH_PROVIDER', 'duckduckgo').lower()
        smart_routing = os.getenv('SMART_SEARCH_ROUTING', 'true').lower() == 'true'
        
        # If smart routing is enabled, decide provider based on query complexity
        if smart_routing:
            if self._is_research_query(query):
                logger.info(f"[WebSearch] Smart routing: Complex query detected, using Tavily")
                provider = 'tavily'
            else:
                logger.info(f"[WebSearch] Smart routing: Simple query detected, using DuckDuckGo")
                provider = 'duckduckgo'

        if provider == 'tavily':
            result = self._search_tavily(query)
            if result.get('success'):
                return result
            logger.warning(f"[WebSearch] Tavily failed, falling back to DuckDuckGo: {result.get('error')}")
            
        return self._search_duckduckgo(query)

    def _is_research_query(self, query: str) -> bool:
        """Detect if a query is complex enough to warrant using Tavily credits"""
        query_lower = query.lower()
        
        # 1. Check for research-intent keywords
        for trigger in self.RESEARCH_TRIGGERS:
            if trigger in query_lower:
                return True
                
        # 2. Longer queries (usually more complex)
        if len(query.split()) >= 8:
            return True
            
        # 3. Questions starting with "How" or "Why" or "Explain"
        research_starters = ['how', 'why', 'explain', 'compare', 'analyze']
        first_word = query_lower.split()[0] if query_lower.split() else ''
        if first_word in research_starters:
            return True
            
        return False

    def _search_tavily(self, query: str) -> Dict[str, Any]:
        """Search using Tavily API (better for AI, no ads, high quality)"""
        import os
        api_key = os.getenv('TAVILY_API_KEY')
        
        if not api_key:
            return {'success': False, 'error': 'TAVILY_API_KEY not found in environment'}
            
        try:
            logger.info(f"[WebSearch] Using Tavily for: {query[:50]}")
            
            response = self.session.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "search_depth": "basic",
                    "include_answer": True,
                    "max_results": 5
                },
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            results = []
            for r in data.get('results', []):
                results.append({
                    'title': r.get('title', ''),
                    'snippet': r.get('content', ''),
                    'url': r.get('url', '')
                })
                
            return {
                'success': True,
                'query': query,
                'source': 'Tavily Search',
                'results': results,
                'summary': data.get('answer') or (results[0]['snippet'] if results else None)
            }
            
        except Exception as e:
            logger.error(f"[WebSearch] Tavily error: {e}")
            return {'success': False, 'error': str(e), 'query': query}

    def _search_duckduckgo(self, query: str) -> Dict[str, Any]:
        """Search using ddgs (DuckDuckGo Search) library for reliable live results."""
        # Try modern ddgs package first (replaces deprecated duckduckgo_search)
        try:
            from ddgs import DDGS
            
            logger.info(f"[WebSearch] Using ddgs for: {query[:50]}")
            
            with DDGS() as ddgs:
                ddgs_results = list(ddgs.text(query, max_results=5))
            
            if not ddgs_results:
                return {'success': False, 'query': query, 'error': 'No results found'}
                
            results = []
            for r in ddgs_results:
                results.append({
                    'title': r.get('title', ''),
                    'snippet': r.get('body', ''),
                    'url': r.get('href', '')
                })
                
            return {
                'success': True,
                'query': query,
                'source': 'DuckDuckGo Live Search',
                'results': results,
                'summary': results[0]['snippet'] if results else None
            }
        except ImportError:
            pass
        
        # Fallback to legacy duckduckgo_search if ddgs not installed
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from duckduckgo_search import DDGS as LegacyDDGS
            
            logger.info(f"[WebSearch] Using duckduckgo_search (legacy) for: {query[:50]}")
            
            with LegacyDDGS() as ddgs:
                ddgs_results = list(ddgs.text(query, max_results=5))
            
            if not ddgs_results:
                return {'success': False, 'query': query, 'error': 'No results found'}
                
            results = []
            for r in ddgs_results:
                results.append({
                    'title': r.get('title', ''),
                    'snippet': r.get('body', ''),
                    'url': r.get('href', '')
                })
                
            return {
                'success': True,
                'query': query,
                'source': 'DuckDuckGo Live Search',
                'results': results,
                'summary': results[0]['snippet'] if results else None
            }
            
        except Exception as e:
            logger.error(f"[WebSearch] Search error: {e}")
            return {'success': False, 'error': str(e), 'query': query}
    
    def format_for_ai(self, search_result: Dict[str, Any]) -> str:
        """Format search results as context for AI"""
        if not search_result.get('success'):
            return ""
        
        parts = []
        
        if search_result.get('answer'):
            parts.append(f"Answer: {search_result['answer']}")
        
        if search_result.get('abstract'):
            parts.append(f"Summary: {search_result['abstract']}")
            if search_result.get('source'):
                parts.append(f"Source: {search_result['source']}")
        
        if search_result.get('definition'):
            parts.append(f"Definition: {search_result['definition']}")
        
        if search_result.get('infobox'):
            parts.append("Key Facts:")
            for fact in search_result['infobox']:
                parts.append(f"  • {fact}")
        
        if search_result.get('results'):
            parts.append("Search Results:")
            for r in search_result['results'][:3]:
                parts.append(f"  • {r.get('title', '')}: {r.get('snippet', '')[:150]}")
        
        if search_result.get('related') and not parts:
            parts.append("Related Information:")
            for r in search_result['related'][:3]:
                parts.append(f"  • {r['text'][:150]}")
        
        return "\n".join(parts) if parts else ""
    
    def get_sources(self, search_result: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extract sources from search results for display badges like ChatGPT."""
        sources = []
        
        if not search_result.get('success'):
            return sources
        
        # Main source from abstract
        if search_result.get('abstract') and search_result.get('url'):
            from urllib.parse import urlparse
            domain = urlparse(search_result.get('url', '')).netloc
            sources.append({
                'title': search_result.get('source', 'Source'),
                'url': search_result.get('url', ''),
                'domain': domain
            })
        
        # Sources from search results
        if search_result.get('results'):
            for r in search_result['results'][:3]:
                if r.get('url'):
                    from urllib.parse import urlparse
                    domain = urlparse(r.get('url', '')).netloc
                    sources.append({
                        'title': r.get('title', 'Source'),
                        'url': r.get('url', ''),
                        'domain': domain
                    })
        
        # Sources from related topics
        if search_result.get('related'):
            for r in search_result['related'][:2]:
                if r.get('url'):
                    from urllib.parse import urlparse
                    domain = urlparse(r.get('url', '')).netloc
                    sources.append({
                        'title': r.get('text', 'Related')[:50],
                        'url': r.get('url', ''),
                        'domain': domain
                    })
        
        return sources
    
    def get_realtime_context(self, query: str) -> Optional[str]:
        """Get real-time context for a query if needed"""
        if not self.needs_web_search(query):
            return None
        
        logger.info(f"[WebSearch] Fetching real-time data for: {query}")
        
        result = self.search(query)
        context = self.format_for_ai(result)
        
        if context:
            logger.info(f"[WebSearch] Found context: {len(context)} chars")
            return context
        
        return None
    
    def get_realtime_context_with_sources(self, query: str) -> tuple:
        """
        Get real-time context and sources for a query.
        Returns: (context_str, sources_list)
        """
        if not self.needs_web_search(query):
            return None, []
        
        logger.info(f"[WebSearch] Fetching real-time data for: {query}")
        
        result = self.search(query)
        context = self.format_for_ai(result)
        sources = self.get_sources(result)
        
        if context:
            logger.info(f"[WebSearch] Found context: {len(context)} chars, {len(sources)} sources")
            return context, sources
        
        return None, []


# Singleton instance
_web_search = None

def get_web_search() -> WebSearchEngine:
    """Get or create web search instance"""
    global _web_search
    if _web_search is None:
        _web_search = WebSearchEngine()
    return _web_search


def search(query: str) -> Dict[str, Any]:
    """Quick search function"""
    return get_web_search().search(query)

def needs_search(query: str) -> bool:
    """Check if query needs web search"""
    return get_web_search().needs_web_search(query)

def get_context(query: str) -> Optional[str]:
    """Get real-time context if needed"""
    return get_web_search().get_realtime_context(query)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ws = WebSearchEngine()
    
    queries = [
        "What is the capital of France?",
        "weather in Chennai today",
        "best phone 2025",
        "Python programming"
    ]
    
    for q in queries:
        print(f"\n{'='*50}")
        print(f"Query: {q}")
        print(f"Needs web search: {ws.needs_web_search(q)}")
        result = ws.search(q)
        print(f"Result: {ws.format_for_ai(result)[:300]}")
