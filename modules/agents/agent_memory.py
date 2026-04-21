"""
LADA v10.0 - Agent Memory Mixin
Memory-based learning and optimization for smart agents

This mixin adds memory capabilities to any agent:
- Learn user preferences (preferred airlines, hotels, products)
- Remember past searches and selections
- Suggest based on history
- Track user feedback
- Personalize recommendations
"""

import logging
from typing import Dict, List, Any, Optional, Set
from datetime import datetime
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# Try to import memory system
try:
    from lada_memory import MemorySystem
    MEMORY_OK = True
except ImportError:
    MemorySystem = None
    MEMORY_OK = False
    logger.warning("[AgentMemory] Memory system not available")


class AgentMemoryMixin:
    """
    Mixin class to add memory capabilities to agents.
    
    Usage:
        class MyAgent(AgentMemoryMixin):
            agent_type = "product"
            
            def __init__(self):
                self.init_memory()
                
            def search(self, query):
                # Get user preferences
                prefs = self.get_preferences()
                
                # Do search...
                results = self._do_search(query)
                
                # Remember the search
                self.remember_search(query, results)
                
                return results
    """
    
    # Override in subclass
    agent_type: str = "generic"
    
    def init_memory(self, memory_system: Optional[Any] = None):
        """Initialize memory system for the agent"""
        self._memory = memory_system
        
        if not self._memory and MEMORY_OK:
            try:
                self._memory = MemorySystem()
            except Exception as e:
                logger.warning(f"[{self.agent_type}] Failed to init memory: {e}")
                self._memory = None
    
    @property
    def memory_available(self) -> bool:
        """Check if memory is available"""
        return self._memory is not None
    
    # ============================================================
    # PREFERENCES
    # ============================================================
    
    def get_preferences(self) -> Dict[str, Any]:
        """Get all preferences for this agent type"""
        if not self._memory:
            return {}
        
        try:
            prefs = self._memory.recall_fact(f"{self.agent_type}_preferences", "agent_preferences")
            return prefs if prefs else {}
        except Exception as e:
            logger.debug(f"[{self.agent_type}] Failed to get preferences: {e}")
            return {}
    
    def set_preference(self, key: str, value: Any):
        """Set a preference for this agent type"""
        if not self._memory:
            return
        
        try:
            prefs = self.get_preferences()
            prefs[key] = value
            prefs['last_updated'] = datetime.now().isoformat()
            
            self._memory.store_fact(
                f"{self.agent_type}_preferences",
                prefs,
                category="agent_preferences"
            )
            logger.info(f"[{self.agent_type}] Preference saved: {key}={value}")
        except Exception as e:
            logger.debug(f"[{self.agent_type}] Failed to set preference: {e}")
    
    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a specific preference"""
        prefs = self.get_preferences()
        return prefs.get(key, default)
    
    # ============================================================
    # SEARCH HISTORY
    # ============================================================
    
    def remember_search(
        self,
        query: str,
        results: List[Dict],
        metadata: Optional[Dict] = None
    ):
        """Remember a search query and its results"""
        if not self._memory:
            return
        
        try:
            history_key = f"{self.agent_type}_search_history"
            history = self._memory.recall_fact(history_key, "agent_history") or []
            
            # Keep last 100 searches
            if len(history) >= 100:
                history = history[-99:]
            
            history.append({
                'query': query,
                'timestamp': datetime.now().isoformat(),
                'result_count': len(results),
                'top_results': [r.get('name', str(r)[:50]) for r in results[:3]],
                'metadata': metadata or {}
            })
            
            self._memory.store_fact(history_key, history, category="agent_history")
        except Exception as e:
            logger.debug(f"[{self.agent_type}] Failed to remember search: {e}")
    
    def get_search_history(self, limit: int = 10) -> List[Dict]:
        """Get recent search history"""
        if not self._memory:
            return []
        
        try:
            history = self._memory.recall_fact(
                f"{self.agent_type}_search_history",
                "agent_history"
            ) or []
            return history[-limit:]
        except Exception as e:
            return []
    
    def get_frequent_searches(self, limit: int = 5) -> List[str]:
        """Get most frequent search queries"""
        history = self.get_search_history(limit=100)
        
        if not history:
            return []
        
        from collections import Counter
        queries = [h.get('query', '').lower() for h in history if h.get('query')]
        
        # Count occurrences
        counter = Counter(queries)
        
        # Return top queries
        return [q for q, _ in counter.most_common(limit)]
    
    # ============================================================
    # USER SELECTIONS & FEEDBACK
    # ============================================================
    
    def remember_selection(
        self,
        query: str,
        selected_item: Dict,
        alternatives: Optional[List[Dict]] = None
    ):
        """Remember what the user selected from results"""
        if not self._memory:
            return
        
        try:
            selections_key = f"{self.agent_type}_selections"
            selections = self._memory.recall_fact(selections_key, "agent_selections") or []
            
            # Keep last 50 selections
            if len(selections) >= 50:
                selections = selections[-49:]
            
            selections.append({
                'query': query,
                'timestamp': datetime.now().isoformat(),
                'selected': {
                    'name': selected_item.get('name'),
                    'price': selected_item.get('price'),
                    'rating': selected_item.get('rating'),
                    'brand': selected_item.get('brand'),
                    'source': selected_item.get('source'),
                },
                'alternatives_count': len(alternatives) if alternatives else 0
            })
            
            self._memory.store_fact(selections_key, selections, category="agent_selections")
            
            # Learn from selection
            self._learn_from_selection(selected_item)
            
        except Exception as e:
            logger.debug(f"[{self.agent_type}] Failed to remember selection: {e}")
    
    def _learn_from_selection(self, selected_item: Dict):
        """Learn preferences from user selection"""
        # Track brand preferences
        brand = selected_item.get('brand')
        if brand:
            brands = self.get_preference('preferred_brands', [])
            if brand not in brands:
                brands.append(brand)
                # Keep top 10 brands
                self.set_preference('preferred_brands', brands[-10:])
        
        # Track price range
        price = selected_item.get('price')
        if price and isinstance(price, (int, float)):
            prices = self.get_preference('price_history', [])
            prices.append(price)
            # Keep last 20 prices
            self.set_preference('price_history', prices[-20:])
            
            # Calculate average price preference
            avg_price = sum(prices) / len(prices)
            self.set_preference('avg_price_preference', round(avg_price, 2))
        
        # Track source/platform preferences
        source = selected_item.get('source')
        if source:
            sources = self.get_preference('preferred_sources', {})
            sources[source] = sources.get(source, 0) + 1
            self.set_preference('preferred_sources', sources)
    
    def get_preferred_brands(self) -> List[str]:
        """Get list of preferred brands"""
        return self.get_preference('preferred_brands', [])
    
    def get_price_preference(self) -> Optional[float]:
        """Get average price preference"""
        return self.get_preference('avg_price_preference')
    
    def get_preferred_sources(self) -> Dict[str, int]:
        """Get preferred sources/platforms with usage count"""
        return self.get_preference('preferred_sources', {})
    
    # ============================================================
    # RECOMMENDATIONS
    # ============================================================
    
    def get_personalized_recommendations(self) -> Dict[str, Any]:
        """Get personalized recommendations based on history"""
        prefs = self.get_preferences()
        history = self.get_search_history(limit=20)
        
        recommendations = {
            'preferred_brands': prefs.get('preferred_brands', []),
            'price_range': {
                'average': prefs.get('avg_price_preference'),
                'history': prefs.get('price_history', [])[-5:],
            },
            'frequent_searches': self.get_frequent_searches(limit=5),
            'preferred_sources': prefs.get('preferred_sources', {}),
            'suggestions': []
        }
        
        # Generate suggestions based on patterns
        if recommendations['preferred_brands']:
            recommendations['suggestions'].append(
                f"Based on your history, you prefer: {', '.join(recommendations['preferred_brands'][:3])}"
            )
        
        if recommendations['price_range']['average']:
            avg = recommendations['price_range']['average']
            recommendations['suggestions'].append(
                f"Your typical price range is around ₹{avg:,.0f}"
            )
        
        if recommendations['preferred_sources']:
            top_source = max(recommendations['preferred_sources'], key=recommendations['preferred_sources'].get)
            recommendations['suggestions'].append(
                f"You often choose from {top_source}"
            )
        
        return recommendations
    
    def score_result(self, item: Dict) -> float:
        """
        Score a result based on user preferences.
        Higher score = better match to user preferences.
        
        Args:
            item: Search result item
            
        Returns:
            Score from 0.0 to 1.0
        """
        score = 0.5  # Base score
        
        prefs = self.get_preferences()
        
        # Brand match
        preferred_brands = prefs.get('preferred_brands', [])
        item_brand = item.get('brand', '').lower()
        if item_brand and any(b.lower() in item_brand for b in preferred_brands):
            score += 0.2
        
        # Price match
        avg_price = prefs.get('avg_price_preference')
        item_price = item.get('price')
        if avg_price and item_price:
            # Score higher if within 30% of average
            price_diff = abs(item_price - avg_price) / avg_price
            if price_diff <= 0.3:
                score += 0.15
        
        # Source preference
        preferred_sources = prefs.get('preferred_sources', {})
        item_source = item.get('source', '')
        if item_source in preferred_sources:
            # Boost based on usage frequency
            source_count = preferred_sources[item_source]
            total_count = sum(preferred_sources.values())
            source_score = (source_count / total_count) * 0.15
            score += source_score
        
        return min(score, 1.0)
    
    def sort_by_preference(self, results: List[Dict]) -> List[Dict]:
        """Sort results by user preference score"""
        scored = [(self.score_result(r), r) for r in results]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored]
    
    # ============================================================
    # SPECIFIC AGENT PREFERENCES
    # ============================================================
    
    def remember_location(self, location: str, location_type: str = "destination"):
        """Remember a location (for travel agents)"""
        locations = self.get_preference(f'{location_type}_locations', [])
        if location not in locations:
            locations.append(location)
            self.set_preference(f'{location_type}_locations', locations[-20:])
    
    def get_frequent_destinations(self) -> List[str]:
        """Get frequently used destinations"""
        return self.get_preference('destination_locations', [])
    
    def get_home_location(self) -> Optional[str]:
        """Get home/default departure location"""
        return self.get_preference('home_location')
    
    def set_home_location(self, location: str):
        """Set home/default departure location"""
        self.set_preference('home_location', location)


# ============================================================
# EXAMPLE IMPLEMENTATION
# ============================================================

class MemoryAwareFlightAgent(AgentMemoryMixin):
    """Example: Flight agent with memory"""
    
    agent_type = "flight"
    
    def __init__(self, ai_router=None, memory_system=None):
        self.ai_router = ai_router
        self.init_memory(memory_system)
    
    def search_flights(
        self,
        from_city: str,
        to_city: str,
        date: str,
        **kwargs
    ) -> Dict:
        """Search flights with memory-based optimization"""
        
        # Use home location as default departure
        if not from_city:
            from_city = self.get_home_location() or "Delhi"
        
        # Get preferences for filtering
        prefs = self.get_preferences()
        preferred_airlines = prefs.get('preferred_brands', [])  # Airlines
        price_pref = prefs.get('avg_price_preference')
        
        # Do the actual search (placeholder)
        results = self._do_search(from_city, to_city, date, **kwargs)
        
        # Remember the search
        self.remember_search(
            f"{from_city} to {to_city}",
            results,
            metadata={'date': date}
        )
        
        # Remember locations
        self.remember_location(from_city, "departure")
        self.remember_location(to_city, "destination")
        
        # Sort by user preference
        results = self.sort_by_preference(results)
        
        # Add personalization info
        return {
            'results': results,
            'personalized': True,
            'preferred_airlines': preferred_airlines,
            'suggestions': self.get_personalized_recommendations().get('suggestions', [])
        }
    
    def _do_search(self, from_city, to_city, date, **kwargs):
        """Placeholder for actual search"""
        return []


class MemoryAwareProductAgent(AgentMemoryMixin):
    """Example: Product agent with memory"""
    
    agent_type = "product"
    
    def __init__(self, ai_router=None, memory_system=None):
        self.ai_router = ai_router
        self.init_memory(memory_system)
    
    def search_products(self, query: str, **kwargs) -> Dict:
        """Search products with memory-based optimization"""
        
        # Check if user asked for similar things before
        frequent = self.get_frequent_searches()
        
        # Get preferences
        preferred_brands = self.get_preferred_brands()
        price_pref = self.get_price_preference()
        preferred_sources = self.get_preferred_sources()
        
        # Do the search (placeholder)
        results = self._do_search(query, **kwargs)
        
        # Remember this search
        self.remember_search(query, results)
        
        # Sort by preference
        results = self.sort_by_preference(results)
        
        return {
            'results': results,
            'personalized': True,
            'preferred_brands': preferred_brands,
            'price_hint': price_pref,
            'recommendations': self.get_personalized_recommendations()
        }
    
    def on_user_purchase(self, product: Dict):
        """Called when user makes a purchase"""
        self.remember_selection("purchase", product)
        
        # Learn from purchase
        brand = product.get('brand')
        if brand:
            logger.info(f"[ProductAgent] Learned brand preference: {brand}")
    
    def _do_search(self, query, **kwargs):
        """Placeholder for actual search"""
        return []


# ============================================================
# USAGE EXAMPLE
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("🧠 Agent Memory Mixin Test")
    print("=" * 50)
    
    # Test product agent
    agent = MemoryAwareProductAgent()
    
    # Set some preferences
    agent.set_preference('preferred_brands', ['Apple', 'Samsung', 'Sony'])
    agent.set_preference('avg_price_preference', 50000)
    
    # Simulate searches
    agent.remember_search("iPhone 15", [{'name': 'iPhone 15', 'price': 79999}])
    agent.remember_search("Samsung S24", [{'name': 'Galaxy S24', 'price': 74999}])
    
    # Get recommendations
    recs = agent.get_personalized_recommendations()
    print(f"\n📊 Recommendations: {recs}")
    
    # Score an item
    test_item = {'name': 'iPhone 16', 'brand': 'Apple', 'price': 89999, 'source': 'amazon'}
    score = agent.score_result(test_item)
    print(f"\n📈 Score for iPhone 16: {score:.2f}")
    
    print("\n✅ Agent Memory test complete!")
