"""
AC control and status API endpoints.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..database import get_ac_state, get_settings, get_node_status, store_weather
from .. import socket_client
from .. import weather as weather_service

router = APIRouter(prefix="/ac", tags=["ac"])


# Request models
class TempThresholds(BaseModel):
    max_temp: int = Field(..., ge=50, le=100, description="Max temperature threshold")
    min_temp: int = Field(..., ge=50, le=100, description="Min temperature threshold")


class BrightnessLevel(BaseModel):
    level: int = Field(..., ge=0, le=100, description="Brightness level 0-100")


@router.get("/status")
def ac_status():
    """Get current AC state and temperature from database."""
    return get_ac_state()


@router.get("/live")
def live_status():
    """Get live temperature and AC status from controller."""
    temp = socket_client.get_current_temp()
    ac_status = socket_client.get_ac_status()
    perm_status = socket_client.get_ac_permission()

    return {
        "temperature": temp if temp and temp != "---" else None,
        "ac_state": ac_status == "AC is ON" if ac_status else None,
        "ac_allowed": perm_status == "True" if perm_status else None,
    }


@router.get("/settings")
def ac_settings():
    """Get AC settings (thresholds and permissions)."""
    return get_settings()


@router.get("/nodes")
def nodes_status():
    """Get mesh network node status."""
    nodes = get_node_status()
    return [
        {
            "node_id": n['node_id'],
            "name": n['name'],
            "status": n['status'],
            "last_seen": str(n['last_seen']) if n['last_seen'] else None,
            "last_message": n['last_message'],
        }
        for n in nodes
    ]


@router.get("/dashboard")
def dashboard():
    """Get all dashboard data in one call."""
    return {
        "status": get_ac_state(),
        "settings": get_settings(),
        "nodes": nodes_status(),
    }


# =============================================================================
# Control Endpoints (relay to controller socket server)
# =============================================================================


@router.post("/power/on")
async def turn_on():
    """Turn AC on."""
    response = socket_client.turn_on_ac()
    if response is None:
        raise HTTPException(status_code=503, detail="Controller not responding")

    # Fetch and store current outdoor weather for this event
    weather = await weather_service.fetch_weather_now()
    if weather and weather.get("outdoor_temp") is not None:
        store_weather(
            outdoor_temp=weather["outdoor_temp"],
            humidity=weather.get("humidity"),
            conditions=weather.get("conditions"),
        )

    return {"success": "AC is ON" in response, "message": response}


@router.post("/power/off")
async def turn_off():
    """Turn AC off."""
    response = socket_client.turn_off_ac()
    if response is None:
        raise HTTPException(status_code=503, detail="Controller not responding")

    # Fetch and store current outdoor weather for this event
    weather = await weather_service.fetch_weather_now()
    if weather and weather.get("outdoor_temp") is not None:
        store_weather(
            outdoor_temp=weather["outdoor_temp"],
            humidity=weather.get("humidity"),
            conditions=weather.get("conditions"),
        )

    return {"success": "AC is OFF" in response, "message": response}


@router.post("/thresholds")
def set_thresholds(temps: TempThresholds):
    """Set temperature thresholds."""
    if temps.max_temp <= temps.min_temp:
        raise HTTPException(status_code=400, detail="Max temp must be greater than min temp")

    response = socket_client.set_temps(temps.max_temp, temps.min_temp)
    if response is None:
        raise HTTPException(status_code=503, detail="Controller not responding")
    return {"success": True, "max_temp": temps.max_temp, "min_temp": temps.min_temp}


@router.post("/permission/toggle")
def toggle_permission():
    """Toggle AC permission (enable/disable AC operation)."""
    response = socket_client.toggle_ac_permission()
    if response is None:
        raise HTTPException(status_code=503, detail="Controller not responding")
    return {"success": True, "message": "AC permission toggled"}


@router.post("/reset")
def reset_ac_node():
    """Reset the AC relay node."""
    response = socket_client.reset_node()
    if response is None:
        raise HTTPException(status_code=503, detail="Controller not responding")
    return {"success": "Success" in response, "message": response}


@router.post("/brightness")
def set_led_brightness(brightness: BrightnessLevel):
    """Set LED brightness (0-100%)."""
    response = socket_client.set_brightness(brightness.level)
    if response is None:
        raise HTTPException(status_code=503, detail="Controller not responding")
    return {"success": True, "level": brightness.level}
