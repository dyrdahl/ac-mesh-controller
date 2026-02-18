"""
Weather API endpoints.
"""

from fastapi import APIRouter, Query

from ..database import get_latest_weather, get_weather_history, store_weather
from .. import weather as weather_service

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("/current")
async def current_weather():
    """
    Get current outdoor weather.

    Fetches from Open-Meteo API (cached for 10 minutes) and stores in database.
    """
    weather = await weather_service.fetch_and_store_weather(store_weather)
    if weather:
        return weather
    # Fallback to latest stored weather
    stored = get_latest_weather()
    if stored:
        return stored
    return {"error": "Weather data unavailable"}


@router.get("/history")
def weather_history(days: int = Query(1, ge=1, le=30)):
    """
    Get weather history for charting.

    - **days**: Number of days to include (default: 1)
    """
    return get_weather_history(days)


@router.get("/latest")
def latest_weather():
    """
    Get latest stored weather reading (no API call).
    """
    return get_latest_weather() or {"error": "No weather data"}
