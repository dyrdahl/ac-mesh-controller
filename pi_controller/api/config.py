"""
Configuration management for AC Dashboard API.

Loads settings from environment variables or .env file.
Copy .env.example to .env and fill in your values.
"""

import os
from pathlib import Path
from typing import Optional

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    # Look for .env in api directory or parent directories
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv not installed, use environment variables only


def get_env(key: str, default: str = None, required: bool = False) -> Optional[str]:
    """Get environment variable with optional default."""
    value = os.getenv(key, default)
    if required and value is None:
        raise ValueError(f"Required environment variable {key} is not set")
    return value


def get_env_float(key: str, default: float) -> float:
    """Get environment variable as float."""
    value = os.getenv(key)
    if value is None:
        return default
    return float(value)


def get_env_int(key: str, default: int) -> int:
    """Get environment variable as int."""
    value = os.getenv(key)
    if value is None:
        return default
    return int(value)


# =============================================================================
# Database Configuration
# =============================================================================
DB_HOST = get_env("DB_HOST", "localhost")
DB_NAME = get_env("DB_NAME", "postgres")
DB_USER = get_env("DB_USER", "pi")
DB_PASSWORD = get_env("DB_PASSWORD", "")
DB_PORT = get_env_int("DB_PORT", 5432)


# =============================================================================
# Location Configuration (for weather API)
# =============================================================================
# Default: San Diego, CA (placeholder)
LATITUDE = get_env_float("LATITUDE", 32.7157)
LONGITUDE = get_env_float("LONGITUDE", -117.1611)
TIMEZONE = get_env("TIMEZONE", "America/Los_Angeles")


# =============================================================================
# AC Unit Configuration
# =============================================================================
# Power consumption in watts
AC_WATTS = get_env_int("AC_WATTS", 5000)
AC_KW = AC_WATTS / 1000


# =============================================================================
# Electricity Rate Configuration
# =============================================================================
# Rate plan identifier (for future multi-plan support)
RATE_PLAN = get_env("RATE_PLAN", "SDGE_TOU_DR")

# SDGE TOU-DR Rates ($/kWh) - Above 130% baseline
# Summer: June 1 - October 31
SUMMER_ON_PEAK = get_env_float("SUMMER_ON_PEAK", 0.57614)
SUMMER_OFF_PEAK = get_env_float("SUMMER_OFF_PEAK", 0.51719)
SUMMER_SUPER_OFF_PEAK = get_env_float("SUMMER_SUPER_OFF_PEAK", 0.46163)

# Winter: November 1 - May 31
WINTER_ON_PEAK = get_env_float("WINTER_ON_PEAK", 0.62177)
WINTER_OFF_PEAK = get_env_float("WINTER_OFF_PEAK", 0.54003)
WINTER_SUPER_OFF_PEAK = get_env_float("WINTER_SUPER_OFF_PEAK", 0.44924)

# Assembled rates dict for easy access
RATES = {
    "summer": {
        "on_peak": SUMMER_ON_PEAK,
        "off_peak": SUMMER_OFF_PEAK,
        "super_off_peak": SUMMER_SUPER_OFF_PEAK,
    },
    "winter": {
        "on_peak": WINTER_ON_PEAK,
        "off_peak": WINTER_OFF_PEAK,
        "super_off_peak": WINTER_SUPER_OFF_PEAK,
    },
}
