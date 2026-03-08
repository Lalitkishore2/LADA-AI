"""
LADA - Deep Research Engine
Perplexity-style multi-step research with parallel search, query decomposition,
and AI synthesis with inline citations.

Features:
- Query decomposition into sub-queries
- Parallel multi-source search (DuckDuckGo, Wikipedia, news)
- AI-powered synthesis with numbered citations
- Source tracking end-to-end
"""

import logging
import re
import time
import requests
from typing import Optional, Dict, Any, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus, urlparse
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Source:
    """A single research source with metadata"""
    index: int  # Citation number [1], [2], etc.
    title: str
    url: str
    domain: str
    snippet: str
    search_query: str = ""  # Which sub-query found this


@dataclass
class ResearchResult:
    """Complete result of a deep research operation"""
    query: str
    sub_queries: List[str]
    sources: List[Source]
    raw_context: str  # Combined context for AI
    synthesis: str = ""  # AI-generated answer (filled later)
    search_time: float = 0.0
    source_count: int = 0


class DeepResearchEngine:
    """
    Multi-step research engine inspired by Perplexity Pro Search.

    Workflow:
    1. Analyze query complexity
    2. Decompose complex queries into sub-queries
    3. Search multiple sources in parallel
    4. Deduplicate and rank results
    5. Format context with numbered sources for AI synthesis
    """

    # Queries that benefit from deep research (multi-step)
    COMPLEX_PATTERNS = [
        r'\b(compare|comparison|versus|vs\.?|difference)\b',
        r'\b(pros?\s+and\s+cons?|advantages?\s+and\s+disadvantages?)\b',
        r'\b(step.by.step|how\s+to|tutorial|guide)\b',
        r'\b(best|top\s+\d+|ranking|recommend)\b',
        r'\b(explain|analyze|evaluate|assess|review)\b',
        r'\b(history|timeline|evolution|development)\b',
        r'\b(why|cause|reason|impact|effect)\b',
        r'\b(research|study|report|statistics|data)\b',
    ]

    def __init__(self, ai_router=None):
        """
        Initialize deep research engine.

        Args:
            ai_router: HybridAIRouter instance for query decomposition
        """
        self.ai_router = ai_router
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.max_workers = 4
        self.search_timeout = 10
        self.max_sources = 10
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes

    def needs_deep_research(self, query: str) -> bool:
        """Determine if a query would benefit from multi-step deep research."""
        q = query.lower().strip()

        # Too short for deep research
        if len(q.split()) < 4:
            return False

        # Check complexity patterns
        for pattern in self.COMPLEX_PATTERNS:
            if re.search(pattern, q):
                return True

        # Multiple question marks or conjunctions suggest compound queries
        if q.count('?') > 1 or ' and ' in q:
            return True

        return False

    def decompose_query(self, query: str) -> List[str]:
        """
        Decompose a complex query into focused sub-queries.
        Uses AI if available, falls back to heuristic decomposition.
        """
        # Try AI decomposition first
        if self.ai_router:
            try:
                prompt = (
                    "Break this research question into 2-4 focused search queries. "
                    "Return ONLY the queries, one per line, no numbering or bullets.\n\n"
                    f"Question: {query}"
                )
                # Use the non-streaming query to avoid complexity
                result = self.ai_router.query(prompt)
                if result:
                    lines = [
                        line.strip().strip('-').strip('•').strip('*').strip()
                        for line in result.strip().split('\n')
                        if line.strip() and len(line.strip()) > 5
                    ]
                    # Filter out meta-text the AI might add
                    sub_queries = [
                        l for l in lines
                        if not l.lower().startswith(('here', 'sure', 'i ', 'these', 'the following'))
                    ]
                    if 2 <= len(sub_queries) <= 5:
                        logger.info(f"[DeepResearch] AI decomposed into {len(sub_queries)} sub-queries")
                        return sub_queries
            except Exception as e:
                logger.warning(f"[DeepResearch] AI decomposition failed: {e}")

        # Heuristic fallback
        return self._heuristic_decompose(query)

    def _heuristic_decompose(self, query: str) -> List[str]:
        """Rule-based query decomposition as fallback."""
        sub_queries = [query]  # Always include original
        q = query.lower()

        # "compare X and Y" -> search each separately + comparison
        compare_match = re.search(
            r'compare\s+(.+?)\s+(?:and|vs\.?|versus|with)\s+(.+)', q
        )
        if compare_match:
            a, b = compare_match.group(1).strip(), compare_match.group(2).strip()
            return [
                query,
                f"{a} features advantages",
                f"{b} features advantages",
                f"{a} vs {b} comparison",
            ]

        # "best X for Y" -> search for reviews + specific use case
        best_match = re.search(r'best\s+(.+?)\s+for\s+(.+)', q)
        if best_match:
            item, use = best_match.group(1).strip(), best_match.group(2).strip()
            return [
                query,
                f"top {item} {time.strftime('%Y')} review",
                f"{item} for {use} recommendations",
            ]

        # "how to X" -> search for tutorials + specifics
        howto_match = re.search(r'how\s+to\s+(.+)', q)
        if howto_match:
            topic = howto_match.group(1).strip()
            return [
                query,
                f"{topic} step by step guide",
                f"{topic} tips best practices",
            ]

        # "why X" or "explain X" -> search for causes + context
        why_match = re.search(r'(?:why|explain)\s+(.+)', q)
        if why_match:
            topic = why_match.group(1).strip()
            return [
                query,
                f"{topic} explanation",
                f"{topic} causes reasons",
            ]

        return sub_queries

    def search_duckduckgo(self, query: str) -> List[Dict[str, Any]]:
        """Search DuckDuckGo and return structured results with URLs."""
        results = []

        # Try Instant Answer API
        try:
            url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
            resp = self.session.get(url, timeout=self.search_timeout)
            if resp.status_code == 200:
                data = resp.json()

                if data.get('Abstract'):
                    results.append({
                        'title': data.get('AbstractSource', 'Source'),
                        'url': data.get('AbstractURL', ''),
                        'snippet': data['Abstract'],
                        'source_type': 'abstract',
                    })

                for topic in data.get('RelatedTopics', [])[:4]:
                    if isinstance(topic, dict) and topic.get('Text'):
                        results.append({
                            'title': topic.get('Text', '')[:80],
                            'url': topic.get('FirstURL', ''),
                            'snippet': topic['Text'],
                            'source_type': 'related',
                        })
        except Exception as e:
            logger.debug(f"[DeepResearch] DDG API error: {e}")

        # Also try HTML scraping for more results
        try:
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            resp = self.session.get(url, timeout=self.search_timeout)
            if resp.status_code == 200:
                snippets = re.findall(
                    r'class="result__snippet"[^>]*>([^<]+)', resp.text
                )
                titles = re.findall(
                    r'class="result__a"[^>]*>([^<]+)', resp.text
                )
                urls = re.findall(
                    r'class="result__url"[^>]*href="([^"]+)"', resp.text
                )
                # Also try extracting urls from result__a hrefs
                if not urls:
                    urls = re.findall(
                        r'class="result__a"\s+href="([^"]+)"', resp.text
                    )

                for i in range(min(len(titles), len(snippets), 5)):
                    result_url = urls[i] if i < len(urls) else ''
                    # DuckDuckGo HTML uses redirect URLs, extract actual URL
                    actual_url = result_url
                    if 'uddg=' in result_url:
                        from urllib.parse import unquote
                        match = re.search(r'uddg=([^&]+)', result_url)
                        if match:
                            actual_url = unquote(match.group(1))

                    results.append({
                        'title': titles[i].strip(),
                        'url': actual_url,
                        'snippet': snippets[i].strip(),
                        'source_type': 'web',
                    })
        except Exception as e:
            logger.debug(f"[DeepResearch] DDG scrape error: {e}")

        return results

    def search_wikipedia(self, query: str) -> List[Dict[str, Any]]:
        """Search Wikipedia API for encyclopedic content."""
        results = []
        try:
            url = "https://en.wikipedia.org/w/api.php"
            params = {
                'action': 'query',
                'list': 'search',
                'srsearch': query,
                'srlimit': 3,
                'format': 'json',
                'utf8': 1,
            }
            resp = self.session.get(url, params=params, timeout=self.search_timeout)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get('query', {}).get('search', []):
                    title = item.get('title', '')
                    # Clean HTML from snippet
                    snippet = re.sub(r'<[^>]+>', '', item.get('snippet', ''))
                    results.append({
                        'title': title,
                        'url': f"https://en.wikipedia.org/wiki/{quote_plus(title.replace(' ', '_'))}",
                        'snippet': snippet,
                        'source_type': 'wikipedia',
                    })
        except Exception as e:
            logger.debug(f"[DeepResearch] Wikipedia error: {e}")

        return results

    def parallel_search(self, sub_queries: List[str]) -> List[Dict[str, Any]]:
        """
        Execute searches for all sub-queries in parallel across multiple sources.
        Returns deduplicated, ranked results.
        """
        all_results = []
        start = time.time()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}

            for sq in sub_queries:
                # DuckDuckGo for each sub-query
                f = executor.submit(self.search_duckduckgo, sq)
                futures[f] = ('duckduckgo', sq)

                # Wikipedia for the first 2 sub-queries only
                if sub_queries.index(sq) < 2:
                    f2 = executor.submit(self.search_wikipedia, sq)
                    futures[f2] = ('wikipedia', sq)

            for future in as_completed(futures, timeout=15):
                source_name, sq = futures[future]
                try:
                    results = future.result()
                    for r in results:
                        r['search_query'] = sq
                    all_results.extend(results)
                except Exception as e:
                    logger.warning(f"[DeepResearch] Search failed ({source_name}): {e}")

        elapsed = time.time() - start
        logger.info(f"[DeepResearch] Parallel search: {len(all_results)} results in {elapsed:.1f}s")

        # Deduplicate by URL
        seen_urls = set()
        unique = []
        for r in all_results:
            url = r.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique.append(r)
            elif not url:
                # Keep results without URLs if snippet is unique
                snippet_key = r.get('snippet', '')[:100]
                if snippet_key not in seen_urls:
                    seen_urls.add(snippet_key)
                    unique.append(r)

        return unique[:self.max_sources]

    def build_research_result(self, query: str, raw_results: List[Dict[str, Any]], sub_queries: List[str]) -> ResearchResult:
        """
        Build a structured ResearchResult with numbered sources and formatted context.
        """
        sources = []
        context_parts = []

        for i, r in enumerate(raw_results):
            idx = i + 1
            url = r.get('url', '')
            domain = urlparse(url).netloc if url else 'unknown'

            source = Source(
                index=idx,
                title=r.get('title', f'Source {idx}'),
                url=url,
                domain=domain,
                snippet=r.get('snippet', ''),
                search_query=r.get('search_query', ''),
            )
            sources.append(source)

            # Format for AI context with source numbers
            context_parts.append(
                f"[Source {idx}: {source.title} - {source.domain}]\n{source.snippet}\n"
            )

        raw_context = "\n".join(context_parts)

        return ResearchResult(
            query=query,
            sub_queries=sub_queries,
            sources=sources,
            raw_context=raw_context,
            source_count=len(sources),
        )

    def research(self, query: str) -> ResearchResult:
        """
        Execute full deep research pipeline.

        Steps:
        1. Decompose query into sub-queries
        2. Search sources in parallel
        3. Build structured result with citations

        The AI synthesis step happens in the router/GUI layer when the context
        is passed to the AI model with citation instructions.
        """
        start = time.time()

        # Check cache
        cache_key = query.lower().strip()[:200]
        if cache_key in self.cache:
            cached_time, cached_result = self.cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                logger.info("[DeepResearch] Cache hit")
                return cached_result

        # Step 1: Decompose
        if self.needs_deep_research(query):
            sub_queries = self.decompose_query(query)
            logger.info(f"[DeepResearch] Decomposed into {len(sub_queries)} sub-queries: {sub_queries}")
        else:
            sub_queries = [query]
            logger.info("[DeepResearch] Simple query, single search")

        # Step 2: Parallel search
        raw_results = self.parallel_search(sub_queries)

        # Step 3: Build result
        result = self.build_research_result(query, raw_results, sub_queries)
        result.search_time = time.time() - start

        # Cache
        self.cache[cache_key] = (time.time(), result)

        logger.info(
            f"[DeepResearch] Complete: {result.source_count} sources, "
            f"{result.search_time:.1f}s"
        )
        return result

    def format_context_for_ai(self, result: ResearchResult) -> str:
        """
        Format research results as context for the AI model,
        with instructions to use inline citations.
        """
        if not result.sources:
            return ""

        parts = [
            "[RESEARCH CONTEXT - Use inline citations like [1], [2] when referencing information below]",
            f"Query: {result.query}",
            f"Sources found: {result.source_count}",
            "",
        ]
        parts.append(result.raw_context)
        parts.append(
            "\nIMPORTANT: When using information from the sources above, "
            "cite them using [1], [2], etc. inline in your response. "
            "Be thorough and synthesize information from multiple sources."
        )

        return "\n".join(parts)

    def get_sources_for_display(self, result: ResearchResult) -> List[Dict[str, str]]:
        """
        Convert research sources to display format for GUI source badges.
        """
        return [
            {
                'index': str(s.index),
                'title': s.title[:60],
                'url': s.url,
                'domain': s.domain,
            }
            for s in result.sources
            if s.url  # Only show sources with URLs
        ]


# Singleton
_deep_research = None


def get_deep_research(ai_router=None) -> DeepResearchEngine:
    """Get or create deep research engine instance."""
    global _deep_research
    if _deep_research is None:
        _deep_research = DeepResearchEngine(ai_router=ai_router)
    elif ai_router and not _deep_research.ai_router:
        _deep_research.ai_router = ai_router
    return _deep_research


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    engine = DeepResearchEngine()

    queries = [
        "Compare solar and wind energy for residential use",
        "Best laptop for programming 2026",
        "How to improve Python performance",
        "Weather today",  # Simple - should NOT trigger deep research
    ]

    for q in queries:
        print(f"\n{'='*60}")
        print(f"Query: {q}")
        print(f"Needs deep research: {engine.needs_deep_research(q)}")
        result = engine.research(q)
        print(f"Sub-queries: {result.sub_queries}")
        print(f"Sources: {result.source_count}")
        print(f"Time: {result.search_time:.1f}s")
        for s in result.sources[:3]:
            print(f"  [{s.index}] {s.title[:50]} - {s.domain}")
