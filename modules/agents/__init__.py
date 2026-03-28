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

# New agents for LADA Next-Gen
from .file_agent import FileAgent, get_file_agent
from .code_agent import CodeAgent, get_code_agent
from .robot_agent import RobotAgent, get_robot_agent
from .research_agent import ResearchAgent, get_research_agent

__all__ = [
    'FlightAgent',
    'ProductAgent',
    'EmailAgent',
    'HotelAgent',
    'RestaurantAgent',
    'CalendarAgent',
    # New agents
    'FileAgent',
    'get_file_agent',
    'CodeAgent',
    'get_code_agent',
    'RobotAgent',
    'get_robot_agent',
    'ResearchAgent',
    'get_research_agent',
]
