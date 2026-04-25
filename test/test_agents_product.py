"""
Comprehensive tests for modules/agents/product_agent.py
Tests ProductAgent class with proper mocking.
"""

import pytest
import sys
from unittest.mock import MagicMock, patch


# Mock browser automation modules
@pytest.fixture(autouse=True)
def mock_browser_modules():
    """Mock browser automation modules for testing."""
    mock_comet = MagicMock()
    mock_comet.CometBrowserAgent = MagicMock()
    
    mock_safety = MagicMock()
    mock_safety.SafetyGate = MagicMock()
    
    with patch.dict(sys.modules, {
        'modules.browser_automation': mock_comet,
        'modules.safety_gate': mock_safety,
    }):
        yield {
            'comet': mock_comet,
            'safety': mock_safety
        }


class TestProductAgentInit:
    """Tests for ProductAgent initialization."""
    
    def test_init_with_ai_router(self, mock_browser_modules):
        """Test ProductAgent initialization."""
        from modules.agents.product_agent import ProductAgent
        
        mock_router = MagicMock()
        agent = ProductAgent(mock_router)
        
        assert agent.ai_router == mock_router
        assert agent.browser is None
        assert agent.safety is None
        assert agent.results == []
    
    def test_init_components(self, mock_browser_modules):
        """Test component initialization."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        agent._init_components()
        
        assert agent.browser is not None
        assert agent.safety is not None


class TestParseProducts:
    """Tests for product parsing from page text."""
    
    def test_parse_products_with_prices(self, mock_browser_modules):
        """Test parsing products with prices."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        
        page_text = """
        iPhone 15 128GB - Best smartphone
        Samsung Galaxy S23 - Premium phone
        OnePlus 12 - Great value
        """
        
        prices = [
            {'amount': 79990, 'currency': 'INR'},
            {'amount': 74999, 'currency': 'INR'},
            {'amount': 64999, 'currency': 'INR'},
        ]
        
        products = agent._parse_products(page_text, prices, "iphone")
        
        assert isinstance(products, list)
    
    def test_parse_products_empty(self, mock_browser_modules):
        """Test parsing with empty data."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        
        products = agent._parse_products("", [], "laptop")
        
        assert products == []
    
    def test_parse_products_filters_unrealistic_prices(self, mock_browser_modules):
        """Test that unrealistic prices are filtered."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        
        prices = [
            {'amount': 100, 'currency': 'INR'},  # Too low
            {'amount': 25000, 'currency': 'INR'},  # Valid
            {'amount': 1000000, 'currency': 'INR'},  # Too high
        ]
        
        products = agent._parse_products("laptop test", prices, "laptop")
        
        # Only valid prices should be included
        for product in products:
            assert 500 <= product['price'] <= 500000


class TestGenerateSampleProducts:
    """Tests for sample product generation."""
    
    def test_generate_sample_phones(self, mock_browser_modules):
        """Test generating sample phone products."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        
        products = agent._generate_sample_products("iphone 15", max_price=80000)
        
        assert isinstance(products, list)
        assert len(products) == 5
        
        # Check for phone brands
        names = [p['name'].lower() for p in products]
        assert any('samsung' in n or 'iphone' in n or 'oneplus' in n for n in names)
    
    def test_generate_sample_laptops(self, mock_browser_modules):
        """Test generating sample laptop products."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        
        products = agent._generate_sample_products("laptop", max_price=60000)
        
        assert len(products) == 5
        
        # Check for laptop brands
        names = [p['name'].lower() for p in products]
        assert any('hp' in n or 'dell' in n or 'lenovo' in n for n in names)
    
    def test_generate_sample_generic(self, mock_browser_modules):
        """Test generating sample generic products."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        
        products = agent._generate_sample_products("headphones", max_price=10000)
        
        assert len(products) == 5
        
        # Should return products (may be generic phone products if not matched)
        assert all('name' in p for p in products)
    
    def test_generate_sample_respects_max_price(self, mock_browser_modules):
        """Test that max price is respected."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        
        products = agent._generate_sample_products("phone", max_price=20000)
        
        for product in products:
            assert product['price'] <= 20000
    
    def test_generate_sample_sorted_by_price(self, mock_browser_modules):
        """Test products are sorted by price."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        
        products = agent._generate_sample_products("laptop", max_price=50000)
        
        prices = [p['price'] for p in products]
        assert prices == sorted(prices)


class TestGenerateRecommendation:
    """Tests for recommendation generation."""
    
    def test_recommendation_empty_products(self, mock_browser_modules):
        """Test recommendation with no products."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        
        rec = agent._generate_recommendation([], "laptop", None)
        
        assert "No products found" in rec
    
    def test_recommendation_with_products(self, mock_browser_modules):
        """Test recommendation with products."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        
        products = [
            {'name': 'Cheap Laptop', 'price': 25000, 'rating': 4.0},
            {'name': 'Premium Laptop', 'price': 50000, 'rating': 4.8},
        ]
        
        rec = agent._generate_recommendation(products, "laptop", None)
        
        assert "Best Value" in rec
        assert "Cheap Laptop" in rec
    
    def test_recommendation_with_different_best_rated(self, mock_browser_modules):
        """Test recommendation when best rated differs from cheapest."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        
        products = [
            {'name': 'Budget Phone', 'price': 15000, 'rating': 3.5},
            {'name': 'Top Phone', 'price': 50000, 'rating': 4.9},
        ]
        
        rec = agent._generate_recommendation(products, "phone", None)
        
        assert "Highest Rated" in rec
        assert "Top Phone" in rec
    
    def test_recommendation_with_max_price(self, mock_browser_modules):
        """Test recommendation includes price filter info."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        
        products = [{'name': 'Product', 'price': 10000, 'rating': 4.0}]
        
        rec = agent._generate_recommendation(products, "item", max_price=15000)
        
        assert "15,000" in rec


class TestSearchProducts:
    """Tests for product search functionality."""
    
    def test_search_cancelled_by_user(self, mock_browser_modules):
        """Test search cancelled when user declines permission."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        
        mock_safety = MagicMock()
        mock_safety.ask_permission.return_value = False
        
        with patch.object(agent, '_init_components'):
            agent.safety = mock_safety
            
            result = agent.search_products("laptop")
            
            assert result['status'] == 'cancelled'
    
    def test_search_browser_init_failure(self, mock_browser_modules):
        """Test search when browser fails to initialize."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        
        mock_safety = MagicMock()
        mock_safety.ask_permission.return_value = True
        
        mock_browser = MagicMock()
        mock_browser.init_browser.return_value = False
        
        with patch.object(agent, '_init_components'):
            agent.safety = mock_safety
            agent.browser = mock_browser
            
            result = agent.search_products("phone")
            
            assert result['status'] == 'error'
            assert 'browser' in result['error'].lower()
    
    def test_search_success(self, mock_browser_modules):
        """Test successful product search."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        
        mock_safety = MagicMock()
        mock_safety.ask_permission.return_value = True
        
        mock_browser = MagicMock()
        mock_browser.init_browser.return_value = True
        mock_browser.navigate.return_value = {'success': True}
        mock_browser.get_page_screenshot.return_value = 'screenshot.png'
        mock_browser.extract_text.return_value = ''
        mock_browser.get_all_prices.return_value = []
        mock_browser.get_current_url.return_value = 'https://amazon.in/search'
        mock_browser.fill_form = MagicMock()
        mock_browser.click_element.return_value = {'success': True}
        
        with patch.object(agent, '_init_components'):
            with patch('time.sleep'):
                agent.safety = mock_safety
                agent.browser = mock_browser
                
                result = agent.search_products("laptop", max_price=50000)
                
                assert result['status'] == 'success'
                assert 'products' in result
                assert 'cheapest' in result
                assert 'recommendation' in result
    
    def test_search_with_progress_callback(self, mock_browser_modules):
        """Test search with progress callback."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        
        progress_calls = []
        def progress_callback(step, total, desc):
            progress_calls.append((step, total, desc))
        
        mock_safety = MagicMock()
        mock_safety.ask_permission.return_value = True
        
        mock_browser = MagicMock()
        mock_browser.init_browser.return_value = True
        mock_browser.navigate.return_value = {'success': True}
        mock_browser.get_page_screenshot.return_value = 'screenshot.png'
        mock_browser.extract_text.return_value = ''
        mock_browser.get_all_prices.return_value = []
        mock_browser.get_current_url.return_value = 'https://amazon.in/search'
        mock_browser.fill_form = MagicMock()
        mock_browser.click_element.return_value = {'success': True}
        
        with patch.object(agent, '_init_components'):
            with patch('time.sleep'):
                agent.safety = mock_safety
                agent.browser = mock_browser
                
                result = agent.search_products(
                    "phone",
                    progress_callback=progress_callback
                )
                
                assert len(progress_calls) == 5
    
    def test_search_filters_by_max_price(self, mock_browser_modules):
        """Test search respects max price filter."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        
        mock_safety = MagicMock()
        mock_safety.ask_permission.return_value = True
        
        mock_browser = MagicMock()
        mock_browser.init_browser.return_value = True
        mock_browser.navigate.return_value = {'success': True}
        mock_browser.get_page_screenshot.return_value = 'screenshot.png'
        mock_browser.extract_text.return_value = ''
        mock_browser.get_all_prices.return_value = []
        mock_browser.get_current_url.return_value = 'https://amazon.in/search'
        mock_browser.fill_form = MagicMock()
        mock_browser.click_element.return_value = {'success': True}
        
        with patch.object(agent, '_init_components'):
            with patch('time.sleep'):
                agent.safety = mock_safety
                agent.browser = mock_browser
                
                result = agent.search_products("phone", max_price=30000)
                
                for product in result['products']:
                    assert product['price'] <= 30000


class TestCompareProducts:
    """Tests for product comparison."""
    
    def test_compare_no_results(self, mock_browser_modules):
        """Test compare with no search results."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        agent.results = []
        
        result = agent.compare_products([0, 1])
        
        assert 'error' in result
        assert "No search results" in result['error']
    
    def test_compare_too_few_products(self, mock_browser_modules):
        """Test compare with less than 2 products."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        agent.results = [{'name': 'Product 1', 'price': 1000, 'rating': 4.0}]
        
        result = agent.compare_products([0])
        
        assert 'error' in result
        assert "at least 2 products" in result['error']
    
    def test_compare_valid_products(self, mock_browser_modules):
        """Test comparing valid products."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        agent.results = [
            {'name': 'Product 1', 'price': 10000, 'rating': 4.0},
            {'name': 'Product 2', 'price': 15000, 'rating': 4.5},
            {'name': 'Product 3', 'price': 12000, 'rating': 4.2},
        ]
        
        result = agent.compare_products([0, 1, 2])
        
        assert 'products' in result
        assert len(result['products']) == 3
        assert result['price_range']['min'] == 10000
        assert result['price_range']['max'] == 15000
        assert result['best_price']['name'] == 'Product 1'
        assert result['best_rating']['name'] == 'Product 2'
    
    def test_compare_invalid_indices(self, mock_browser_modules):
        """Test compare with invalid product indices."""
        from modules.agents.product_agent import ProductAgent
        
        agent = ProductAgent(MagicMock())
        agent.results = [
            {'name': 'Product 1', 'price': 10000, 'rating': 4.0},
        ]
        
        # Index 5 doesn't exist
        result = agent.compare_products([0, 5])
        
        assert 'error' in result
