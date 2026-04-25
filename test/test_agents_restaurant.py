"""
Comprehensive tests for modules/agents/restaurant_agent.py
Tests RestaurantAgent class with all methods.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


class TestRestaurantDataclass:
    """Tests for Restaurant dataclass."""
    
    def test_restaurant_creation(self):
        """Test creating a Restaurant instance."""
        from modules.agents.restaurant_agent import Restaurant
        
        restaurant = Restaurant(
            name="Test Restaurant",
            cuisine="Indian",
            location="Delhi, Main Road",
            rating=4.5,
            reviews_count=1200,
            price_range="$$",
            avg_cost_for_two=800.0,
            is_open=True,
            opening_hours="11:00 AM - 11:00 PM",
            delivery_available=True,
            dine_in_available=True,
            offers=['20% off'],
            image_url="https://example.com/img.jpg",
            zomato_url="https://zomato.com/test",
            swiggy_url="https://swiggy.com/test"
        )
        
        assert restaurant.name == "Test Restaurant"
        assert restaurant.cuisine == "Indian"
        assert restaurant.rating == 4.5
        assert restaurant.is_open is True


class TestRestaurantAgentInit:
    """Tests for RestaurantAgent initialization."""
    
    def test_init_defaults(self):
        """Test RestaurantAgent initialization."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        assert agent.last_search_results == []
    
    def test_cuisines_defined(self):
        """Test that cuisines list is defined."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        assert len(RestaurantAgent.CUISINES) > 0
        assert 'indian' in RestaurantAgent.CUISINES
        assert 'chinese' in RestaurantAgent.CUISINES
        assert 'pizza' in RestaurantAgent.CUISINES


class TestSearchRestaurants:
    """Tests for restaurant search functionality."""
    
    def test_search_basic(self):
        """Test basic restaurant search."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        result = agent.search_restaurants(location="Delhi")
        
        assert result['success'] is True
        assert result['location'] == 'Delhi'
        assert 'restaurants' in result
        assert len(result['restaurants']) > 0
    
    def test_search_with_cuisine(self):
        """Test search with cuisine filter."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        result = agent.search_restaurants(location="Mumbai", cuisine="Chinese")
        
        assert result['success'] is True
        assert result['cuisine_filter'] == 'Chinese'
    
    def test_search_with_budget(self):
        """Test search with budget filter."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        result = agent.search_restaurants(location="Bangalore", max_budget=600)
        
        for restaurant in result['restaurants']:
            assert restaurant['avg_cost_for_two'] <= 600
    
    def test_search_with_min_rating(self):
        """Test search with minimum rating filter."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        result = agent.search_restaurants(location="Chennai", min_rating=4.0)
        
        for restaurant in result['restaurants']:
            assert restaurant['rating'] >= 4.0
    
    def test_search_delivery_only(self):
        """Test search with delivery only filter."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        result = agent.search_restaurants(location="Hyderabad", delivery_only=True)
        
        for restaurant in result['restaurants']:
            assert restaurant['delivery_available'] is True
    
    def test_search_open_now(self):
        """Test search with open now filter."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        result = agent.search_restaurants(location="Pune", open_now=True)
        
        for restaurant in result['restaurants']:
            assert restaurant['is_open'] is True
    
    def test_search_sorted_by_rating(self):
        """Test that results are sorted by rating."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        result = agent.search_restaurants(location="Delhi")
        
        ratings = [r['rating'] for r in result['restaurants']]
        assert ratings == sorted(ratings, reverse=True)
    
    def test_search_includes_cheapest(self):
        """Test that search includes cheapest option."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        result = agent.search_restaurants(location="Mumbai")
        
        assert 'cheapest' in result
        assert result['cheapest'] is not None
    
    def test_search_includes_best_rated(self):
        """Test that search includes best rated option."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        result = agent.search_restaurants(location="Bangalore")
        
        assert 'best_rated' in result
        assert result['best_rated'] is not None
    
    def test_search_includes_recommendation(self):
        """Test that search includes recommendation."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        result = agent.search_restaurants(location="Chennai")
        
        assert 'recommendation' in result
        assert len(result['recommendation']) > 0


class TestGenerateSampleRestaurants:
    """Tests for sample restaurant generation."""
    
    def test_generate_sample_restaurants(self):
        """Test sample restaurant generation."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        restaurants = agent._generate_sample_restaurants(
            location="Delhi",
            cuisine=None,
            max_budget=None,
            min_rating=None
        )
        
        assert isinstance(restaurants, list)
        assert len(restaurants) > 0
    
    def test_generate_with_cuisine_filter(self):
        """Test sample generation with cuisine filter."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        restaurants = agent._generate_sample_restaurants(
            location="Mumbai",
            cuisine="Pizza",
            max_budget=None,
            min_rating=None
        )
        
        # Should have pizza-related restaurants
        assert len(restaurants) > 0
    
    def test_generate_with_unknown_cuisine(self):
        """Test sample generation with unknown cuisine creates generic entries."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        restaurants = agent._generate_sample_restaurants(
            location="Delhi",
            cuisine="Ethiopian",  # Not in default list
            max_budget=None,
            min_rating=None
        )
        
        # Should still return restaurants
        assert len(restaurants) > 0
    
    def test_generate_respects_max_budget(self):
        """Test that max budget is respected."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        restaurants = agent._generate_sample_restaurants(
            location="Chennai",
            cuisine=None,
            max_budget=500,
            min_rating=None
        )
        
        for restaurant in restaurants:
            assert restaurant.avg_cost_for_two <= 500
    
    def test_generate_respects_min_rating(self):
        """Test that min rating is respected."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        restaurants = agent._generate_sample_restaurants(
            location="Hyderabad",
            cuisine=None,
            max_budget=None,
            min_rating=4.5
        )
        
        for restaurant in restaurants:
            assert restaurant.rating >= 4.5


class TestRestaurantToDict:
    """Tests for Restaurant to dictionary conversion."""
    
    def test_restaurant_to_dict_valid(self):
        """Test converting valid Restaurant to dict."""
        from modules.agents.restaurant_agent import RestaurantAgent, Restaurant
        
        agent = RestaurantAgent()
        
        restaurant = Restaurant(
            name="Test Restaurant",
            cuisine="Indian",
            location="Delhi",
            rating=4.2,
            reviews_count=500,
            price_range="$$",
            avg_cost_for_two=600.0,
            is_open=True,
            opening_hours="10:00 AM - 10:00 PM",
            delivery_available=True,
            dine_in_available=True,
            offers=['Special Offer'],
            image_url="https://example.com/img.jpg",
            zomato_url="https://zomato.com/test",
            swiggy_url="https://swiggy.com/test"
        )
        
        result = agent._restaurant_to_dict(restaurant)
        
        assert result['name'] == "Test Restaurant"
        assert result['cuisine'] == "Indian"
        assert result['rating'] == 4.2
        assert result['is_open'] is True


class TestGetRecommendation:
    """Tests for recommendation generation."""
    
    def test_recommendation_empty_list(self):
        """Test recommendation with empty restaurant list."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        result = agent._get_recommendation([], None)
        
        assert "No restaurants found" in result
    
    def test_recommendation_with_restaurants(self):
        """Test recommendation with restaurants."""
        from modules.agents.restaurant_agent import RestaurantAgent, Restaurant
        
        agent = RestaurantAgent()
        
        restaurants = [
            Restaurant(
                name="Top Restaurant",
                cuisine="Indian",
                location="Delhi",
                rating=4.8,
                reviews_count=1000,
                price_range="$$",
                avg_cost_for_two=800.0,
                is_open=True,
                opening_hours="11:00 AM - 11:00 PM",
                delivery_available=True,
                dine_in_available=True,
                offers=['20% off'],
                image_url="",
                zomato_url="",
                swiggy_url=""
            )
        ]
        
        result = agent._get_recommendation(restaurants, None)
        
        assert "recommend" in result.lower()
        assert "Top Restaurant" in result
        assert "20% off" in result


class TestMakeReservation:
    """Tests for restaurant reservation."""
    
    def test_make_reservation_success(self):
        """Test successful reservation."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        result = agent.make_reservation(
            restaurant_name="Test Restaurant",
            date="2025-03-15",
            time="19:00",
            party_size=4,
            guest_name="John Doe",
            guest_phone="+91-9876543210"
        )
        
        assert result['success'] is True
        assert 'confirmation_id' in result
        assert 'LADA-RES' in result['confirmation_id']
        assert result['status'] == 'confirmed'
        assert result['party_size'] == 4
    
    def test_make_reservation_with_special_requests(self):
        """Test reservation with special requests."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        result = agent.make_reservation(
            restaurant_name="Fine Dining",
            date="2025-04-01",
            time="20:00",
            party_size=2,
            guest_name="Jane Doe",
            guest_phone="+91-9876543210",
            special_requests="Window seat please"
        )
        
        assert result['success'] is True


class TestOrderFood:
    """Tests for food ordering."""
    
    def test_order_food_success(self):
        """Test successful food order."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        items = [
            {'name': 'Butter Chicken', 'quantity': 2, 'price': 350},
            {'name': 'Naan', 'quantity': 4, 'price': 60},
        ]
        
        result = agent.order_food(
            restaurant_name="Test Restaurant",
            items=items,
            delivery_address="123 Test Street, Delhi"
        )
        
        assert result['success'] is True
        assert 'order_id' in result
        assert 'LADA-ORD' in result['order_id']
        assert result['subtotal'] == 2*350 + 4*60  # 940
        assert result['delivery_fee'] == 40
        assert result['status'] == 'confirmed'
    
    def test_order_food_calculates_total(self):
        """Test order total calculation."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        items = [
            {'name': 'Pizza', 'quantity': 1, 'price': 500},
        ]
        
        result = agent.order_food(
            restaurant_name="Pizza Place",
            items=items,
            delivery_address="456 Test Avenue"
        )
        
        subtotal = 500
        delivery_fee = 40
        taxes = subtotal * 0.05
        expected_total = subtotal + delivery_fee + taxes
        
        assert result['subtotal'] == subtotal
        assert result['delivery_fee'] == delivery_fee
        assert result['taxes'] == taxes
        assert result['total'] == expected_total


class TestGetMenu:
    """Tests for getting restaurant menu."""
    
    def test_get_menu_success(self):
        """Test getting menu."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        result = agent.get_menu("Test Restaurant")
        
        assert result['success'] is True
        assert 'menu' in result
        assert len(result['menu']) > 0
    
    def test_get_menu_has_categories(self):
        """Test menu has categories."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        result = agent.get_menu("Indian Restaurant")
        
        categories = [cat['category'] for cat in result['menu']]
        assert 'Starters' in categories
        assert 'Main Course' in categories
        assert 'Beverages' in categories
    
    def test_get_menu_items_have_prices(self):
        """Test menu items have prices."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        result = agent.get_menu("Test Restaurant")
        
        for category in result['menu']:
            for item in category['items']:
                assert 'name' in item
                assert 'price' in item
                assert item['price'] > 0


class TestProcess:
    """Tests for natural language query processing."""
    
    def test_process_extracts_location(self):
        """Test processing extracts location."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        result = agent.process("Find restaurants in Mumbai")
        
        assert result['success'] is True
        assert result['location'] == 'Mumbai'
    
    def test_process_extracts_cuisine(self):
        """Test processing extracts cuisine."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        result = agent.process("Find chinese restaurants in Delhi")
        
        assert result['cuisine_filter'] == 'Chinese'
    
    def test_process_extracts_budget(self):
        """Test processing extracts budget."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        result = agent.process("Restaurants in Bangalore under 500")
        
        # Should filter by budget
        for restaurant in result['restaurants']:
            assert restaurant['avg_cost_for_two'] <= 500
    
    def test_process_default_location(self):
        """Test processing uses default location if none specified."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        result = agent.process("Find good restaurants")
        
        # Should use default location (Delhi)
        assert result['success'] is True
        assert result['location'] == 'Delhi'


class TestLastSearchResults:
    """Tests for last search results storage."""
    
    def test_search_stores_results(self):
        """Test that search stores results."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        # Initially empty
        assert agent.last_search_results == []
        
        # After search
        agent.search_restaurants(location="Delhi")
        
        assert len(agent.last_search_results) > 0
    
    def test_search_replaces_previous_results(self):
        """Test that new search replaces previous results."""
        from modules.agents.restaurant_agent import RestaurantAgent
        
        agent = RestaurantAgent()
        
        # First search
        agent.search_restaurants(location="Delhi")
        first_results = agent.last_search_results.copy()
        
        # Second search
        agent.search_restaurants(location="Mumbai")
        second_results = agent.last_search_results
        
        # Results should be different
        assert first_results != second_results
