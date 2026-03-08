"""
LADA v7.0 - Agent Orchestrator
Smart routing and coordination of multiple AI agents
"""

import re
import json
import logging
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class AgentType(Enum):
    """Types of available agents."""
    CHAT = "chat"
    FLIGHT = "flight"
    PRODUCT = "product"
    HOTEL = "hotel"
    RESTAURANT = "restaurant"
    EMAIL = "email"
    CALENDAR = "calendar"
    SHOPPING = "shopping"
    WEB_SEARCH = "web_search"
    SYSTEM = "system"


@dataclass
class AgentResult:
    """Result from an agent execution."""
    success: bool
    agent_type: AgentType
    data: Any
    message: str
    execution_time: float = 0.0
    error: Optional[str] = None


class AgentOrchestrator:
    """
    Smart routing and coordination of multiple AI agents.
    
    Features:
    - Intent detection from user queries
    - Route to appropriate agent
    - Fallback handling when primary agent fails
    - Parallel agent execution
    - Result comparison and aggregation
    """
    
    # Intent detection patterns
    INTENT_PATTERNS = {
        AgentType.FLIGHT: [
            r'\b(flight|flights|fly|flying|airline|airfare)\b',
            r'\b(book.*flight|flight.*book)\b',
            r'\b(cheap.*flight|flight.*cheap)\b',
            r'\b(from .+ to .+)\b.*\b(flight|fly)\b',
        ],
        AgentType.HOTEL: [
            r'\b(hotel|hotels|accommodation|stay|lodging|resort|motel)\b',
            r'\b(book.*hotel|hotel.*book)\b',
            r'\b(room.*night|night.*room)\b',
            r'\b(check.?in|check.?out)\b',
        ],
        AgentType.RESTAURANT: [
            r'\b(restaurant|restaurants|food|dining|eat|dinner|lunch|breakfast)\b',
            r'\b(book.*table|table.*book|reservation)\b',
            r'\b(near.*food|food.*near)\b',
            r'\b(cuisine|menu|order.*food)\b',
        ],
        AgentType.EMAIL: [
            r'\b(email|mail|send.*email|draft.*email)\b',
            r'\b(inbox|compose|reply)\b',
            r'\b(write.*to|message.*to)\b.*@',
        ],
        AgentType.CALENDAR: [
            r'\b(calendar|schedule|meeting|appointment)\b',
            r'\b(schedule.*meeting|meeting.*schedule)\b',
            r'\b(free.*time|available|availability)\b',
            r'\b(remind|reminder)\b',
        ],
        AgentType.PRODUCT: [
            r'\b(product|products|buy|purchase|shop|compare)\b',
            r'\b(amazon|flipkart|price|review)\b',
            r'\b(best.*under|under.*budget)\b',
            r'\b(laptop|phone|tv|headphone|camera)\b',
        ],
        AgentType.SHOPPING: [
            r'\b(shopping|shop|store|cart|checkout)\b',
            r'\b(deal|discount|offer|sale)\b',
            r'\b(add.*cart|buy.*online)\b',
        ],
        AgentType.WEB_SEARCH: [
            r'\b(search|google|find|look up|what is)\b',
            r'\b(latest|current|today|news|trending)\b',
            r'\b(weather|stock|price)\b',
        ],
        AgentType.SYSTEM: [
            r'\b(volume|brightness|screenshot|wifi|bluetooth)\b',
            r'\b(open|close|launch|run)\b.*\b(app|application|program)\b',
            r'\b(shutdown|restart|sleep|lock)\b',
        ],
    }
    
    def __init__(self, ai_router=None):
        """
        Initialize the orchestrator.
        
        Args:
            ai_router: HybridAIRouter instance for chat fallback
        """
        self.ai_router = ai_router
        self.agents: Dict[AgentType, Any] = {}
        self.fallback_chain: List[AgentType] = []
        self.execution_history: List[Dict] = []
        
        # Register default fallback chain
        self.fallback_chain = [
            AgentType.WEB_SEARCH,
            AgentType.CHAT
        ]
        
        # Callbacks
        self.on_agent_start: Optional[Callable] = None
        self.on_agent_complete: Optional[Callable] = None
        self.on_progress: Optional[Callable] = None
    
    def register_agent(self, agent_type: AgentType, agent_instance: Any):
        """Register an agent with the orchestrator."""
        self.agents[agent_type] = agent_instance
        logger.info(f"[Orchestrator] Registered agent: {agent_type.value}")
    
    def detect_intent(self, query: str) -> Tuple[AgentType, float]:
        """
        Detect the user's intent from the query.
        
        Args:
            query: User's input text
            
        Returns:
            Tuple of (AgentType, confidence_score)
        """
        query_lower = query.lower()
        
        best_match = AgentType.CHAT
        best_score = 0.0
        
        for agent_type, patterns in self.INTENT_PATTERNS.items():
            score = 0
            for pattern in patterns:
                matches = re.findall(pattern, query_lower, re.IGNORECASE)
                if matches:
                    score += len(matches)
            
            # Normalize score
            if score > 0:
                normalized_score = min(score / 3.0, 1.0)  # Cap at 1.0
                if normalized_score > best_score:
                    best_score = normalized_score
                    best_match = agent_type
        
        # If no strong match, default to chat
        if best_score < 0.3:
            best_match = AgentType.CHAT
            best_score = 0.5
        
        logger.info(f"[Orchestrator] Intent: {best_match.value} (confidence: {best_score:.2f})")
        return best_match, best_score
    
    def route_to_agent(self, query: str, force_agent: Optional[AgentType] = None) -> AgentResult:
        """
        Route the query to the appropriate agent.
        
        Args:
            query: User's input text
            force_agent: Optionally force a specific agent
            
        Returns:
            AgentResult from the executed agent
        """
        import time
        start_time = time.time()
        
        # Detect intent
        if force_agent:
            agent_type = force_agent
            confidence = 1.0
        else:
            agent_type, confidence = self.detect_intent(query)
        
        # Notify start
        if self.on_agent_start:
            self.on_agent_start(agent_type, query)
        
        # Try to execute the agent
        result = self._execute_agent(agent_type, query)
        
        # If failed, try fallback chain
        if not result.success and agent_type != AgentType.CHAT:
            for fallback_type in self.fallback_chain:
                if fallback_type == agent_type:
                    continue
                
                logger.info(f"[Orchestrator] Trying fallback: {fallback_type.value}")
                result = self._execute_agent(fallback_type, query)
                
                if result.success:
                    break
        
        # Calculate execution time
        result.execution_time = time.time() - start_time
        
        # Record history
        self.execution_history.append({
            'timestamp': datetime.now().isoformat(),
            'query': query,
            'intent': agent_type.value,
            'confidence': confidence,
            'success': result.success,
            'execution_time': result.execution_time
        })
        
        # Keep only last 100 entries
        if len(self.execution_history) > 100:
            self.execution_history = self.execution_history[-100:]
        
        # Notify complete
        if self.on_agent_complete:
            self.on_agent_complete(result)
        
        return result
    
    def _execute_agent(self, agent_type: AgentType, query: str) -> AgentResult:
        """Execute a specific agent."""
        try:
            # Check if agent is registered
            if agent_type in self.agents:
                agent = self.agents[agent_type]
                
                # Different agents have different interfaces
                if hasattr(agent, 'process'):
                    data = agent.process(query)
                elif hasattr(agent, 'search'):
                    data = agent.search(query)
                elif hasattr(agent, 'execute'):
                    data = agent.execute(query)
                else:
                    data = str(agent)
                
                return AgentResult(
                    success=True,
                    agent_type=agent_type,
                    data=data,
                    message=f"Executed {agent_type.value} agent successfully"
                )
            
            # Fallback to chat via AI router
            elif agent_type == AgentType.CHAT and self.ai_router:
                response = self.ai_router.query(query)
                return AgentResult(
                    success=True,
                    agent_type=AgentType.CHAT,
                    data={'response': response},
                    message="Chat response generated"
                )
            
            # Agent not available
            else:
                return AgentResult(
                    success=False,
                    agent_type=agent_type,
                    data=None,
                    message=f"Agent {agent_type.value} not registered",
                    error="Agent not available"
                )
                
        except Exception as e:
            logger.error(f"[Orchestrator] Agent {agent_type.value} failed: {e}")
            return AgentResult(
                success=False,
                agent_type=agent_type,
                data=None,
                message=f"Agent failed: {str(e)}",
                error=str(e)
            )
    
    def parallel_execute(self, query: str, agent_types: List[AgentType]) -> List[AgentResult]:
        """
        Execute multiple agents in parallel.
        
        Args:
            query: User's input text
            agent_types: List of agent types to execute
            
        Returns:
            List of AgentResults
        """
        import concurrent.futures
        
        results = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(agent_types)) as executor:
            futures = {
                executor.submit(self._execute_agent, agent_type, query): agent_type
                for agent_type in agent_types
            }
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    agent_type = futures[future]
                    results.append(AgentResult(
                        success=False,
                        agent_type=agent_type,
                        data=None,
                        message=f"Parallel execution failed: {e}",
                        error=str(e)
                    ))
        
        return results
    
    def compare_results(self, results: List[AgentResult]) -> AgentResult:
        """
        Compare multiple agent results and return the best one.
        
        Args:
            results: List of AgentResults to compare
            
        Returns:
            Best AgentResult
        """
        # Filter successful results
        successful = [r for r in results if r.success]
        
        if not successful:
            # Return first failed result
            return results[0] if results else AgentResult(
                success=False,
                agent_type=AgentType.CHAT,
                data=None,
                message="No results available"
            )
        
        # Prefer non-chat results
        non_chat = [r for r in successful if r.agent_type != AgentType.CHAT]
        if non_chat:
            # Return the one with shortest execution time
            return min(non_chat, key=lambda r: r.execution_time)
        
        # Return any successful result
        return successful[0]
    
    def get_available_agents(self) -> List[str]:
        """Get list of registered agent names."""
        return [agent_type.value for agent_type in self.agents.keys()]
    
    def get_statistics(self) -> Dict:
        """Get orchestrator statistics."""
        total = len(self.execution_history)
        successful = sum(1 for h in self.execution_history if h.get('success'))
        
        # Agent usage counts
        agent_counts = {}
        for h in self.execution_history:
            intent = h.get('intent', 'chat')
            agent_counts[intent] = agent_counts.get(intent, 0) + 1
        
        # Average execution time
        times = [h.get('execution_time', 0) for h in self.execution_history]
        avg_time = sum(times) / len(times) if times else 0
        
        return {
            'total_queries': total,
            'successful': successful,
            'success_rate': successful / total if total > 0 else 0,
            'agent_usage': agent_counts,
            'average_execution_time': avg_time,
            'registered_agents': self.get_available_agents()
        }


# ============================================================
# EXAMPLE USAGE
# ============================================================
if __name__ == "__main__":
    print("🚀 Testing AgentOrchestrator...")
    
    orchestrator = AgentOrchestrator()
    
    # Test intent detection
    test_queries = [
        "Book a flight from Chennai to Mumbai tomorrow",
        "Find hotels in Delhi under 5000",
        "Search for best laptop under 50000",
        "What's the weather today?",
        "Set up a meeting with John at 3pm",
        "Hello, how are you?",
        "Send email to boss@company.com",
        "Find restaurants near me",
    ]
    
    print("\n📊 Intent Detection Tests:")
    for query in test_queries:
        intent, confidence = orchestrator.detect_intent(query)
        print(f"  '{query[:40]}...' → {intent.value} ({confidence:.2f})")
    
    # Test statistics
    print(f"\n📈 Statistics: {orchestrator.get_statistics()}")
    
    print("\n✅ AgentOrchestrator test complete!")
