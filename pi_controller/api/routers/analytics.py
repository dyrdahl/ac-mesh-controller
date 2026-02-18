"""
Analytics API endpoints for AC dashboard.
"""

from datetime import datetime
from fastapi import APIRouter, Query

from ..database import (
    get_runtime_stats,
    get_daily_runtime,
    get_monthly_runtime,
    get_hourly_usage,
    get_efficiency_stats,
    get_cost_stats,
    get_daily_costs,
    get_temperature_history,
    get_weather_history,
    get_latest_weather,
    store_weather,
)
from .. import rates
from .. import weather as weather_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/runtime")
def runtime_stats(
    period: str = Query("day", pattern="^(day|week|month)$")
):
    """
    Get AC runtime statistics for a period.

    - **period**: day, week, or month
    """
    days = {"day": 1, "week": 7, "month": 30}[period]
    return get_runtime_stats(days)


@router.get("/daily")
def daily_runtime(days: int = Query(14, ge=1, le=90)):
    """
    Get daily runtime for trend chart.

    - **days**: Number of days to include (default: 14)
    """
    return get_daily_runtime(days)


@router.get("/hourly")
def hourly_usage(days: int = Query(7, ge=1, le=30)):
    """
    Get hourly usage distribution for peak hours analysis.

    - **days**: Number of days to aggregate (default: 7)
    """
    return get_hourly_usage(days)


@router.get("/efficiency")
def efficiency_stats(days: int = Query(7, ge=1, le=30)):
    """
    Get cooling efficiency and heat buildup rates.

    - **days**: Number of days to analyze (default: 7)
    """
    return get_efficiency_stats(days)


@router.get("/cost")
def cost_stats(period: str = Query("day", pattern="^(day|week|month)$")):
    """
    Get AC cost statistics for a period.

    - **period**: day, week, or month
    """
    days = {"day": 1, "week": 7, "month": 30}[period]
    return get_cost_stats(days)


@router.get("/daily-costs")
def daily_costs(days: int = Query(14, ge=1, le=90)):
    """
    Get daily cost breakdown for trend chart.

    - **days**: Number of days to include (default: 14)
    """
    return get_daily_costs(days)


@router.get("/rates")
def current_rates():
    """
    Get current rate information based on current time.
    """
    now = datetime.now()
    info = rates.get_rate_info(now)
    return {
        "current_time": now.isoformat(),
        "season": info["season"],
        "period": rates.format_period_name(info["period"]),
        "rate_per_kwh": info["rate"],
        "cost_per_hour": round(info["cost_per_hour"], 2),
        "ac_watts": rates.AC_WATTS,
        "is_weekend_or_holiday": info["is_weekend_or_holiday"],
    }


@router.get("/summary")
async def analytics_summary():
    """
    Get all analytics in one call for dashboard.
    """
    # Use 3650 days (~10 years) for "all time" to capture all historical data
    ALL_TIME_DAYS = 3650

    # Fetch live weather (cached for 10 min) and store in DB
    current_weather = await weather_service.fetch_and_store_weather(store_weather)

    return {
        "today": get_runtime_stats(1),
        "week": get_runtime_stats(7),
        "month": get_runtime_stats(30),
        "daily_trend": get_daily_runtime(14),
        "monthly_all_time": get_monthly_runtime(),
        "hourly": get_hourly_usage(7),
        "hourly_all_time": get_hourly_usage(ALL_TIME_DAYS),
        "efficiency": get_efficiency_stats(7),
        "cost_today": get_cost_stats(1),
        "cost_week": get_cost_stats(7),
        "cost_month": get_cost_stats(30),
        "cost_all_time": get_cost_stats(ALL_TIME_DAYS),
        "current_rate": rates.get_rate_info(datetime.now()),
        "temperature_history": get_temperature_history(1),
        "temperature_history_week": get_temperature_history(7),
        "weather_history": get_weather_history(1),
        "weather_history_week": get_weather_history(7),
        "current_weather": current_weather,
    }
