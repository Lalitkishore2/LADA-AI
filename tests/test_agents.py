"""
LADA v9.0 - Agent Tests
Tests for specialized AI agents
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys

# Mock modules - REMOVED global sys.modules mocking to avoid polluting other tests
# sys.modules["modules.browser_automation"] = MagicMock()
# sys.modules["modules.safety_gate"] = MagicMock()

from modules.agent_orchestrator import AgentOrchestrator, AgentType, AgentResult
from modules.agents.product_agent import ProductAgent

class TestAgentOrchestrator:
    """Test agent orchestration"""
    
    def test_orchestrator_initialization(self):
        """Test orchestrator initializes"""
        orchestrator = AgentOrchestrator()
        assert orchestrator is not None
        assert hasattr(orchestrator, "agents")
    
    def test_agent_selection(self):
        """Test correct agent is selected for query"""
        orchestrator = AgentOrchestrator()
        
        test_cases = [
            ("find gaming laptop", AgentType.PRODUCT),
            ("book flight to Paris", AgentType.FLIGHT),
            ("find hotels in Tokyo", AgentType.HOTEL),
            ("restaurants near me", AgentType.RESTAURANT),
            ("send email to John", AgentType.EMAIL),
            ("schedule meeting tomorrow", AgentType.CALENDAR)
        ]
        
        for query, expected_agent in test_cases:
            agent_type, confidence = orchestrator.detect_intent(query)
            assert agent_type == expected_agent, f"Failed for: {query}"
    
    def test_route_to_agent(self):
        """Test routing to a specific agent"""
        orchestrator = AgentOrchestrator()
        mock_agent = MagicMock()
        mock_agent.process.return_value = "Processed"
        
        orchestrator.register_agent(AgentType.PRODUCT, mock_agent)
        
        result = orchestrator.route_to_agent("find laptop", force_agent=AgentType.PRODUCT)
        
        assert result.success
        assert result.data == "Processed"
        assert result.agent_type == AgentType.PRODUCT
        mock_agent.process.assert_called_with("find laptop")

    def test_parallel_execute(self):
        """Test parallel execution of multiple agents"""
        orchestrator = AgentOrchestrator()
        
        mock_product = MagicMock()
        mock_product.process.return_value = "Product Result"
        orchestrator.register_agent(AgentType.PRODUCT, mock_product)
        
        mock_flight = MagicMock()
        mock_flight.process.return_value = "Flight Result"
        orchestrator.register_agent(AgentType.FLIGHT, mock_flight)
        
        results = orchestrator.parallel_execute("test query", [AgentType.PRODUCT, AgentType.FLIGHT])
        
        assert len(results) == 2
        assert any(r.agent_type == AgentType.PRODUCT for r in results)
        assert any(r.agent_type == AgentType.FLIGHT for r in results)
        assert any(r.data == "Product Result" for r in results)
        assert any(r.data == "Flight Result" for r in results)

    def test_agent_error_handling(self):
        """Test agent handles errors gracefully"""
        orchestrator = AgentOrchestrator()
        # Disable fallback for this test to see the original error
        orchestrator.fallback_chain = []
        
        mock_agent = MagicMock()
        mock_agent.process.side_effect = Exception("Test error")
        
        orchestrator.register_agent(AgentType.PRODUCT, mock_agent)
        
        result = orchestrator.route_to_agent("test query", force_agent=AgentType.PRODUCT)
        
        assert not result.success
        assert "Test error" in result.error


class TestProductAgent:
    """Test product search agent"""
    
    @pytest.fixture
    def product_agent(self):
        return ProductAgent(ai_router=MagicMock())
    
    def test_initialization(self, product_agent):
        assert product_agent is not None
        assert product_agent.ai_router is not None

    def test_search_products_permission_denied(self, product_agent):
        """Test search when permission is denied"""
        with patch.object(product_agent, "_init_components"):
            product_agent.safety = MagicMock()
            product_agent.safety.ask_permission.return_value = False
            product_agent.browser = MagicMock()
            
            result = product_agent.search_products("laptop")
            
            assert result["status"] == "cancelled"
            assert "User declined" in result["error"]

    def test_search_products_browser_fail(self, product_agent):
        """Test search when browser init fails"""
        with patch.object(product_agent, "_init_components"):
            product_agent.safety = MagicMock()
            product_agent.safety.ask_permission.return_value = True
            product_agent.browser = MagicMock()
            product_agent.browser.init_browser.return_value = False
            
            result = product_agent.search_products("laptop")
            
            assert result["status"] == "error"
            assert "Failed to initialize browser" in result["error"]

