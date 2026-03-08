"""
LADA v7.0 - Agents Package
Specialized automation agents for different tasks
"""

from .flight_agent import FlightAgent
from .product_agent import ProductAgent
from .email_agent import EmailAgent
from .hotel_agent import HotelAgent
from .restaurant_agent import RestaurantAgent
from .calendar_agent import CalendarAgent

__all__ = [
    'FlightAgent',
    'ProductAgent',
    'EmailAgent',
    'HotelAgent',
    'RestaurantAgent',
    'CalendarAgent'
]
