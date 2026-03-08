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
    
    def search_duckduckgo(self, query: str) -> Dict[str, Any]:
        """
        Search using DuckDuckGo Instant Answer API
        Free, no API key required
        """
        try:
            url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            # Check if response is valid JSON
            try:
                data = response.json()
            except ValueError:
                logger.warning(f"[WebSearch] DuckDuckGo returned invalid JSON")
                return {'success': False, 'error': 'Invalid JSON response', 'query': query}
            
            result = {
                'success': True,
                'query': query,
                'source': 'DuckDuckGo',
                'answer': None,
                'abstract': None,
                'url': None,
                'related': []
            }
            
            # Direct answer (like calculator, conversions)
            if data.get('Answer'):
                result['answer'] = data['Answer']
                result['answer_type'] = data.get('AnswerType', 'instant')
            
            # Abstract (Wikipedia-style summary)
            if data.get('Abstract'):
                result['abstract'] = data['Abstract']
                result['url'] = data.get('AbstractURL', '')
                result['source'] = data.get('AbstractSource', 'DuckDuckGo')
            
            # Infobox data
            if data.get('Infobox') and data['Infobox'].get('content'):
                infobox = []
                for item in data['Infobox']['content'][:5]:
                    if item.get('label') and item.get('value'):
                        infobox.append(f"{item['label']}: {item['value']}")
                if infobox:
                    result['infobox'] = infobox
            
            # Related topics (these often have useful info)
            for topic in data.get('RelatedTopics', [])[:5]:
                if isinstance(topic, dict) and topic.get('Text'):
                    result['related'].append({
                        'text': topic['Text'],
                        'url': topic.get('FirstURL', '')
                    })
            
            # Definition
            if data.get('Definition'):
                result['definition'] = data['Definition']
                result['definition_source'] = data.get('DefinitionSource', '')
            
            return result
            
        except requests.RequestException as e:
            logger.error(f"[WebSearch] DuckDuckGo error: {e}")
            return {
                'success': False,
                'error': str(e),
                'query': query
            }
    
    def search_with_scraping(self, query: str) -> Dict[str, Any]:
        """
        Fallback: Search using DuckDuckGo HTML and parse results
        """
        try:
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = self.session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            results = []
            
            # Simple regex parsing for results
            snippets = re.findall(r'class="result__snippet"[^>]*>([^<]+)', response.text)
            titles = re.findall(r'class="result__a"[^>]*>([^<]+)', response.text)
            
            for i, (title, snippet) in enumerate(zip(titles[:5], snippets[:5])):
                results.append({
                    'title': title.strip(),
                    'snippet': snippet.strip()
                })
            
            if results:
                return {
                    'success': True,
                    'query': query,
                    'source': 'DuckDuckGo Search',
                    'results': results,
                    'summary': results[0]['snippet'] if results else None
                }
            
            return {'success': False, 'query': query, 'error': 'No results found'}
            
        except Exception as e:
            logger.error(f"[WebSearch] Scraping error: {e}")
            return {'success': False, 'error': str(e), 'query': query}
    
    def search(self, query: str) -> Dict[str, Any]:
        """Main search method - tries multiple sources with robust fallback"""
        # Try instant answer first (fast)
        result = self.search_duckduckgo(query)
        
        # If API gave good results, return them
        if result.get('success') and (result.get('answer') or result.get('abstract')):
            logger.info(f"[WebSearch] Got instant answer for: {query[:50]}")
            return result
        
        # If API has related topics, that's still useful
        if result.get('success') and result.get('related') and len(result['related']) > 0:
            logger.info(f"[WebSearch] Got {len(result['related'])} related topics for: {query[:50]}")
            return result
        
        # Always try scraping as fallback (more reliable for general queries)
        logger.info(f"[WebSearch] Trying scrape fallback for: {query[:50]}")
        scrape_result = self.search_with_scraping(query)
        if scrape_result.get('success') and scrape_result.get('results'):
            logger.info(f"[WebSearch] Scrape found {len(scrape_result['results'])} results")
            return scrape_result
        
        # Return whatever we have
        return result if result.get('success') else scrape_result
    
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
