"""
Database connection and query functions for AC analytics.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional

from . import config


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = psycopg2.connect(
        host=config.DB_HOST,
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        port=config.DB_PORT
    )
    try:
        yield conn
    finally:
        conn.close()


def get_ac_state() -> dict:
    """Get current AC state."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT date, time, ac_state, temperature
                FROM ac_data
                ORDER BY date DESC, time DESC
                LIMIT 1;
            """)
            result = cur.fetchone()
            if result:
                return {
                    "ac_state": result['ac_state'],
                    "temperature": result['temperature'],
                    "timestamp": f"{result['date']} {result['time']}"
                }
            return {"ac_state": False, "temperature": None, "timestamp": None}


def get_settings() -> dict:
    """Get AC settings (thresholds and permissions)."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT key, value FROM ac_settings
                WHERE key IN ('max_temp', 'min_temp', 'ac_allowed');
            """)
            results = cur.fetchall()
            settings = {row['key']: row['value'] for row in results}
            return {
                "max_temp": float(settings.get('max_temp', 78)),
                "min_temp": float(settings.get('min_temp', 72)),
                "ac_allowed": settings.get('ac_allowed', 'False') == 'True'
            }


def get_node_status() -> list:
    """Get mesh node status."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM mesh_nodes ORDER BY node_id;")
            return cur.fetchall()


def get_runtime_stats(days: int = 1) -> dict:
    """
    Calculate AC runtime statistics for a given period.

    Args:
        days: Number of days to analyze (1=today, 7=week, 30=month)

    Returns:
        dict with total_runtime_minutes, cycle_count, avg_cycle_minutes
    """
    start_date = datetime.now().date() - timedelta(days=days-1)

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT date, time, ac_state, temperature
                FROM ac_data
                WHERE date >= %s
                ORDER BY date, time;
            """, (start_date,))
            rows = cur.fetchall()

    if not rows:
        return {
            "total_runtime_minutes": 0,
            "cycle_count": 0,
            "avg_cycle_minutes": 0
        }

    total_runtime = timedelta()
    cycle_count = 0
    ac_on_time = None

    for row in rows:
        timestamp = datetime.combine(row['date'], row['time'])

        if row['ac_state'] and ac_on_time is None:
            # AC turned on
            ac_on_time = timestamp
            cycle_count += 1
        elif not row['ac_state'] and ac_on_time is not None:
            # AC turned off
            total_runtime += timestamp - ac_on_time
            ac_on_time = None

    # If AC is still on, count runtime up to now
    if ac_on_time is not None:
        total_runtime += datetime.now() - ac_on_time

    total_minutes = total_runtime.total_seconds() / 60
    avg_cycle = total_minutes / cycle_count if cycle_count > 0 else 0

    return {
        "total_runtime_minutes": round(total_minutes, 1),
        "cycle_count": cycle_count,
        "avg_cycle_minutes": round(avg_cycle, 1)
    }


def get_daily_runtime(days: int = 14) -> list:
    """
    Get daily runtime for trend chart.

    Returns:
        List of {date, runtime_minutes} for each day
    """
    start_date = datetime.now().date() - timedelta(days=days-1)

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT date, time, ac_state
                FROM ac_data
                WHERE date >= %s
                ORDER BY date, time;
            """, (start_date,))
            rows = cur.fetchall()

    # Group by date and calculate runtime per day
    daily_stats = {}
    ac_on_time = None
    current_date = None

    for row in rows:
        row_date = row['date']
        timestamp = datetime.combine(row_date, row['time'])

        if row_date != current_date:
            # New day - if AC was on, count remaining time to midnight
            if ac_on_time is not None and current_date is not None:
                midnight = datetime.combine(current_date + timedelta(days=1), datetime.min.time())
                daily_stats[current_date] = daily_stats.get(current_date, 0) + (midnight - ac_on_time).total_seconds() / 60
                ac_on_time = datetime.combine(row_date, datetime.min.time())
            current_date = row_date
            if row_date not in daily_stats:
                daily_stats[row_date] = 0

        if row['ac_state'] and ac_on_time is None:
            ac_on_time = timestamp
        elif not row['ac_state'] and ac_on_time is not None:
            daily_stats[row_date] = daily_stats.get(row_date, 0) + (timestamp - ac_on_time).total_seconds() / 60
            ac_on_time = None

    # Fill in missing days with 0
    result = []
    for i in range(days):
        date = start_date + timedelta(days=i)
        result.append({
            "date": str(date),
            "runtime_minutes": round(daily_stats.get(date, 0), 1)
        })

    return result


def get_hourly_usage(days: int = 7) -> list:
    """
    Get hourly usage distribution for peak hours analysis.

    Returns:
        List of {hour, total_minutes} for hours 0-23
    """
    start_date = datetime.now().date() - timedelta(days=days-1)

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT date, time, ac_state
                FROM ac_data
                WHERE date >= %s
                ORDER BY date, time;
            """, (start_date,))
            rows = cur.fetchall()

    hourly_minutes = [0] * 24
    ac_on_time = None

    for row in rows:
        timestamp = datetime.combine(row['date'], row['time'])

        if row['ac_state'] and ac_on_time is None:
            ac_on_time = timestamp
        elif not row['ac_state'] and ac_on_time is not None:
            # Distribute runtime across hours
            current = ac_on_time
            while current < timestamp:
                hour_end = current.replace(minute=59, second=59, microsecond=999999)
                if hour_end > timestamp:
                    hour_end = timestamp
                minutes_in_hour = (hour_end - current).total_seconds() / 60
                hourly_minutes[current.hour] += minutes_in_hour
                current = (current + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            ac_on_time = None

    return [{"hour": h, "total_minutes": round(m, 1)} for h, m in enumerate(hourly_minutes)]


def get_efficiency_stats(days: int = 7) -> dict:
    """
    Calculate cooling efficiency and heat buildup rates.

    Returns:
        dict with avg_cooling_rate, avg_heat_buildup_rate (degrees per hour)
    """
    start_date = datetime.now().date() - timedelta(days=days-1)

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT date, time, ac_state, temperature
                FROM ac_data
                WHERE date >= %s AND temperature IS NOT NULL
                ORDER BY date, time;
            """, (start_date,))
            rows = cur.fetchall()

    cooling_rates = []
    heating_rates = []
    prev_row = None

    for row in rows:
        if prev_row is not None and row['temperature'] is not None and prev_row['temperature'] is not None:
            prev_ts = datetime.combine(prev_row['date'], prev_row['time'])
            curr_ts = datetime.combine(row['date'], row['time'])
            hours = (curr_ts - prev_ts).total_seconds() / 3600

            if hours > 0 and hours < 24:  # Ignore gaps > 24 hours
                temp_delta = prev_row['temperature'] - row['temperature']
                rate = temp_delta / hours

                if prev_row['ac_state']:  # AC was on = cooling
                    if temp_delta > 0:  # Temperature dropped
                        cooling_rates.append(rate)
                else:  # AC was off = heating
                    if temp_delta < 0:  # Temperature rose
                        heating_rates.append(abs(rate))

        prev_row = row

    return {
        "avg_cooling_rate": round(sum(cooling_rates) / len(cooling_rates), 2) if cooling_rates else None,
        "avg_heat_buildup_rate": round(sum(heating_rates) / len(heating_rates), 2) if heating_rates else None,
        "cooling_samples": len(cooling_rates),
        "heating_samples": len(heating_rates)
    }


def get_cost_stats(days: int = 1) -> dict:
    """
    Calculate AC cost statistics for a given period.

    Args:
        days: Number of days to analyze (1=today, 7=week, 30=month)

    Returns:
        dict with total_cost, cost_by_period, runtime_minutes
    """
    from . import rates

    start_date = datetime.now().date() - timedelta(days=days-1)

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT date, time, ac_state
                FROM ac_data
                WHERE date >= %s
                ORDER BY date, time;
            """, (start_date,))
            rows = cur.fetchall()

    if not rows:
        return {
            "total_cost": 0,
            "total_runtime_minutes": 0,
            "cost_by_period": {
                "on_peak": {"cost": 0, "minutes": 0},
                "off_peak": {"cost": 0, "minutes": 0},
                "super_off_peak": {"cost": 0, "minutes": 0},
            }
        }

    total_cost = 0.0
    total_minutes = 0.0
    cost_by_period = {
        "on_peak": {"cost": 0.0, "minutes": 0.0},
        "off_peak": {"cost": 0.0, "minutes": 0.0},
        "super_off_peak": {"cost": 0.0, "minutes": 0.0},
    }
    ac_on_time = None

    for row in rows:
        timestamp = datetime.combine(row['date'], row['time'])

        if row['ac_state'] and ac_on_time is None:
            ac_on_time = timestamp
        elif not row['ac_state'] and ac_on_time is not None:
            # Calculate cost for this AC cycle, broken down by hour
            current = ac_on_time
            while current < timestamp:
                # Get the end of this hour or the off time, whichever is earlier
                hour_end = (current + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                if hour_end > timestamp:
                    hour_end = timestamp

                minutes_in_segment = (hour_end - current).total_seconds() / 60
                period = rates.get_rate_period(current)
                rate = rates.get_rate(current)
                segment_cost = rates.calculate_hourly_cost(current, minutes_in_segment)

                total_cost += segment_cost
                total_minutes += minutes_in_segment
                cost_by_period[period]["cost"] += segment_cost
                cost_by_period[period]["minutes"] += minutes_in_segment

                current = hour_end

            ac_on_time = None

    # If AC is still on, calculate cost up to now
    if ac_on_time is not None:
        current = ac_on_time
        now = datetime.now()
        while current < now:
            hour_end = (current + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            if hour_end > now:
                hour_end = now

            minutes_in_segment = (hour_end - current).total_seconds() / 60
            period = rates.get_rate_period(current)
            segment_cost = rates.calculate_hourly_cost(current, minutes_in_segment)

            total_cost += segment_cost
            total_minutes += minutes_in_segment
            cost_by_period[period]["cost"] += segment_cost
            cost_by_period[period]["minutes"] += minutes_in_segment

            current = hour_end

    return {
        "total_cost": round(total_cost, 2),
        "total_runtime_minutes": round(total_minutes, 1),
        "cost_by_period": {
            period: {
                "cost": round(data["cost"], 2),
                "minutes": round(data["minutes"], 1)
            }
            for period, data in cost_by_period.items()
        }
    }


def store_weather(outdoor_temp: float, humidity: float = None, conditions: str = None):
    """Store a weather reading in the database."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO weather_data (outdoor_temp, humidity, conditions)
                VALUES (%s, %s, %s);
            """, (outdoor_temp, humidity, conditions))
        conn.commit()


def get_latest_weather() -> Optional[dict]:
    """Get the most recent weather reading."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT timestamp, outdoor_temp, humidity, conditions
                FROM weather_data
                ORDER BY timestamp DESC
                LIMIT 1;
            """)
            result = cur.fetchone()
            if result:
                return {
                    "timestamp": result["timestamp"].isoformat() if result["timestamp"] else None,
                    "outdoor_temp": result["outdoor_temp"],
                    "humidity": result["humidity"],
                    "conditions": result["conditions"],
                }
            return None


def get_weather_history(days: int = 1) -> list:
    """
    Get weather history for charting.

    Returns:
        List of {timestamp, outdoor_temp, humidity, conditions}
    """
    start_date = datetime.now().date() - timedelta(days=days-1)

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT timestamp, outdoor_temp, humidity, conditions
                FROM weather_data
                WHERE timestamp >= %s
                ORDER BY timestamp;
            """, (start_date,))
            rows = cur.fetchall()

    return [
        {
            "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None,
            "outdoor_temp": row["outdoor_temp"],
            "humidity": row["humidity"],
            "conditions": row["conditions"],
        }
        for row in rows
    ]


def get_temperature_history(days: int = 1) -> list:
    """
    Get temperature history with AC state for charting.

    Returns:
        List of {timestamp, temperature, ac_state} for each data point
    """
    start_date = datetime.now().date() - timedelta(days=days-1)

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT date, time, temperature, ac_state
                FROM ac_data
                WHERE date >= %s AND temperature IS NOT NULL
                ORDER BY date, time;
            """, (start_date,))
            rows = cur.fetchall()

    result = []
    for row in rows:
        timestamp = datetime.combine(row['date'], row['time'])
        result.append({
            "timestamp": timestamp.isoformat(),
            "temperature": row['temperature'],
            "ac_state": row['ac_state']
        })

    return result


def get_monthly_runtime() -> list:
    """
    Get monthly runtime for all-time trend chart.

    Returns:
        List of {month, runtime_minutes} for each month with data
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT date, time, ac_state
                FROM ac_data
                ORDER BY date, time;
            """)
            rows = cur.fetchall()

    if not rows:
        return []

    # Group by month and calculate runtime per month
    monthly_stats = {}
    ac_on_time = None
    current_month = None

    for row in rows:
        row_date = row['date']
        row_month = row_date.strftime('%Y-%m')
        timestamp = datetime.combine(row_date, row['time'])

        if row_month != current_month:
            # New month - if AC was on, count remaining time to end of previous month
            if ac_on_time is not None and current_month is not None:
                # Get first day of new month as cutoff
                month_end = datetime.combine(row_date.replace(day=1), datetime.min.time())
                monthly_stats[current_month] = monthly_stats.get(current_month, 0) + (month_end - ac_on_time).total_seconds() / 60
                ac_on_time = datetime.combine(row_date.replace(day=1), datetime.min.time())
            current_month = row_month
            if row_month not in monthly_stats:
                monthly_stats[row_month] = 0

        if row['ac_state'] and ac_on_time is None:
            ac_on_time = timestamp
        elif not row['ac_state'] and ac_on_time is not None:
            monthly_stats[row_month] = monthly_stats.get(row_month, 0) + (timestamp - ac_on_time).total_seconds() / 60
            ac_on_time = None

    # If AC is still on, count up to now
    if ac_on_time is not None and current_month is not None:
        monthly_stats[current_month] = monthly_stats.get(current_month, 0) + (datetime.now() - ac_on_time).total_seconds() / 60

    # Convert to sorted list
    result = []
    for month in sorted(monthly_stats.keys()):
        result.append({
            "month": month,
            "runtime_minutes": round(monthly_stats[month], 1)
        })

    return result


def get_daily_costs(days: int = 14) -> list:
    """
    Get daily cost breakdown for trend chart.

    Returns:
        List of {date, cost, runtime_minutes} for each day
    """
    from . import rates

    start_date = datetime.now().date() - timedelta(days=days-1)

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT date, time, ac_state
                FROM ac_data
                WHERE date >= %s
                ORDER BY date, time;
            """, (start_date,))
            rows = cur.fetchall()

    # Calculate cost per day
    daily_stats = {}
    ac_on_time = None

    for row in rows:
        row_date = row['date']
        timestamp = datetime.combine(row_date, row['time'])

        if row_date not in daily_stats:
            daily_stats[row_date] = {"cost": 0.0, "minutes": 0.0}

        if row['ac_state'] and ac_on_time is None:
            ac_on_time = timestamp
        elif not row['ac_state'] and ac_on_time is not None:
            # Handle day boundary crossing
            current = ac_on_time
            while current < timestamp:
                current_date = current.date()
                # End of day or end of cycle, whichever is first
                day_end = datetime.combine(current_date + timedelta(days=1), datetime.min.time())
                segment_end = min(day_end, timestamp)

                # Calculate cost for this segment
                while current < segment_end:
                    hour_end = (current + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                    if hour_end > segment_end:
                        hour_end = segment_end

                    minutes = (hour_end - current).total_seconds() / 60
                    cost = rates.calculate_hourly_cost(current, minutes)

                    if current_date not in daily_stats:
                        daily_stats[current_date] = {"cost": 0.0, "minutes": 0.0}
                    daily_stats[current_date]["cost"] += cost
                    daily_stats[current_date]["minutes"] += minutes

                    current = hour_end

            ac_on_time = None

    # Fill in missing days with 0
    result = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        stats = daily_stats.get(d, {"cost": 0.0, "minutes": 0.0})
        result.append({
            "date": str(d),
            "cost": round(stats["cost"], 2),
            "runtime_minutes": round(stats["minutes"], 1)
        })

    return result
