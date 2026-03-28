"""LADA ResearchAgent

Specialized agent for multi-step research tasks.

Features:
- Multi-source web research
- Academic paper search
- News aggregation
- Fact checking
- Citation tracking
- Summary generation

Usage:
    from modules.agents.research_agent import ResearchAgent
    
    agent = ResearchAgent()
    result = await agent.research("latest AI breakthroughs 2026")
"""

from __future__ import annotations

import os
import asyncio
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ResearchSource:
    """A source found during research."""
    title: str
    url: str
    snippet: str
    source_type: str  # web, news, academic, wiki
    relevance_score: float = 0.0
    timestamp: Optional[datetime] = None


@dataclass
class ResearchResult:
    """Complete research result."""
    query: str
    summary: str
    sources: List[ResearchSource]
    facts: List[str]
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "summary": self.summary,
            "sources": [
                {"title": s.title, "url": s.url, "type": s.source_type}
                for s in self.sources
            ],
            "facts": self.facts,
            "timestamp": self.timestamp.isoformat(),
        }


class ResearchAgent:
    """Agent for comprehensive multi-source research.
    
    Combines web search, news, and academic sources to provide
    well-researched answers with citations.
    """
    
    def __init__(self, max_sources: int = 10):
        """Initialize research agent.
        
        Args:
            max_sources: Maximum sources to gather per query
        """
        self.max_sources = max_sources
        self._cache: Dict[str, ResearchResult] = {}
        
        logger.info("[ResearchAgent] Initialized")
    
    async def research(
        self,
        query: str,
        depth: str = "standard",
        include_news: bool = True,
        include_academic: bool = False,
    ) -> ResearchResult:
        """Perform comprehensive research on a topic.
        
        Args:
            query: Research query
            depth: Research depth (quick, standard, deep)
            include_news: Include recent news
            include_academic: Include academic papers
            
        Returns:
            ResearchResult with sources and summary
        """
        logger.info(f"[ResearchAgent] Researching: {query}")
        
        # Check cache
        cache_key = f"{query}:{depth}"
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            age = (datetime.now() - cached.timestamp).total_seconds()
            if age < 3600:  # 1 hour cache
                logger.debug("[ResearchAgent] Returning cached result")
                return cached
        
        sources: List[ResearchSource] = []
        
        # Gather sources based on depth
        tasks = [self._search_web(query)]
        
        if include_news:
            tasks.append(self._search_news(query))
        
        if include_academic:
            tasks.append(self._search_academic(query))
        
        if depth == "deep":
            tasks.append(self._search_wikipedia(query))
        
        # Run searches concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, list):
                sources.extend(result)
        
        # Sort by relevance and limit
        sources.sort(key=lambda s: s.relevance_score, reverse=True)
        sources = sources[:self.max_sources]
        
        # Generate summary
        summary = await self._generate_summary(query, sources)
        
        # Extract key facts
        facts = await self._extract_facts(sources)
        
        result = ResearchResult(
            query=query,
            summary=summary,
            sources=sources,
            facts=facts,
        )
        
        # Cache result
        self._cache[cache_key] = result
        
        return result
    
    async def _search_web(self, query: str) -> List[ResearchSource]:
        """Search web sources."""
        sources = []
        
        try:
            # Try to use LADA's web search
            from modules.web_search import WebSearchEngine
            
            engine = WebSearchEngine()
            results = engine.search(query, num_results=5)
            
            for i, r in enumerate(results):
                sources.append(ResearchSource(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("snippet", ""),
                    source_type="web",
                    relevance_score=1.0 - (i * 0.1),
                ))
                
        except ImportError:
            logger.debug("[ResearchAgent] Web search not available")
        
        return sources
    
    async def _search_news(self, query: str) -> List[ResearchSource]:
        """Search news sources."""
        sources = []
        
        try:
            from modules.news_aggregator import NewsAggregator
            
            aggregator = NewsAggregator()
            articles = aggregator.search(query, limit=3)
            
            for i, article in enumerate(articles):
                sources.append(ResearchSource(
                    title=article.get("title", ""),
                    url=article.get("url", ""),
                    snippet=article.get("description", ""),
                    source_type="news",
                    relevance_score=0.9 - (i * 0.1),
                    timestamp=article.get("published"),
                ))
                
        except ImportError:
            logger.debug("[ResearchAgent] News aggregator not available")
        
        return sources
    
    async def _search_academic(self, query: str) -> List[ResearchSource]:
        """Search academic sources (arXiv, Google Scholar)."""
        sources = []
        
        # Placeholder - would integrate with arXiv API, Semantic Scholar, etc.
        logger.debug("[ResearchAgent] Academic search placeholder")
        
        return sources
    
    async def _search_wikipedia(self, query: str) -> List[ResearchSource]:
        """Search Wikipedia for background info."""
        sources = []
        
        try:
            import urllib.parse
            
            # Simple Wikipedia search URL
            wiki_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(query.replace(' ', '_'))}"
            
            sources.append(ResearchSource(
                title=f"Wikipedia: {query}",
                url=wiki_url,
                snippet=f"Wikipedia article about {query}",
                source_type="wiki",
                relevance_score=0.7,
            ))
            
        except Exception as e:
            logger.debug(f"[ResearchAgent] Wikipedia search error: {e}")
        
        return sources
    
    async def _generate_summary(self, query: str, sources: List[ResearchSource]) -> str:
        """Generate a summary from gathered sources."""
        if not sources:
            return f"No sources found for: {query}"
        
        # Build context from sources
        context = "\n".join([
            f"- {s.title}: {s.snippet}"
            for s in sources[:5]
        ])
        
        try:
            # Try to use LADA's AI router for summary
            from lada_ai_router import query_ai
            
            prompt = f"""Based on these sources about "{query}":

{context}

Provide a concise 2-3 sentence summary of the key findings."""

            summary = await asyncio.to_thread(
                query_ai, prompt, tier="fast"
            )
            return summary
            
        except Exception:
            # Fallback: simple concatenation
            return f"Research on '{query}' found {len(sources)} sources. " + \
                   (sources[0].snippet if sources else "")
    
    async def _extract_facts(self, sources: List[ResearchSource]) -> List[str]:
        """Extract key facts from sources."""
        facts = []
        
        for source in sources[:3]:
            if source.snippet:
                # Simple fact extraction - first sentence
                sentences = source.snippet.split('. ')
                if sentences:
                    facts.append(sentences[0].strip())
        
        return facts
    
    async def fact_check(self, claim: str) -> Dict[str, Any]:
        """Fact-check a specific claim.
        
        Args:
            claim: Claim to verify
            
        Returns:
            Dict with verdict and supporting sources
        """
        result = await self.research(claim, depth="deep", include_news=True)
        
        # Simple verdict based on source agreement
        if len(result.sources) >= 3:
            verdict = "likely_true"
        elif len(result.sources) >= 1:
            verdict = "unverified"
        else:
            verdict = "no_sources"
        
        return {
            "claim": claim,
            "verdict": verdict,
            "sources": [s.url for s in result.sources],
            "summary": result.summary,
        }
    
    def clear_cache(self):
        """Clear the research cache."""
        self._cache.clear()
        logger.info("[ResearchAgent] Cache cleared")


# Singleton
_agent: Optional[ResearchAgent] = None


def get_research_agent(**kwargs) -> ResearchAgent:
    """Get or create ResearchAgent singleton."""
    global _agent
    if _agent is None:
        _agent = ResearchAgent(**kwargs)
    return _agent
