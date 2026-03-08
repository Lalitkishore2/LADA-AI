"""
Comprehensive tests for modules/agents/hotel_agent.py
Tests HotelAgent class with proper mocking.
"""

import pytest
import sys
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from dataclasses import asdict


# Mock browser modules at module level
@pytest.fixture(autouse=True)
def mock_browser_modules():
    """Mock browser automation modules for testing."""
    mock_comet = MagicMock()
    mock_comet.CometBrowserAgent = MagicMock()
    
    mock_safety = MagicMock()
    mock_safety.SafetyGate = MagicMock()
    mock_safety.RiskLevel = MagicMock()
    mock_safety.RiskLevel.HIGH = 'high'
    
    with patch.dict(sys.modules, {
        'modules.browser_automation': mock_comet,
        'modules.safety_gate': mock_safety,
    }):
        yield {
            'comet': mock_comet,
            'safety': mock_safety
        }


class TestHotelDataclass:
    """Tests for Hotel dataclass."""
    
    def test_hotel_creation(self, mock_browser_modules):
        """Test creating a Hotel instance."""
        from modules.agents.hotel_agent import Hotel
        
        hotel = Hotel(
            name="Grand Palace",
            location="Delhi City Center",
            price_per_night=3500.0,
            total_price=7000.0,
            rating=4.5,
            reviews_count=1200,
            amenities=['WiFi', 'Pool', 'Gym'],
            image_url="https://example.com/hotel.jpg",
            booking_url="https://booking.com/grand-palace",
            source="sample"
        )
        
        assert hotel.name == "Grand Palace"
        assert hotel.price_per_night == 3500.0
        assert hotel.rating == 4.5
        assert 'WiFi' in hotel.amenities


class TestHotelAgentInit:
    """Tests for HotelAgent initialization."""
    
    def test_init_with_defaults(self, mock_browser_modules):
        """Test HotelAgent initialization with defaults."""
        from modules.agents.hotel_agent import HotelAgent
        
        agent = HotelAgent()
        
        assert agent.browser is None
        assert agent.safety_gate is None
        assert agent.last_search_results == []
    
    def test_init_with_browser(self, mock_browser_modules):
        """Test HotelAgent initialization with browser."""
        from modules.agents.hotel_agent import HotelAgent
        
        mock_browser = MagicMock()
        agent = HotelAgent(browser=mock_browser)
        
        assert agent.browser == mock_browser
    
    def test_init_with_safety_gate(self, mock_browser_modules):
        """Test HotelAgent initialization with safety gate."""
        from modules.agents.hotel_agent import HotelAgent
        
        mock_safety = MagicMock()
        agent = HotelAgent(safety_gate=mock_safety)
        
        assert agent.safety_gate == mock_safety


class TestSearchHotels:
    """Tests for hotel search functionality."""
    
    def test_search_hotels_basic(self, mock_browser_modules):
        """Test basic hotel search."""
        from modules.agents.hotel_agent import HotelAgent
        
        agent = HotelAgent()
        
        result = agent.search_hotels(
            location="Delhi",
            check_in="2025-02-01",
            check_out="2025-02-03"
        )
        
        assert result['success'] is True
        assert result['location'] == 'Delhi'
        assert result['nights'] == 2
        assert 'hotels' in result
        assert len(result['hotels']) > 0
    
    def test_search_hotels_with_filters(self, mock_browser_modules):
        """Test hotel search with filters."""
        from modules.agents.hotel_agent import HotelAgent
        
        agent = HotelAgent()
        
        result = agent.search_hotels(
            location="Mumbai",
            check_in="2025-03-01",
            check_out="2025-03-02",
            guests=2,
            rooms=1,
            max_price=5000.0,
            min_rating=4.0
        )
        
        assert result['success'] is True
        
        # Verify filters applied
        for hotel in result['hotels']:
            assert hotel['price_per_night'] <= 5000.0
            assert hotel['rating'] >= 4.0
    
    def test_search_hotels_invalid_dates(self, mock_browser_modules):
        """Test search with invalid date format."""
        from modules.agents.hotel_agent import HotelAgent
        
        agent = HotelAgent()
        
        # Invalid date format should still work (falls back to 1 night)
        result = agent.search_hotels(
            location="Delhi",
            check_in="invalid",
            check_out="also-invalid"
        )
        
        assert result['success'] is True
        assert result['nights'] == 1
    
    def test_search_hotels_includes_recommendation(self, mock_browser_modules):
        """Test that search includes recommendation."""
        from modules.agents.hotel_agent import HotelAgent
        
        agent = HotelAgent()
        
        result = agent.search_hotels(
            location="Bangalore",
            check_in="2025-04-01",
            check_out="2025-04-03"
        )
        
        assert 'recommendation' in result
        assert len(result['recommendation']) > 0
    
    def test_search_hotels_sorted_by_price(self, mock_browser_modules):
        """Test that hotels are sorted by price."""
        from modules.agents.hotel_agent import HotelAgent
        
        agent = HotelAgent()
        
        result = agent.search_hotels(
            location="Chennai",
            check_in="2025-05-01",
            check_out="2025-05-02"
        )
        
        prices = [h['price_per_night'] for h in result['hotels']]
        assert prices == sorted(prices)


class TestGenerateSampleHotels:
    """Tests for sample hotel generation."""
    
    def test_generate_sample_hotels(self, mock_browser_modules):
        """Test sample hotel generation."""
        from modules.agents.hotel_agent import HotelAgent
        
        agent = HotelAgent()
        
        hotels = agent._generate_sample_hotels(
            location="Delhi",
            nights=2,
            guests=2,
            max_price=None,
            min_rating=None
        )
        
        assert isinstance(hotels, list)
        assert len(hotels) == 15
    
    def test_generate_sample_hotels_with_max_price(self, mock_browser_modules):
        """Test sample generation with price limit."""
        from modules.agents.hotel_agent import HotelAgent
        
        agent = HotelAgent()
        
        hotels = agent._generate_sample_hotels(
            location="Mumbai",
            nights=1,
            guests=1,
            max_price=3000.0,
            min_rating=None
        )
        
        # All hotels should respect max price
        for hotel in hotels:
            assert hotel.price_per_night <= 3000.0
    
    def test_generate_sample_hotels_with_min_rating(self, mock_browser_modules):
        """Test sample generation with minimum rating."""
        from modules.agents.hotel_agent import HotelAgent
        
        agent = HotelAgent()
        
        hotels = agent._generate_sample_hotels(
            location="Goa",
            nights=3,
            guests=2,
            max_price=None,
            min_rating=4.0
        )
        
        # All hotels should have minimum rating
        for hotel in hotels:
            assert hotel.rating >= 4.0


class TestHotelToDict:
    """Tests for Hotel to dictionary conversion."""
    
    def test_hotel_to_dict_valid(self, mock_browser_modules):
        """Test converting valid Hotel to dict."""
        from modules.agents.hotel_agent import HotelAgent, Hotel
        
        agent = HotelAgent()
        
        hotel = Hotel(
            name="Test Hotel",
            location="Test Location",
            price_per_night=2500.0,
            total_price=5000.0,
            rating=4.2,
            reviews_count=500,
            amenities=['WiFi', 'Pool'],
            image_url="https://example.com/img.jpg",
            booking_url="https://booking.com/test",
            source="test"
        )
        
        result = agent._hotel_to_dict(hotel)
        
        assert result['name'] == "Test Hotel"
        assert result['price_per_night'] == 2500.0
        assert result['rating'] == 4.2
        assert 'WiFi' in result['amenities']
    
    def test_hotel_to_dict_none(self, mock_browser_modules):
        """Test converting None returns empty dict."""
        from modules.agents.hotel_agent import HotelAgent
        
        agent = HotelAgent()
        
        result = agent._hotel_to_dict(None)
        
        assert result == {}


class TestGetRecommendation:
    """Tests for recommendation generation."""
    
    def test_get_recommendation_empty_list(self, mock_browser_modules):
        """Test recommendation with empty hotel list."""
        from modules.agents.hotel_agent import HotelAgent
        
        agent = HotelAgent()
        
        result = agent._get_recommendation([], None, None)
        
        assert "No hotels found" in result
    
    def test_get_recommendation_with_hotels(self, mock_browser_modules):
        """Test recommendation with hotels."""
        from modules.agents.hotel_agent import HotelAgent, Hotel
        
        agent = HotelAgent()
        
        hotels = [
            Hotel(
                name="Budget Hotel",
                location="Delhi",
                price_per_night=2000.0,
                total_price=4000.0,
                rating=3.5,
                reviews_count=300,
                amenities=['WiFi'],
                image_url="",
                booking_url="",
                source="test"
            ),
            Hotel(
                name="Luxury Hotel",
                location="Delhi",
                price_per_night=5000.0,
                total_price=10000.0,
                rating=4.8,
                reviews_count=1000,
                amenities=['WiFi', 'Pool', 'Spa'],
                image_url="",
                booking_url="",
                source="test"
            ),
        ]
        
        result = agent._get_recommendation(hotels, None, None)
        
        # Should recommend best value
        assert "recommend" in result.lower()


class TestComparePrices:
    """Tests for price comparison."""
    
    def test_compare_prices(self, mock_browser_modules):
        """Test comparing prices across platforms."""
        from modules.agents.hotel_agent import HotelAgent
        
        agent = HotelAgent()
        
        result = agent.compare_prices("Grand Hotel Delhi")
        
        assert result['success'] is True
        assert 'prices' in result
        assert 'Booking.com' in result['prices']
        assert 'Agoda' in result['prices']
        assert 'cheapest' in result
        assert 'savings' in result


class TestBookHotel:
    """Tests for hotel booking."""
    
    def test_book_hotel_without_safety_gate(self, mock_browser_modules):
        """Test booking without safety gate."""
        from modules.agents.hotel_agent import HotelAgent
        
        agent = HotelAgent()
        
        result = agent.book_hotel(
            hotel_name="Grand Hotel",
            check_in="2025-03-01",
            check_out="2025-03-03",
            guest_name="John Doe",
            guest_email="john@example.com",
            guest_phone="+91-9876543210"
        )
        
        assert result['success'] is True
        assert 'booking_id' in result
        assert result['status'] == 'confirmed'
    
    def test_book_hotel_safety_gate_approved(self, mock_browser_modules):
        """Test booking with safety gate approval."""
        from modules.agents.hotel_agent import HotelAgent
        
        mock_safety = MagicMock()
        mock_safety.check_permission.return_value = True
        
        agent = HotelAgent(safety_gate=mock_safety)
        
        result = agent.book_hotel(
            hotel_name="Luxury Hotel",
            check_in="2025-04-01",
            check_out="2025-04-03",
            guest_name="Jane Doe",
            guest_email="jane@example.com",
            guest_phone="+91-9876543210"
        )
        
        assert result['success'] is True
        assert 'LADA-HTL' in result['booking_id']
    
    def test_book_hotel_safety_gate_declined(self, mock_browser_modules):
        """Test booking declined by safety gate."""
        from modules.agents.hotel_agent import HotelAgent
        
        mock_safety = MagicMock()
        mock_safety.check_permission.return_value = False
        
        agent = HotelAgent(safety_gate=mock_safety)
        
        result = agent.book_hotel(
            hotel_name="Expensive Hotel",
            check_in="2025-05-01",
            check_out="2025-05-03",
            guest_name="User",
            guest_email="user@example.com",
            guest_phone="+91-9876543210"
        )
        
        assert result['success'] is False
        assert result['action'] == 'cancelled'


class TestHotelSites:
    """Tests for hotel site configuration."""
    
    def test_hotel_sites_defined(self, mock_browser_modules):
        """Test that hotel sites are defined."""
        from modules.agents.hotel_agent import HotelAgent
        
        assert 'booking' in HotelAgent.HOTEL_SITES
        assert 'agoda' in HotelAgent.HOTEL_SITES
        assert 'makemytrip' in HotelAgent.HOTEL_SITES


class TestSearchWithBrowser:
    """Tests for browser-based search."""
    
    def test_search_with_browser_fallback(self, mock_browser_modules):
        """Test that browser search falls back gracefully."""
        from modules.agents.hotel_agent import HotelAgent
        
        mock_browser = MagicMock()
        mock_browser.navigate = MagicMock(side_effect=Exception("Browser error"))
        
        agent = HotelAgent(browser=mock_browser)
        
        # Should fall back to sample data
        result = agent.search_hotels(
            location="Delhi",
            check_in="2025-06-01",
            check_out="2025-06-03"
        )
        
        assert result['success'] is True
        assert len(result['hotels']) > 0
