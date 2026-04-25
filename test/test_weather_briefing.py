"""Tests for modules/weather_briefing.py"""
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class TestWeatherBriefing:
    """Tests for WeatherBriefing class"""

    def test_init_default(self, monkeypatch):
        monkeypatch.setenv("OPENWEATHER_API_KEY", "test_key")
        monkeypatch.setenv("WEATHER_CITY", "Mumbai")
        monkeypatch.setenv("WEATHER_COUNTRY", "IN")

        from modules.weather_briefing import WeatherBriefing

        wb = WeatherBriefing()
        assert wb.api_key == "test_key"
        assert wb.default_city == "Mumbai"
        assert wb.default_country == "IN"

    def test_init_with_api_key(self):
        from modules.weather_briefing import WeatherBriefing

        wb = WeatherBriefing(api_key="my_api_key")
        assert wb.api_key == "my_api_key"

    def test_load_cache_empty(self, tmp_path, monkeypatch):
        from modules.weather_briefing import WeatherBriefing

        wb = WeatherBriefing()
        wb.cache_file = tmp_path / "weather_cache.json"
        cache = wb._load_cache()
        assert cache == {}

    def test_load_cache_existing(self, tmp_path):
        from modules.weather_briefing import WeatherBriefing

        cache_file = tmp_path / "weather_cache.json"
        cache_data = {"Chennai,IN": {"timestamp": datetime.now().timestamp(), "data": {"temp": 30}}}
        cache_file.write_text(json.dumps(cache_data))

        wb = WeatherBriefing()
        wb.cache_file = cache_file
        cache = wb._load_cache()
        assert "Chennai,IN" in cache

    def test_save_cache(self, tmp_path):
        from modules.weather_briefing import WeatherBriefing

        wb = WeatherBriefing()
        wb.cache_file = tmp_path / "weather_cache.json"
        wb.cache = {"test": "data"}
        wb._save_cache()
        assert wb.cache_file.exists()

    def test_get_weather_from_cache(self, monkeypatch):
        from modules.weather_briefing import WeatherBriefing

        wb = WeatherBriefing()
        wb.cache = {
            "TestCity,TC": {
                "timestamp": datetime.now().timestamp(),
                "data": {"temp": 25, "condition": "sunny"},
            }
        }

        result = wb.get_weather(city="TestCity", country="TC")
        assert result["temp"] == 25

    def test_get_weather_mock_no_api_key(self, monkeypatch):
        from modules.weather_briefing import WeatherBriefing

        monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
        wb = WeatherBriefing(api_key="")
        wb.cache = {}

        result = wb.get_weather(city="Chennai")
        # Should return mock data since no API key
        assert result is not None
        assert "temp" in result or result is None  # Depends on mock implementation

    def test_should_give_briefing_new_day(self, tmp_path):
        from modules.weather_briefing import WeatherBriefing

        wb = WeatherBriefing()
        wb.briefing_file = tmp_path / "last_briefing.txt"
        # File doesn't exist, should give briefing
        assert wb.should_give_briefing() is True

    def test_should_give_briefing_already_given(self, tmp_path):
        from modules.weather_briefing import WeatherBriefing

        wb = WeatherBriefing()
        wb.briefing_file = tmp_path / "last_briefing.txt"
        wb.briefing_file.write_text(datetime.now().strftime("%Y-%m-%d"))

        assert wb.should_give_briefing() is False

    def test_mark_briefing_given(self, tmp_path):
        from modules.weather_briefing import WeatherBriefing

        wb = WeatherBriefing()
        wb.briefing_file = tmp_path / "last_briefing.txt"
        wb.mark_briefing_given()

        assert wb.briefing_file.exists()
        assert wb.briefing_file.read_text() == datetime.now().strftime("%Y-%m-%d")
