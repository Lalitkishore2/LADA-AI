"""
LADA v7.0 - Restaurant Agent
Search restaurants and make reservations
"""

import re
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Restaurant:
    """Restaurant search result."""
    name: str
    cuisine: str
    location: str
    rating: float
    reviews_count: int
    price_range: str  # $, $$, $$$, $$$$
    avg_cost_for_two: float
    is_open: bool
    opening_hours: str
    delivery_available: bool
    dine_in_available: bool
    offers: List[str]
    image_url: str
    zomato_url: str
    swiggy_url: str


class RestaurantAgent:
    """
    Restaurant search and reservation agent.
    
    Features:
    - Search restaurants by cuisine, location, budget
    - Get menus and reviews
    - Make reservations
    - Order food delivery
    """
    
    # Cuisines we recognize
    CUISINES = [
        'indian', 'chinese', 'italian', 'mexican', 'thai', 
        'japanese', 'korean', 'mediterranean', 'american',
        'north indian', 'south indian', 'mughlai', 'biryani',
        'pizza', 'burger', 'cafe', 'desserts', 'bakery'
    ]
    
    def __init__(self):
        """Initialize restaurant agent."""
        self.last_search_results: List[Restaurant] = []
    
    def search_restaurants(
        self,
        location: str,
        cuisine: Optional[str] = None,
        max_budget: Optional[float] = None,
        min_rating: Optional[float] = None,
        delivery_only: bool = False,
        open_now: bool = False
    ) -> Dict:
        """
        Search for restaurants.
        
        Args:
            location: City or area name
            cuisine: Preferred cuisine type
            max_budget: Maximum cost for two
            min_rating: Minimum rating (1-5)
            delivery_only: Only show delivery options
            open_now: Only show currently open restaurants
            
        Returns:
            Search results dict
        """
        logger.info(f"[RestaurantAgent] Searching restaurants in {location}")
        
        # Generate sample restaurant data
        restaurants = self._generate_sample_restaurants(
            location, cuisine, max_budget, min_rating
        )
        self.last_search_results = restaurants
        
        # Apply filters
        if max_budget:
            restaurants = [r for r in restaurants if r.avg_cost_for_two <= max_budget]
        if min_rating:
            restaurants = [r for r in restaurants if r.rating >= min_rating]
        if delivery_only:
            restaurants = [r for r in restaurants if r.delivery_available]
        if open_now:
            restaurants = [r for r in restaurants if r.is_open]
        
        # Sort by rating
        restaurants.sort(key=lambda r: r.rating, reverse=True)
        
        # Get recommendations
        cheapest = min(restaurants, key=lambda r: r.avg_cost_for_two) if restaurants else None
        best_rated = max(restaurants, key=lambda r: r.rating) if restaurants else None
        
        return {
            'success': True,
            'location': location,
            'cuisine_filter': cuisine,
            'count': len(restaurants),
            'restaurants': [self._restaurant_to_dict(r) for r in restaurants[:10]],
            'cheapest': self._restaurant_to_dict(cheapest) if cheapest else None,
            'best_rated': self._restaurant_to_dict(best_rated) if best_rated else None,
            'recommendation': self._get_recommendation(restaurants, cuisine),
            'message': f"Found {len(restaurants)} restaurants in {location}"
        }
    
    def _generate_sample_restaurants(
        self,
        location: str,
        cuisine: Optional[str],
        max_budget: Optional[float],
        min_rating: Optional[float]
    ) -> List[Restaurant]:
        """Generate sample restaurant data."""
        import random
        
        restaurant_data = [
            ("Punjabi By Nature", "North Indian", 1200, "$$", ['Unlimited Thali Offer']),
            ("Mainland China", "Chinese", 1500, "$$$", ['20% off on orders above ₹1000']),
            ("Pizza Hut", "Pizza", 800, "$$", ['Buy 1 Get 1 Free']),
            ("Biryani Blues", "Biryani", 600, "$", ['Free Raita with Biryani']),
            ("Domino's Pizza", "Pizza", 700, "$$", ['30% off on Medium Pizza']),
            ("Barbeque Nation", "North Indian", 1800, "$$$", ['Unlimited Lunch ₹799']),
            ("Saravana Bhavan", "South Indian", 500, "$", ['Combo Meal Offer']),
            ("Haldiram's", "Indian", 600, "$$", ['Festive Special Thali']),
            ("KFC", "American", 500, "$$", ['Wednesday Special']),
            ("McDonald's", "Burger", 400, "$", ['McValue Meals']),
            ("Starbucks", "Cafe", 700, "$$$", ['Happy Hours 2-5 PM']),
            ("Cafe Coffee Day", "Cafe", 400, "$$", ['Buy 2 Get 1 Free']),
            ("Paradise Biryani", "Biryani", 800, "$$", ['Jumbo Biryani Offer']),
            ("Taco Bell", "Mexican", 600, "$$", ['Taco Tuesday']),
            ("Subway", "American", 450, "$", ['Sub of the Day ₹199']),
        ]
        
        if cuisine:
            cuisine_lower = cuisine.lower()
            restaurant_data = [r for r in restaurant_data if cuisine_lower in r[1].lower()]
            if not restaurant_data:
                # If no match, create generic ones
                restaurant_data = [
                    (f"The {cuisine.title()} Kitchen", cuisine.title(), 800, "$$", []),
                    (f"{location} {cuisine.title()} House", cuisine.title(), 1000, "$$", []),
                    (f"Royal {cuisine.title()}", cuisine.title(), 1200, "$$$", []),
                ]
        
        restaurants = []
        for i, (name, rest_cuisine, base_cost, price_range, offers) in enumerate(restaurant_data):
            # Vary the values
            cost = base_cost + random.randint(-200, 300)
            if max_budget and cost > max_budget:
                cost = max_budget - random.randint(50, 200)
            cost = max(300, cost)
            
            rating = round(random.uniform(3.5, 4.9), 1)
            if min_rating and rating < min_rating:
                rating = min_rating + random.uniform(0, 0.3)
            rating = min(5.0, rating)
            
            is_open = random.random() > 0.2  # 80% chance open
            
            restaurant = Restaurant(
                name=name,
                cuisine=rest_cuisine,
                location=f"{location}, Near Metro Station" if i % 2 == 0 else f"{location}, Main Road",
                rating=rating,
                reviews_count=random.randint(100, 10000),
                price_range=price_range,
                avg_cost_for_two=cost,
                is_open=is_open,
                opening_hours="11:00 AM - 11:00 PM",
                delivery_available=random.random() > 0.1,  # 90% have delivery
                dine_in_available=random.random() > 0.2,  # 80% have dine-in
                offers=offers,
                image_url=f"https://example.com/restaurant_{i}.jpg",
                zomato_url=f"https://zomato.com/{name.lower().replace(' ', '-')}",
                swiggy_url=f"https://swiggy.com/{name.lower().replace(' ', '-')}"
            )
            restaurants.append(restaurant)
        
        return restaurants
    
    def _restaurant_to_dict(self, restaurant: Restaurant) -> Dict:
        """Convert Restaurant to dictionary."""
        if not restaurant:
            return {}
        return {
            'name': restaurant.name,
            'cuisine': restaurant.cuisine,
            'location': restaurant.location,
            'rating': restaurant.rating,
            'reviews_count': restaurant.reviews_count,
            'price_range': restaurant.price_range,
            'avg_cost_for_two': restaurant.avg_cost_for_two,
            'is_open': restaurant.is_open,
            'opening_hours': restaurant.opening_hours,
            'delivery_available': restaurant.delivery_available,
            'dine_in_available': restaurant.dine_in_available,
            'offers': restaurant.offers,
            'zomato_url': restaurant.zomato_url,
            'swiggy_url': restaurant.swiggy_url
        }
    
    def _get_recommendation(self, restaurants: List[Restaurant], cuisine: Optional[str]) -> str:
        """Generate recommendation message."""
        if not restaurants:
            return "No restaurants found. Try a different location or cuisine."
        
        top = restaurants[0]
        msg = f"I recommend **{top.name}** "
        msg += f"({top.cuisine}) - ★{top.rating}. "
        msg += f"Cost for two: ₹{top.avg_cost_for_two:.0f}. "
        if top.offers:
            msg += f"Current offer: {top.offers[0]}."
        
        return msg
    
    def make_reservation(
        self,
        restaurant_name: str,
        date: str,
        time: str,
        party_size: int,
        guest_name: str,
        guest_phone: str,
        special_requests: str = ""
    ) -> Dict:
        """
        Make a restaurant reservation.
        
        Args:
            restaurant_name: Restaurant to book
            date: Reservation date (YYYY-MM-DD)
            time: Reservation time (HH:MM)
            party_size: Number of guests
            guest_name: Guest's name
            guest_phone: Guest's phone
            special_requests: Any special requests
            
        Returns:
            Reservation result
        """
        # Generate confirmation
        confirmation_id = f"LADA-RES-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        return {
            'success': True,
            'confirmation_id': confirmation_id,
            'restaurant': restaurant_name,
            'date': date,
            'time': time,
            'party_size': party_size,
            'guest_name': guest_name,
            'status': 'confirmed',
            'message': f"Reservation confirmed at {restaurant_name} for {party_size} guests on {date} at {time}. Confirmation: {confirmation_id}",
            'note': '(This is a simulation - no actual reservation was made)'
        }
    
    def order_food(
        self,
        restaurant_name: str,
        items: List[Dict],
        delivery_address: str,
        payment_method: str = 'online'
    ) -> Dict:
        """
        Order food for delivery.
        
        Args:
            restaurant_name: Restaurant to order from
            items: List of items [{name, quantity, price}]
            delivery_address: Delivery address
            payment_method: Payment method
            
        Returns:
            Order result
        """
        # Calculate totals
        subtotal = sum(item.get('price', 0) * item.get('quantity', 1) for item in items)
        delivery_fee = 40
        taxes = subtotal * 0.05
        total = subtotal + delivery_fee + taxes
        
        order_id = f"LADA-ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        return {
            'success': True,
            'order_id': order_id,
            'restaurant': restaurant_name,
            'items': items,
            'subtotal': subtotal,
            'delivery_fee': delivery_fee,
            'taxes': taxes,
            'total': total,
            'delivery_address': delivery_address,
            'estimated_time': '30-40 mins',
            'status': 'confirmed',
            'message': f"Order placed at {restaurant_name}. Total: ₹{total:.0f}. Expected in 30-40 mins.",
            'note': '(This is a simulation - no actual order was placed)'
        }
    
    def get_menu(self, restaurant_name: str) -> Dict:
        """Get restaurant menu."""
        import random
        
        menu_items = [
            {'category': 'Starters', 'items': [
                {'name': 'Paneer Tikka', 'price': 280, 'veg': True},
                {'name': 'Chicken Tikka', 'price': 320, 'veg': False},
                {'name': 'Veg Spring Roll', 'price': 180, 'veg': True},
            ]},
            {'category': 'Main Course', 'items': [
                {'name': 'Dal Makhani', 'price': 250, 'veg': True},
                {'name': 'Butter Chicken', 'price': 350, 'veg': False},
                {'name': 'Paneer Butter Masala', 'price': 280, 'veg': True},
                {'name': 'Biryani', 'price': 320, 'veg': False},
            ]},
            {'category': 'Breads', 'items': [
                {'name': 'Butter Naan', 'price': 60, 'veg': True},
                {'name': 'Garlic Naan', 'price': 70, 'veg': True},
                {'name': 'Tandoori Roti', 'price': 40, 'veg': True},
            ]},
            {'category': 'Beverages', 'items': [
                {'name': 'Lassi', 'price': 100, 'veg': True},
                {'name': 'Masala Chai', 'price': 50, 'veg': True},
                {'name': 'Cold Coffee', 'price': 120, 'veg': True},
            ]},
            {'category': 'Desserts', 'items': [
                {'name': 'Gulab Jamun', 'price': 80, 'veg': True},
                {'name': 'Rasmalai', 'price': 100, 'veg': True},
                {'name': 'Ice Cream', 'price': 120, 'veg': True},
            ]}
        ]
        
        return {
            'success': True,
            'restaurant': restaurant_name,
            'menu': menu_items,
            'total_items': sum(len(cat['items']) for cat in menu_items),
            'message': f"Menu for {restaurant_name}"
        }
    
    def process(self, query: str) -> Dict:
        """
        Process a natural language restaurant query.
        
        Args:
            query: Natural language query
            
        Returns:
            Result dict
        """
        query_lower = query.lower()
        
        # Extract location
        location = None
        location_patterns = [
            r'(?:in|at|near)\s+([a-zA-Z\s]+?)(?:\s+for|\s+serving|\s*$)',
            r'restaurants?\s+(?:in|at)\s+([a-zA-Z\s]+)',
        ]
        for pattern in location_patterns:
            match = re.search(pattern, query_lower)
            if match:
                location = match.group(1).strip().title()
                break
        
        if not location:
            location = 'Delhi'  # Default
        
        # Extract cuisine
        cuisine = None
        for c in self.CUISINES:
            if c in query_lower:
                cuisine = c.title()
                break
        
        # Extract budget
        max_budget = None
        budget_match = re.search(r'(?:under|below|budget)\s*(?:rs\.?|₹)?\s*(\d+)', query_lower)
        if budget_match:
            max_budget = float(budget_match.group(1))
        
        # Extract rating
        min_rating = None
        rating_match = re.search(r'(?:rating|rated)\s*(?:above|over|minimum)?\s*(\d+(?:\.\d+)?)', query_lower)
        if rating_match:
            min_rating = float(rating_match.group(1))
        
        # Check for delivery
        delivery_only = 'delivery' in query_lower
        
        # Search
        return self.search_restaurants(
            location=location,
            cuisine=cuisine,
            max_budget=max_budget,
            min_rating=min_rating,
            delivery_only=delivery_only
        )


# ============================================================
# EXAMPLE USAGE
# ============================================================
if __name__ == "__main__":
    print("🚀 Testing RestaurantAgent...")
    
    agent = RestaurantAgent()
    
    # Test search
    print("\n🍽️ Searching restaurants...")
    result = agent.search_restaurants(
        location="Mumbai",
        cuisine="Indian",
        max_budget=1000,
        min_rating=4.0
    )
    
    print(f"  Found: {result['count']} restaurants")
    if result['best_rated']:
        print(f"  Best: {result['best_rated']['name']} - ★{result['best_rated']['rating']}")
    print(f"  Recommendation: {result['recommendation']}")
    
    # Test menu
    print("\n📋 Getting menu...")
    menu = agent.get_menu("Punjabi By Nature")
    print(f"  Items: {menu['total_items']}")
    
    # Test reservation
    print("\n📅 Making reservation...")
    reservation = agent.make_reservation(
        restaurant_name="Punjabi By Nature",
        date="2025-01-15",
        time="19:30",
        party_size=4,
        guest_name="Test User",
        guest_phone="9876543210"
    )
    print(f"  {reservation['message']}")
    
    # Test natural language
    print("\n🗣️ Testing natural language...")
    result = agent.process("Find Chinese restaurants in Delhi under 1000")
    print(f"  {result['message']}")
    
    print("\n✅ RestaurantAgent test complete!")
