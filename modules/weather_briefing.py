"""
LADA v7.0 - Weather & Morning Briefing Module
Get weather info and provide morning briefings
"""

import os
import logging
import requests
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class WeatherBriefing:
    """
    Weather information and morning briefings for LADA
    Uses OpenWeatherMap API (free tier: 1000 calls/day)
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv('OPENWEATHER_API_KEY', '')
        self.base_url = "https://api.openweathermap.org/data/2.5"
        
        # Default location (Chennai, India)
        self.default_city = os.getenv('WEATHER_CITY', 'Chennai')
        self.default_country = os.getenv('WEATHER_COUNTRY', 'IN')
        
        # Cache to avoid repeated API calls
        self.cache_file = Path('config/weather_cache.json')
        self.cache = self._load_cache()
        
        # Track if briefing was given today
        self.briefing_file = Path('config/last_briefing.txt')
    
    def _load_cache(self) -> Dict:
        """Load cached weather data"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {}
    
    def _save_cache(self):
        """Save weather cache"""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f)
        except:
            pass
    
    def get_weather(self, city: str = None, country: str = None) -> Optional[Dict[str, Any]]:
        """
        Get current weather for a city
        
        Args:
            city: City name (default: configured city)
            country: Country code (default: configured country)
            
        Returns:
            Weather data dict or None
        """
        city = city or self.default_city
        country = country or self.default_country
        
        # Check cache (valid for 30 minutes)
        cache_key = f"{city},{country}"
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            cache_time = cached.get('timestamp', 0)
            if datetime.now().timestamp() - cache_time < 1800:  # 30 min
                return cached.get('data')
        
        if not self.api_key:
            # Return mock data if no API key
            return self._get_mock_weather(city)
        
        try:
            response = requests.get(
                f"{self.base_url}/weather",
                params={
                    'q': f"{city},{country}",
                    'appid': self.api_key,
                    'units': 'metric'
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                weather = {
                    'city': city,
                    'temp': round(data['main']['temp']),
                    'feels_like': round(data['main']['feels_like']),
                    'humidity': data['main']['humidity'],
                    'description': data['weather'][0]['description'],
                    'icon': data['weather'][0]['icon'],
                    'wind_speed': round(data['wind']['speed'] * 3.6),  # m/s to km/h
                }
                
                # Cache result
                self.cache[cache_key] = {
                    'timestamp': datetime.now().timestamp(),
                    'data': weather
                }
                self._save_cache()
                
                return weather
            else:
                logger.warning(f"Weather API error: {response.status_code}")
                return self._get_mock_weather(city)
                
        except Exception as e:
            logger.error(f"Weather fetch failed: {e}")
            return self._get_mock_weather(city)
    
    def _get_mock_weather(self, city: str) -> Dict[str, Any]:
        """Return mock weather when API unavailable"""
        hour = datetime.now().hour
        
        # Estimate temperature based on time
        if 6 <= hour < 10:
            temp = 26
        elif 10 <= hour < 16:
            temp = 32
        elif 16 <= hour < 20:
            temp = 29
        else:
            temp = 25
        
        return {
            'city': city,
            'temp': temp,
            'feels_like': temp + 2,
            'humidity': 65,
            'description': 'partly cloudy',
            'wind_speed': 12,
            'is_mock': True
        }
    
    def format_weather_speech(self, weather: Dict[str, Any]) -> str:
        """Format weather for voice output"""
        if not weather:
            return "I couldn't get the weather information."
        
        city = weather.get('city', 'your area')
        temp = weather.get('temp', 0)
        desc = weather.get('description', '')
        feels = weather.get('feels_like', temp)
        
        speech = f"Currently in {city}, it's {temp} degrees with {desc}."
        
        if abs(feels - temp) > 3:
            speech += f" Feels like {feels} degrees."
        
        return speech
    
    def should_give_briefing(self) -> bool:
        """Check if we should give morning briefing (only once per day)"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            
            if self.briefing_file.exists():
                last = self.briefing_file.read_text().strip()
                if last == today:
                    return False  # Already gave briefing today
            
            return True
        except:
            return True
    
    def mark_briefing_given(self):
        """Mark that briefing was given today"""
        try:
            self.briefing_file.parent.mkdir(parents=True, exist_ok=True)
            self.briefing_file.write_text(datetime.now().strftime('%Y-%m-%d'))
        except:
            pass
    
    def get_morning_briefing(self, calendar=None) -> str:
        """
        Generate a complete morning briefing
        
        Args:
            calendar: Optional GoogleCalendar instance for events
            
        Returns:
            Full briefing text for speech
        """
        now = datetime.now()
        hour = now.hour
        
        # Greeting based on time
        if 5 <= hour < 12:
            greeting = "Good morning"
        elif 12 <= hour < 17:
            greeting = "Good afternoon"
        elif 17 <= hour < 21:
            greeting = "Good evening"
        else:
            greeting = "Hello"
        
        parts = [f"{greeting}!"]
        
        # Date
        day_name = now.strftime('%A')
        date_str = now.strftime('%B %d')
        parts.append(f"It's {day_name}, {date_str}.")
        
        # Weather
        weather = self.get_weather()
        if weather:
            weather_text = self.format_weather_speech(weather)
            parts.append(weather_text)
        
        # Calendar events
        if calendar and hasattr(calendar, 'get_todays_events'):
            events = calendar.get_todays_events()
            if events:
                event_text = calendar.format_events_speech(events)
                parts.append(event_text)
            else:
                parts.append("You have no events scheduled for today.")
        
        # Closing
        parts.append("How can I help you today?")
        
        return " ".join(parts)


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    briefing = WeatherBriefing()
    
    print("LADA Weather & Briefing Test")
    print("=" * 40)
    
    # Get weather
    weather = briefing.get_weather('Chennai')
    print(f"\nWeather: {weather}")
    print(f"Speech: {briefing.format_weather_speech(weather)}")
    
    # Morning briefing
    print(f"\nMorning Briefing:")
    print(briefing.get_morning_briefing())
