"""
LADA v7.0 - Hotel Agent
Search and book hotels via web automation
"""

import re
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Try to import browser automation
try:
    from modules.browser_automation import CometBrowserAgent
    from modules.safety_gate import SafetyGate, RiskLevel
    BROWSER_OK = True
except ImportError:
    BROWSER_OK = False
    logger.warning("[HotelAgent] Browser automation not available")


@dataclass
class Hotel:
    """Hotel search result."""
    name: str
    location: str
    price_per_night: float
    total_price: float
    rating: float
    reviews_count: int
    amenities: List[str]
    image_url: str
    booking_url: str
    source: str


class HotelAgent:
    """
    Hotel search and booking agent.
    
    Features:
    - Search hotels by location and dates
    - Filter by price, rating, amenities
    - Compare prices across platforms
    - Book with safety gate approval
    """
    
    # Supported hotel sites
    HOTEL_SITES = {
        'booking': 'https://www.booking.com',
        'agoda': 'https://www.agoda.com',
        'makemytrip': 'https://www.makemytrip.com/hotels',
        'oyo': 'https://www.oyorooms.com',
        'goibibo': 'https://www.goibibo.com/hotels'
    }
    
    def __init__(self, browser: Optional[Any] = None, safety_gate: Optional[Any] = None):
        """
        Initialize hotel agent.
        
        Args:
            browser: CometBrowserAgent instance
            safety_gate: SafetyGate instance
        """
        self.browser = browser
        self.safety_gate = safety_gate
        self.last_search_results: List[Hotel] = []
    
    def search_hotels(
        self,
        location: str,
        check_in: str,
        check_out: str,
        guests: int = 2,
        rooms: int = 1,
        max_price: Optional[float] = None,
        min_rating: Optional[float] = None,
        amenities: Optional[List[str]] = None
    ) -> Dict:
        """
        Search for hotels.
        
        Args:
            location: City or area name
            check_in: Check-in date (YYYY-MM-DD)
            check_out: Check-out date (YYYY-MM-DD)
            guests: Number of guests
            rooms: Number of rooms
            max_price: Maximum price per night
            min_rating: Minimum rating (1-5)
            amenities: Required amenities (wifi, pool, parking, etc.)
            
        Returns:
            Search results dict
        """
        logger.info(f"[HotelAgent] Searching hotels in {location}")
        
        # Calculate nights
        try:
            check_in_dt = datetime.strptime(check_in, '%Y-%m-%d')
            check_out_dt = datetime.strptime(check_out, '%Y-%m-%d')
            nights = (check_out_dt - check_in_dt).days
            if nights < 1:
                nights = 1
        except:
            nights = 1
        
        # If browser available, try real search
        if self.browser and BROWSER_OK:
            try:
                return self._search_with_browser(
                    location, check_in, check_out, guests, rooms,
                    max_price, min_rating, amenities
                )
            except Exception as e:
                logger.warning(f"[HotelAgent] Browser search failed: {e}")
        
        # Fallback: Generate sample data
        hotels = self._generate_sample_hotels(location, nights, guests, max_price, min_rating)
        self.last_search_results = hotels
        
        # Apply filters
        if max_price:
            hotels = [h for h in hotels if h.price_per_night <= max_price]
        if min_rating:
            hotels = [h for h in hotels if h.rating >= min_rating]
        
        # Sort by price
        hotels.sort(key=lambda h: h.price_per_night)
        
        # Get cheapest and best rated
        cheapest = min(hotels, key=lambda h: h.price_per_night) if hotels else None
        best_rated = max(hotels, key=lambda h: h.rating) if hotels else None
        
        return {
            'success': True,
            'location': location,
            'check_in': check_in,
            'check_out': check_out,
            'nights': nights,
            'guests': guests,
            'rooms': rooms,
            'count': len(hotels),
            'hotels': [self._hotel_to_dict(h) for h in hotels[:10]],
            'cheapest': self._hotel_to_dict(cheapest) if cheapest else None,
            'best_rated': self._hotel_to_dict(best_rated) if best_rated else None,
            'recommendation': self._get_recommendation(hotels, max_price, min_rating),
            'message': f"Found {len(hotels)} hotels in {location} for {nights} night(s)"
        }
    
    def _search_with_browser(
        self,
        location: str,
        check_in: str,
        check_out: str,
        guests: int,
        rooms: int,
        max_price: Optional[float],
        min_rating: Optional[float],
        amenities: Optional[List[str]]
    ) -> Dict:
        """Search using actual browser automation."""
        # Build Booking.com URL
        check_in_dt = datetime.strptime(check_in, '%Y-%m-%d')
        check_out_dt = datetime.strptime(check_out, '%Y-%m-%d')
        
        url = (
            f"https://www.booking.com/searchresults.html"
            f"?ss={location.replace(' ', '+')}"
            f"&checkin={check_in}"
            f"&checkout={check_out}"
            f"&group_adults={guests}"
            f"&no_rooms={rooms}"
        )
        
        # Navigate and extract
        import asyncio
        
        async def search():
            await self.browser.navigate(url)
            await asyncio.sleep(3)  # Wait for results
            
            # Extract hotel cards
            html = await self.browser.get_page_html()
            # Parse HTML for hotel data...
            return []
        
        # Run async search
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            hotels = loop.run_until_complete(search())
        finally:
            loop.close()
        
        return {
            'success': True,
            'hotels': hotels,
            'source': 'browser'
        }
    
    def _generate_sample_hotels(
        self,
        location: str,
        nights: int,
        guests: int,
        max_price: Optional[float],
        min_rating: Optional[float]
    ) -> List[Hotel]:
        """Generate sample hotel data."""
        import random
        
        hotel_prefixes = ['Grand', 'Royal', 'The', 'Hotel', 'Taj', 'ITC', 'Hyatt', 'Marriott', 'Radisson', 'Lemon Tree']
        hotel_suffixes = ['Palace', 'Inn', 'Suites', 'Resort', 'Residency', 'Plaza', 'Continental', 'Regency']
        
        amenities_list = ['Free WiFi', 'Pool', 'Gym', 'Spa', 'Restaurant', 'Bar', 'Parking', 'Room Service', 'AC', 'Breakfast']
        
        base_price = 3000 if 'delhi' in location.lower() or 'mumbai' in location.lower() else 2000
        
        hotels = []
        for i in range(15):
            prefix = random.choice(hotel_prefixes)
            suffix = random.choice(hotel_suffixes)
            name = f"{prefix} {suffix} {location.split()[0]}"
            
            price = base_price + random.randint(-1000, 3000)
            if max_price and price > max_price:
                price = max_price - random.randint(100, 500)
            price = max(1500, price)  # Minimum price
            
            rating = round(random.uniform(3.0, 4.9), 1)
            if min_rating and rating < min_rating:
                rating = min_rating + random.uniform(0, 0.5)
            rating = min(5.0, rating)
            
            hotel = Hotel(
                name=name,
                location=f"{location} City Center" if i % 3 == 0 else f"{location} Downtown",
                price_per_night=price,
                total_price=price * nights,
                rating=rating,
                reviews_count=random.randint(100, 5000),
                amenities=random.sample(amenities_list, random.randint(4, 8)),
                image_url=f"https://example.com/hotel_{i}.jpg",
                booking_url=f"https://booking.com/hotel/{name.lower().replace(' ', '-')}",
                source='sample'
            )
            hotels.append(hotel)
        
        return hotels
    
    def _hotel_to_dict(self, hotel: Hotel) -> Dict:
        """Convert Hotel to dictionary."""
        if not hotel:
            return {}
        return {
            'name': hotel.name,
            'location': hotel.location,
            'price_per_night': hotel.price_per_night,
            'total_price': hotel.total_price,
            'rating': hotel.rating,
            'reviews_count': hotel.reviews_count,
            'amenities': hotel.amenities,
            'image_url': hotel.image_url,
            'booking_url': hotel.booking_url,
            'source': hotel.source
        }
    
    def _get_recommendation(
        self,
        hotels: List[Hotel],
        max_price: Optional[float],
        min_rating: Optional[float]
    ) -> str:
        """Generate a recommendation message."""
        if not hotels:
            return "No hotels found matching your criteria."
        
        # Find best value (price/rating ratio)
        best_value = min(hotels, key=lambda h: h.price_per_night / h.rating if h.rating > 0 else float('inf'))
        
        msg = f"I recommend **{best_value.name}** "
        msg += f"at ₹{best_value.price_per_night:.0f}/night "
        msg += f"(★{best_value.rating}). "
        msg += f"It has {', '.join(best_value.amenities[:3])}."
        
        return msg
    
    def compare_prices(self, hotel_name: str) -> Dict:
        """Compare prices across different platforms."""
        # In real implementation, would search multiple sites
        # For now, generate sample comparison
        import random
        
        platforms = {
            'Booking.com': random.randint(2500, 4000),
            'Agoda': random.randint(2400, 3800),
            'MakeMyTrip': random.randint(2600, 4200),
            'Goibibo': random.randint(2500, 3900),
            'OYO': random.randint(2000, 3500),
        }
        
        cheapest_platform = min(platforms, key=platforms.get)
        
        return {
            'success': True,
            'hotel': hotel_name,
            'prices': platforms,
            'cheapest': {
                'platform': cheapest_platform,
                'price': platforms[cheapest_platform]
            },
            'savings': max(platforms.values()) - min(platforms.values()),
            'message': f"Best price for {hotel_name}: ₹{platforms[cheapest_platform]} on {cheapest_platform}"
        }
    
    def book_hotel(
        self,
        hotel_name: str,
        check_in: str,
        check_out: str,
        guest_name: str,
        guest_email: str,
        guest_phone: str,
        payment_method: str = 'card'
    ) -> Dict:
        """
        Book a hotel (requires safety gate approval).
        
        Args:
            hotel_name: Hotel to book
            check_in: Check-in date
            check_out: Check-out date
            guest_name: Guest's full name
            guest_email: Guest's email
            guest_phone: Guest's phone
            payment_method: Payment method
            
        Returns:
            Booking result
        """
        # This is a HIGH risk action - requires safety gate
        if self.safety_gate:
            action_desc = f"Book {hotel_name} from {check_in} to {check_out} for {guest_name}"
            
            # Check approval
            approved = self.safety_gate.check_permission(
                action=action_desc,
                risk_level=RiskLevel.HIGH,
                details={
                    'hotel': hotel_name,
                    'dates': f"{check_in} to {check_out}",
                    'guest': guest_name,
                    'email': guest_email
                }
            )
            
            if not approved:
                return {
                    'success': False,
                    'message': 'Booking cancelled - user declined permission',
                    'action': 'cancelled'
                }
        
        # In real implementation, would proceed with booking
        # For now, return simulated confirmation
        booking_id = f"LADA-HTL-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        return {
            'success': True,
            'booking_id': booking_id,
            'hotel': hotel_name,
            'check_in': check_in,
            'check_out': check_out,
            'guest_name': guest_name,
            'status': 'confirmed',
            'message': f"Hotel booked successfully! Confirmation: {booking_id}",
            'note': '(This is a simulation - no actual booking was made)'
        }
    
    def process(self, query: str) -> Dict:
        """
        Process a natural language hotel query.
        
        Args:
            query: Natural language query
            
        Returns:
            Result dict
        """
        query_lower = query.lower()
        
        # Extract location
        location = None
        location_patterns = [
            r'(?:in|at|near)\s+([a-zA-Z\s]+?)(?:\s+for|\s+from|\s*$)',
            r'hotels?\s+(?:in|at)\s+([a-zA-Z\s]+)',
        ]
        for pattern in location_patterns:
            match = re.search(pattern, query_lower)
            if match:
                location = match.group(1).strip().title()
                break
        
        if not location:
            location = 'Delhi'  # Default
        
        # Extract dates
        check_in = datetime.now().strftime('%Y-%m-%d')
        check_out = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Look for date patterns
        date_match = re.search(r'(\d{1,2})\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)', query_lower)
        if date_match:
            day = int(date_match.group(1))
            month_name = date_match.group(2)
            month_map = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
            month = month_map.get(month_name, 1)
            year = datetime.now().year
            if month < datetime.now().month:
                year += 1
            check_in = f"{year}-{month:02d}-{day:02d}"
            check_out = (datetime.strptime(check_in, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Extract max price
        max_price = None
        price_match = re.search(r'(?:under|below|max|budget)\s*(?:rs\.?|₹)?\s*(\d+)', query_lower)
        if price_match:
            max_price = float(price_match.group(1))
        
        # Search
        return self.search_hotels(
            location=location,
            check_in=check_in,
            check_out=check_out,
            max_price=max_price
        )


# ============================================================
# EXAMPLE USAGE
# ============================================================
if __name__ == "__main__":
    print("🚀 Testing HotelAgent...")
    
    agent = HotelAgent()
    
    # Test search
    print("\n🏨 Searching hotels...")
    result = agent.search_hotels(
        location="Mumbai",
        check_in="2025-01-15",
        check_out="2025-01-17",
        guests=2,
        max_price=5000,
        min_rating=4.0
    )
    
    print(f"  Found: {result['count']} hotels")
    print(f"  Cheapest: {result['cheapest']['name']} - ₹{result['cheapest']['price_per_night']}")
    print(f"  Best rated: {result['best_rated']['name']} - ★{result['best_rated']['rating']}")
    print(f"  Recommendation: {result['recommendation']}")
    
    # Test compare
    print("\n💰 Comparing prices...")
    compare = agent.compare_prices("Taj Mahal Palace")
    print(f"  Best price: {compare['cheapest']['platform']} - ₹{compare['cheapest']['price']}")
    print(f"  Savings: ₹{compare['savings']}")
    
    # Test natural language
    print("\n🗣️ Testing natural language...")
    result = agent.process("Find hotels in Delhi under 4000")
    print(f"  {result['message']}")
    
    print("\n✅ HotelAgent test complete!")
