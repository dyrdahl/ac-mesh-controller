"""
Weather service using Open-Meteo API.
"""

import httpx
from datetime import datetime, timedelta
from typing import Optional

from . import config

# Open-Meteo API endpoint
API_URL = "https://api.open-meteo.com/v1/forecast"

# Cache to avoid excessive API calls
_cache: dict = {
    "data": None,
    "fetched_at": None,
    "stored_at": None,  # Track when we last stored to DB
}
CACHE_DURATION = timedelta(minutes=5)  # Only fetch from Open-Meteo every 5 min
DB_STORE_INTERVAL = timedelta(minutes=15)  # Only store to DB every 15 min


def _is_cache_valid() -> bool:
    """Check if cached data is still valid."""
    if _cache["data"] is None or _cache["fetched_at"] is None:
        return False
    return datetime.now() - _cache["fetched_at"] < CACHE_DURATION


def _should_store_to_db() -> bool:
    """Check if enough time has passed to store to DB again."""
    if _cache["stored_at"] is None:
        return True
    return datetime.now() - _cache["stored_at"] >= DB_STORE_INTERVAL


async def fetch_current_weather() -> Optional[dict]:
    """
    Fetch current weather from Open-Meteo API.

    Returns:
        dict with outdoor_temp, humidity, conditions, or None on error
    """
    # Return cached data if valid
    if _is_cache_valid():
        return _cache["data"]

    params = {
        "latitude": config.LATITUDE,
        "longitude": config.LONGITUDE,
        "current": "temperature_2m,relative_humidity_2m,weather_code",
        "temperature_unit": "fahrenheit",
        "timezone": config.TIMEZONE,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(API_URL, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()

        current = data.get("current", {})

        result = {
            "outdoor_temp": current.get("temperature_2m"),
            "humidity": current.get("relative_humidity_2m"),
            "conditions": _weather_code_to_condition(current.get("weather_code", 0)),
            "timestamp": current.get("time"),
        }

        # Update cache
        _cache["data"] = result
        _cache["fetched_at"] = datetime.now()

        return result

    except Exception as e:
        print(f"Weather API error: {e}")
        # Return stale cache if available
        if _cache["data"]:
            return _cache["data"]
        return None


def _weather_code_to_condition(code: int) -> str:
    """Convert WMO weather code to simple condition string."""
    # WMO Weather interpretation codes
    # https://open-meteo.com/en/docs
    if code == 0:
        return "clear"
    elif code in (1, 2):
        return "partly_cloudy"
    elif code in (3,):
        return "cloudy"
    elif code in (45, 48):
        return "foggy"
    elif code in (51, 53, 55, 56, 57):
        return "drizzle"
    elif code in (61, 63, 65, 66, 67):
        return "rain"
    elif code in (71, 73, 75, 77):
        return "snow"
    elif code in (80, 81, 82):
        return "showers"
    elif code in (85, 86):
        return "snow_showers"
    elif code in (95, 96, 99):
        return "thunderstorm"
    else:
        return "unknown"


async def fetch_weather_now() -> Optional[dict]:
    """
    Force fetch current weather, bypassing cache.
    Use for important events like AC state changes.
    """
    params = {
        "latitude": config.LATITUDE,
        "longitude": config.LONGITUDE,
        "current": "temperature_2m,relative_humidity_2m,weather_code",
        "temperature_unit": "fahrenheit",
        "timezone": config.TIMEZONE,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(API_URL, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()

        current = data.get("current", {})

        result = {
            "outdoor_temp": current.get("temperature_2m"),
            "humidity": current.get("relative_humidity_2m"),
            "conditions": _weather_code_to_condition(current.get("weather_code", 0)),
            "timestamp": current.get("time"),
        }

        # Update cache too
        _cache["data"] = result
        _cache["fetched_at"] = datetime.now()

        return result

    except Exception as e:
        print(f"Weather API error (force fetch): {e}")
        return _cache.get("data")  # Return stale cache on error


async def fetch_and_store_weather(db_func) -> Optional[dict]:
    """
    Fetch current weather and optionally store in database.

    Only stores to DB every DB_STORE_INTERVAL (15 min) to avoid spam.

    Args:
        db_func: Function to store weather data (from database.py)

    Returns:
        The weather data dict, or None on error
    """
    weather = await fetch_current_weather()

    # Only store to DB periodically, not every request
    if weather and weather.get("outdoor_temp") is not None and _should_store_to_db():
        db_func(
            outdoor_temp=weather["outdoor_temp"],
            humidity=weather.get("humidity"),
            conditions=weather.get("conditions"),
        )
        _cache["stored_at"] = datetime.now()

    return weather
