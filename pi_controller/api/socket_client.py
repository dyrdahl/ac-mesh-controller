"""
Socket client for relaying commands to the controller.
"""

import socket
from typing import Optional

CONTROLLER_HOST = 'localhost'
CONTROLLER_PORT = 65432
TIMEOUT = 5


def send_command(command: str, wait_response: bool = True) -> Optional[str]:
    """
    Send a command to the controller's socket server.

    Args:
        command: Command string to send
        wait_response: Whether to wait for a response

    Returns:
        Response string, or None on failure/timeout
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(TIMEOUT)
            sock.connect((CONTROLLER_HOST, CONTROLLER_PORT))
            sock.sendall(command.encode('utf-8'))

            if wait_response:
                response = sock.recv(1024).decode('utf-8')
                return response
            return "OK"

    except socket.timeout:
        return None
    except ConnectionRefusedError:
        return None
    except Exception as e:
        return None


def get_ac_status() -> Optional[str]:
    """Get current AC status (ON/OFF)."""
    return send_command("AC_Status")


def turn_on_ac() -> Optional[str]:
    """Turn AC on."""
    return send_command("TurnOnAC")


def turn_off_ac() -> Optional[str]:
    """Turn AC off."""
    return send_command("TurnOffAC")


def set_temps(max_temp: int, min_temp: int) -> Optional[str]:
    """Set temperature thresholds. Controller doesn't send response on success."""
    return send_command(f"setTemps:{max_temp},{min_temp}", wait_response=False)


def get_temps() -> Optional[str]:
    """Get current temperature thresholds."""
    return send_command("getTemps")


def toggle_ac_permission() -> Optional[str]:
    """Toggle AC permission (allowed/not allowed). Controller doesn't send response."""
    return send_command("ToggleAC", wait_response=False)


def get_ac_permission() -> Optional[str]:
    """Get current AC permission status."""
    return send_command("AC_Perm_Status")


def reset_node() -> Optional[str]:
    """Reset the AC relay node."""
    return send_command("ResetNode")


def set_brightness(level: int) -> Optional[str]:
    """Set LED brightness (0-100). Controller doesn't send response on success."""
    return send_command(f"setBrightness:{level}", wait_response=False)


def get_current_temp() -> Optional[str]:
    """Get current temperature reading."""
    return send_command("current_temp")
