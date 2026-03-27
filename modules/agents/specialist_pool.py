"""
LADA v11.0 - Specialist Agent Pool
Registers existing specialist agents with the collaboration hub for delegation.
"""

import logging
from typing import Dict, Any, Optional, List, Callable

logger = logging.getLogger(__name__)

# Capability mappings for each specialist agent
SPECIALIST_CAPABILITIES = {
    'flight_agent': ['flight_search', 'flight_booking', 'travel', 'airlines', 'airports'],
    'hotel_agent': ['hotel_search', 'hotel_booking', 'accommodation', 'lodging', 'stay'],
    'restaurant_agent': ['restaurant_search', 'food', 'dining', 'reservations', 'cuisine'],
    'product_agent': ['product_search', 'shopping', 'e-commerce', 'price_comparison', 'reviews'],
    'email_agent': ['email', 'gmail', 'send_email', 'inbox', 'compose'],
    'calendar_agent': ['calendar', 'events', 'scheduling', 'meetings', 'appointments'],
    'package_tracking_agent': ['package_tracking', 'delivery', 'shipping', 'courier', 'tracking'],
}


class SpecialistPool:
    """
    Pool of specialist agents that can be delegated tasks via the collaboration hub.

    Features:
    - Lazy loading of specialist agents
    - Capability-based agent selection
    - Integration with AgentCollaborationHub
    """

    def __init__(self, ai_router=None):
        """
        Initialize the specialist pool.

        Args:
            ai_router: Optional HybridAIRouter instance for agents that need it
        """
        self.ai_router = ai_router
        self._agents: Dict[str, Any] = {}
        self._registered_with_hub = False

    def _load_agent(self, agent_name: str) -> Optional[Any]:
        """Lazy load a specialist agent by name."""
        if agent_name in self._agents:
            return self._agents[agent_name]

        try:
            if agent_name == 'flight_agent':
                from modules.agents.flight_agent import FlightAgent
                self._agents[agent_name] = FlightAgent(self.ai_router)

            elif agent_name == 'hotel_agent':
                from modules.agents.hotel_agent import HotelAgent
                self._agents[agent_name] = HotelAgent()

            elif agent_name == 'restaurant_agent':
                from modules.agents.restaurant_agent import RestaurantAgent
                self._agents[agent_name] = RestaurantAgent()

            elif agent_name == 'product_agent':
                from modules.agents.product_agent import ProductAgent
                self._agents[agent_name] = ProductAgent()

            elif agent_name == 'email_agent':
                from modules.agents.email_agent import EmailAgent
                self._agents[agent_name] = EmailAgent()

            elif agent_name == 'calendar_agent':
                from modules.agents.calendar_agent import CalendarAgent
                self._agents[agent_name] = CalendarAgent()

            elif agent_name == 'package_tracking_agent':
                from modules.agents.package_tracking_agent import PackageTrackingAgent
                self._agents[agent_name] = PackageTrackingAgent()

            else:
                logger.warning(f"[SpecialistPool] Unknown agent: {agent_name}")
                return None

            logger.info(f"[SpecialistPool] Loaded specialist: {agent_name}")
            return self._agents[agent_name]

        except Exception as e:
            logger.error(f"[SpecialistPool] Failed to load {agent_name}: {e}")
            return None

    def get_agent(self, agent_name: str) -> Optional[Any]:
        """Get a specialist agent instance by name."""
        return self._load_agent(agent_name)

    def register_with_hub(self, hub=None) -> bool:
        """
        Register all specialist agents with the collaboration hub.

        Args:
            hub: Optional AgentCollaborationHub instance (uses singleton if None)

        Returns:
            True if registration successful
        """
        if self._registered_with_hub:
            return True

        try:
            if hub is None:
                from modules.agent_collaboration import get_collaboration_hub
                hub = get_collaboration_hub()

            for agent_name, capabilities in SPECIALIST_CAPABILITIES.items():
                # Create message handler for this agent
                handler = self._create_message_handler(agent_name)

                hub.register_agent(
                    agent_name=agent_name,
                    capabilities=capabilities,
                    handler=handler,
                    metadata={
                        'type': 'specialist',
                        'pool': 'specialist_pool',
                    }
                )

            self._registered_with_hub = True
            logger.info(f"[SpecialistPool] Registered {len(SPECIALIST_CAPABILITIES)} specialists with hub")
            return True

        except Exception as e:
            logger.error(f"[SpecialistPool] Hub registration failed: {e}")
            return False

    def _create_message_handler(self, agent_name: str) -> Callable:
        """Create a message handler function for a specialist agent."""
        def handler(message):
            """Handle incoming message for this specialist."""
            agent = self._load_agent(agent_name)
            if agent is None:
                logger.error(f"[SpecialistPool] Cannot handle message - agent not loaded: {agent_name}")
                return

            msg_type = message.message_type
            content = message.content

            logger.info(f"[SpecialistPool] {agent_name} received {msg_type}: {str(content)[:100]}")

            if msg_type == 'task':
                # Execute the delegated task
                result = self._execute_task(agent_name, agent, content)

                # Report result back through hub
                from modules.agent_collaboration import get_collaboration_hub
                hub = get_collaboration_hub()

                if result.get('success', False):
                    hub.complete_task(content['task_id'], result, agent_name)
                else:
                    hub.fail_task(content['task_id'], result.get('error', 'Unknown error'), agent_name)

        return handler

    def _execute_task(self, agent_name: str, agent: Any, task_content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a task using the appropriate specialist agent method.

        Args:
            agent_name: Name of the specialist agent
            agent: Agent instance
            task_content: Task content with description and context

        Returns:
            Result dict with success flag and data/error
        """
        description = task_content.get('description', '')
        context = task_content.get('context', {})

        try:
            # Route to appropriate agent method based on description keywords
            desc_lower = description.lower()

            if agent_name == 'flight_agent':
                # Extract flight search params from description/context
                from_city = context.get('from_city', '')
                to_city = context.get('to_city', '')
                date = context.get('date', '')
                if hasattr(agent, 'search_flights'):
                    result = agent.search_flights(from_city, to_city, date)
                    return {'success': True, 'data': result}

            elif agent_name == 'hotel_agent':
                location = context.get('location', '')
                checkin = context.get('checkin', '')
                checkout = context.get('checkout', '')
                if hasattr(agent, 'search_hotels'):
                    result = agent.search_hotels(location, checkin, checkout)
                    return {'success': True, 'data': result}

            elif agent_name == 'restaurant_agent':
                location = context.get('location', '')
                cuisine = context.get('cuisine', '')
                if hasattr(agent, 'search_restaurants'):
                    result = agent.search_restaurants(location, cuisine)
                    return {'success': True, 'data': result}

            elif agent_name == 'product_agent':
                query = context.get('query', description)
                if hasattr(agent, 'search'):
                    result = agent.search(query)
                    return {'success': True, 'data': result}

            elif agent_name == 'email_agent':
                if 'send' in desc_lower or 'compose' in desc_lower:
                    to = context.get('to', '')
                    subject = context.get('subject', '')
                    body = context.get('body', '')
                    if hasattr(agent, 'send_email'):
                        result = agent.send_email(to, subject, body)
                        return {'success': True, 'data': result}
                elif 'check' in desc_lower or 'inbox' in desc_lower:
                    if hasattr(agent, 'check_inbox'):
                        result = agent.check_inbox()
                        return {'success': True, 'data': result}

            elif agent_name == 'calendar_agent':
                if 'create' in desc_lower or 'add' in desc_lower:
                    if hasattr(agent, 'create_event'):
                        result = agent.create_event(context)
                        return {'success': True, 'data': result}
                elif 'list' in desc_lower or 'show' in desc_lower:
                    if hasattr(agent, 'list_events'):
                        result = agent.list_events()
                        return {'success': True, 'data': result}

            elif agent_name == 'package_tracking_agent':
                tracking_number = context.get('tracking_number', '')
                if hasattr(agent, 'track'):
                    result = agent.track(tracking_number)
                    return {'success': True, 'data': result}

            # Fallback: try generic execute method
            if hasattr(agent, 'execute'):
                result = agent.execute(description, context)
                return {'success': True, 'data': result}

            return {'success': False, 'error': f'No suitable method found for task: {description[:50]}'}

        except Exception as e:
            logger.error(f"[SpecialistPool] Task execution error in {agent_name}: {e}")
            return {'success': False, 'error': str(e)}

    def delegate_to_specialist(self, task_description: str,
                               required_capability: str = None,
                               context: Dict[str, Any] = None,
                               from_agent: str = "orchestrator") -> Optional[str]:
        """
        Delegate a task to the best matching specialist.

        Args:
            task_description: Description of the task
            required_capability: Optional specific capability needed
            context: Task context/parameters
            from_agent: Name of the delegating agent

        Returns:
            Task ID if delegation successful, None otherwise
        """
        try:
            from modules.agent_collaboration import get_collaboration_hub
            hub = get_collaboration_hub()

            # Auto-detect capability from description if not specified
            if not required_capability:
                required_capability = self._detect_capability(task_description)

            # Delegate through hub
            task = hub.delegate_task(
                from_agent=from_agent,
                description=task_description,
                required_capability=required_capability,
                context=context or {}
            )

            return task.task_id

        except Exception as e:
            logger.error(f"[SpecialistPool] Delegation failed: {e}")
            return None

    def _detect_capability(self, description: str) -> str:
        """Detect required capability from task description."""
        desc_lower = description.lower()

        # Keywords to capability mapping
        keyword_map = {
            'flight': 'flight_search',
            'flights': 'flight_search',
            'airline': 'flight_search',
            'fly': 'flight_search',
            'hotel': 'hotel_search',
            'hotels': 'hotel_search',
            'accommodation': 'hotel_search',
            'stay': 'hotel_search',
            'restaurant': 'restaurant_search',
            'restaurants': 'restaurant_search',
            'food': 'restaurant_search',
            'dining': 'restaurant_search',
            'product': 'product_search',
            'shopping': 'product_search',
            'buy': 'product_search',
            'price': 'product_search',
            'email': 'email',
            'send mail': 'email',
            'inbox': 'email',
            'calendar': 'calendar',
            'event': 'calendar',
            'meeting': 'calendar',
            'schedule': 'calendar',
            'package': 'package_tracking',
            'tracking': 'package_tracking',
            'delivery': 'package_tracking',
        }

        for keyword, capability in keyword_map.items():
            if keyword in desc_lower:
                return capability

        return 'general'

    def list_specialists(self) -> List[Dict[str, Any]]:
        """List all available specialist agents with their capabilities."""
        return [
            {
                'name': name,
                'capabilities': caps,
                'loaded': name in self._agents,
            }
            for name, caps in SPECIALIST_CAPABILITIES.items()
        ]


# Singleton instance
_pool_instance: Optional[SpecialistPool] = None


def get_specialist_pool(ai_router=None) -> SpecialistPool:
    """Get the singleton SpecialistPool instance."""
    global _pool_instance
    if _pool_instance is None:
        _pool_instance = SpecialistPool(ai_router)
    return _pool_instance


def init_specialist_pool(ai_router=None, auto_register: bool = True) -> SpecialistPool:
    """
    Initialize the specialist pool and optionally register with collaboration hub.

    Args:
        ai_router: HybridAIRouter instance for agents that need it
        auto_register: Whether to automatically register with collaboration hub

    Returns:
        SpecialistPool instance
    """
    pool = get_specialist_pool(ai_router)
    if auto_register:
        pool.register_with_hub()
    return pool
