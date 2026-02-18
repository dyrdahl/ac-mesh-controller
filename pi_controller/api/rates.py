"""
Electricity Rate Configuration and Cost Calculation

Supports TOU (Time-of-Use) rate schedules.
Configure rates in .env file or environment variables.
"""

from datetime import datetime, date
from typing import Literal

from . import config

# AC unit power consumption from config
AC_WATTS = config.AC_WATTS
AC_KW = config.AC_KW

# Rates from config
RATES = config.RATES

# Holidays - treated as weekends for rate purposes
# TODO: Could make this configurable or auto-fetch
HOLIDAYS = [
    # 2025
    date(2025, 1, 1),    # New Year's Day
    date(2025, 1, 20),   # MLK Day
    date(2025, 2, 17),   # Presidents Day
    date(2025, 5, 26),   # Memorial Day
    date(2025, 7, 4),    # Independence Day
    date(2025, 9, 1),    # Labor Day
    date(2025, 11, 11),  # Veterans Day
    date(2025, 11, 27),  # Thanksgiving
    date(2025, 12, 25),  # Christmas
    # 2026
    date(2026, 1, 1),    # New Year's Day
    date(2026, 1, 19),   # MLK Day
    date(2026, 2, 16),   # Presidents Day
    date(2026, 5, 25),   # Memorial Day
    date(2026, 7, 4),    # Independence Day (observed)
    date(2026, 9, 7),    # Labor Day
    date(2026, 11, 11),  # Veterans Day
    date(2026, 11, 26),  # Thanksgiving
    date(2026, 12, 25),  # Christmas
    # 2027
    date(2027, 1, 1),    # New Year's Day
    date(2027, 1, 18),   # MLK Day
    date(2027, 2, 15),   # Presidents Day
    date(2027, 5, 31),   # Memorial Day
    date(2027, 7, 5),    # Independence Day (observed)
    date(2027, 9, 6),    # Labor Day
    date(2027, 11, 11),  # Veterans Day
    date(2027, 11, 25),  # Thanksgiving
    date(2027, 12, 25),  # Christmas (observed 12/24)
]


def get_season(dt: datetime | date) -> Literal["summer", "winter"]:
    """Determine season based on date. Summer: Jun 1 - Oct 31, Winter: Nov 1 - May 31"""
    if isinstance(dt, datetime):
        dt = dt.date()
    month = dt.month
    if 6 <= month <= 10:
        return "summer"
    return "winter"


def is_weekend_or_holiday(dt: datetime | date) -> bool:
    """Check if date is a weekend or holiday."""
    if isinstance(dt, datetime):
        dt = dt.date()
    # Weekend: Saturday (5) or Sunday (6)
    if dt.weekday() >= 5:
        return True
    # Check holidays
    if dt in HOLIDAYS:
        return True
    return False


def get_rate_period(dt: datetime) -> Literal["on_peak", "off_peak", "super_off_peak"]:
    """
    Determine TOU rate period based on datetime.

    SDGE TOU-DR Schedule:
    Weekdays:
        On-Peak: 4pm - 9pm
        Off-Peak: 6am - 4pm, 9pm - midnight
        Super Off-Peak: midnight - 6am

    Weekends/Holidays:
        On-Peak: 4pm - 9pm
        Off-Peak: 2pm - 4pm, 9pm - midnight
        Super Off-Peak: midnight - 2pm
    """
    hour = dt.hour
    is_weekend = is_weekend_or_holiday(dt)

    # On-Peak: 4pm (16:00) - 9pm (21:00) for all days
    if 16 <= hour < 21:
        return "on_peak"

    if is_weekend:
        # Weekend/Holiday schedule
        # Super Off-Peak: midnight - 2pm (0:00 - 14:00)
        if 0 <= hour < 14:
            return "super_off_peak"
        # Off-Peak: 2pm - 4pm (14:00 - 16:00), 9pm - midnight (21:00 - 24:00)
        else:
            return "off_peak"
    else:
        # Weekday schedule
        # Super Off-Peak: midnight - 6am (0:00 - 6:00)
        if 0 <= hour < 6:
            return "super_off_peak"
        # Off-Peak: 6am - 4pm (6:00 - 16:00), 9pm - midnight (21:00 - 24:00)
        else:
            return "off_peak"


def get_rate(dt: datetime) -> float:
    """Get the electricity rate ($/kWh) for a given datetime."""
    season = get_season(dt)
    period = get_rate_period(dt)
    return RATES[season][period]


def calculate_hourly_cost(dt: datetime, runtime_minutes: float) -> float:
    """
    Calculate cost for AC runtime during a specific hour.

    Args:
        dt: datetime for the hour
        runtime_minutes: minutes the AC ran during that hour

    Returns:
        Cost in dollars
    """
    if runtime_minutes <= 0:
        return 0.0

    runtime_hours = runtime_minutes / 60
    rate = get_rate(dt)
    kwh = AC_KW * runtime_hours
    cost = kwh * rate
    return cost


def get_rate_info(dt: datetime) -> dict:
    """Get detailed rate information for a datetime."""
    season = get_season(dt)
    period = get_rate_period(dt)
    rate = RATES[season][period]
    is_weekend = is_weekend_or_holiday(dt)

    # Time ranges depend on weekday vs weekend/holiday
    if is_weekend:
        schedule = {
            "on_peak": "4pm - 9pm",
            "off_peak": "2pm - 4pm, 9pm - 12am",
            "super_off_peak": "12am - 2pm",
        }
    else:
        schedule = {
            "on_peak": "4pm - 9pm",
            "off_peak": "6am - 4pm, 9pm - 12am",
            "super_off_peak": "12am - 6am",
        }

    return {
        "season": season,
        "period": period,
        "rate": rate,
        "cost_per_hour": AC_KW * rate,
        "is_weekend_or_holiday": is_weekend,
        "schedule": schedule,
    }


def format_period_name(period: str) -> str:
    """Format period name for display."""
    return {
        "on_peak": "On-Peak",
        "off_peak": "Off-Peak",
        "super_off_peak": "Super Off-Peak",
    }.get(period, period)
