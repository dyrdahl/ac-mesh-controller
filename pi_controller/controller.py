#!/usr/bin/env python3
"""
AC Control System - Mesh Network Controller Node

This module implements the central controller (Node 0) for a home automation
system that manages AC units via an RF24 mesh network. It coordinates
communication between:
    - Node 1: AC relay controller
    - Node 2: Temperature sensor + LCD display (keypadLCD)

The controller provides:
    - Real-time temperature monitoring with safety shutoffs
    - AC state persistence via PostgreSQL database
    - Socket server for mobile/remote client connections
    - Automatic mesh network management and node health checks

Hardware: Raspberry Pi with nRF24L01+ radio module (SPI)
Protocol: RF24Mesh on channel 97 at 1Mbps

Author: Shane Dyrdahl
Version: 1.5.1
"""

import os
import sys
import time
import threading
from datetime import datetime, timedelta
from queue import Queue

import psycopg2
from psycopg2.extras import RealDictCursor
from colorama import init
from termcolor import colored

from pyrf24 import (
    RF24,
    RF24Network,
    RF24Mesh,
    MAX_PAYLOAD_SIZE,
    RF24_PA_MAX,
    RF24_1MBPS,
)

from socket_server import (
    start_server,
    stop_server,
    message_queue,
    send_message_to_client,
    restart_server,
)

# =============================================================================
# Constants
# =============================================================================

VERSION = "1.5.1"

# Database configuration
DB_HOST = 'localhost'
DB_NAME = 'postgres'
DB_USER = 'pi'
DB_PASSWORD = '6589'
DB_PORT = 5432

# RF24 hardware pins (directly attached to Raspberry Pi GPIO)
RF24_CE_PIN = 22      # GPIO pin for Chip Enable
RF24_CSN_PIN = 0      # SPI CE0 (/dev/spidev0.0)

# Mesh network settings
MESH_CHANNEL = 97     # RF channel (must match all nodes)
MESH_NODE_ID = 0      # Controller is always Node 0

# Timing intervals (seconds)
TEMP_WARNING_TIMEOUT = 90     # Warn if no temp received (keypad sends every 60s)
TEMP_SAFETY_TIMEOUT = 180     # Safety shutoff if no temp
PING_INTERVAL = 60            # Node health check interval (seconds)
DB_STALE_THRESHOLD = 40       # Minutes before DB state considered stale

# Node IDs for reference
NODE_AC_RELAY = 1
NODE_TEMP_LCD = 2

# =============================================================================
# Initialization
# =============================================================================

init()  # Initialize colorama for cross-platform colored output


def log(level: str, message: str, node=None) -> None:
    """
    Unified logging with timestamps and color-coded output.

    Args:
        level: Log level - "rx", "tx", "db", "info", "warn", or "error"
        message: The message to log
        node: Optional node identifier (int or string) for RX/TX messages

    Output format:
        [HH:MM:SS] PREFIX [Node X ->/<-] message
    """
    timestamp = datetime.now().strftime('%H:%M:%S')

    prefixes = {
        "rx":    ("RX ", "cyan"),     # Received from mesh/socket
        "tx":    ("TX ", "green"),    # Transmitted to mesh
        "db":    ("DB ", "blue"),     # Database operations
        "info":  ("-- ", "white"),    # General info
        "warn":  ("\u26a0\ufe0f ", "yellow"),  # Warnings
        "error": ("\u274c ", "red"),  # Errors
    }

    prefix, color = prefixes.get(level, ("?? ", "white"))

    if node is not None:
        arrow = "\u2192" if level == "rx" else "\u2190"
        node_str = f"Node {node}" if isinstance(node, int) else node
        print(colored(f"[{timestamp}] {prefix} {node_str} {arrow} {message}", color))
    else:
        print(colored(f"[{timestamp}] {prefix} {message}", color))


# =============================================================================
# Global State
# =============================================================================

# AC permission flag - when False, AC commands are blocked
# Loaded from database on startup (see after DB functions defined)
ac_allowed = False  # Will be set from DB in main()

# Connected mesh nodes (tracked for health checks)
# Start empty - nodes added when they actually connect
connected_clients = []
connect_fail_clients = []

# Temperature state
last_known_temp = None           # Last temperature reading from Node 2

# Node status DB update throttle (avoid DB hit on every mesh message)
_node_status_last_update = {}    # {node_id: timestamp}
NODE_STATUS_DB_INTERVAL = 30     # Seconds between DB updates per node

# Node last-heard timestamps (in memory, for skipping unnecessary pings)
_node_last_heard = {}            # {node_id: timestamp}

# ACK wait state for node health checks
waiting_for_ack_state = None

# =============================================================================
# RF24 Mesh Network Setup
# =============================================================================

radio = RF24(RF24_CE_PIN, RF24_CSN_PIN)
network = RF24Network(radio)
mesh = RF24Mesh(radio, network)

mesh.node_id = MESH_NODE_ID
log("info", f"Starting mesh controller node (v{VERSION})")

# Initialize mesh network with retry logic
if not mesh.begin():
    log("warn", "Mesh begin failed, retrying with renew_address()")
    for attempt in range(5):
        mesh.renew_address()
        if mesh.begin():
            log("info", "Mesh connected")
            break
        log("error", f"Mesh retry {attempt + 1}/5 failed")
        time.sleep(10)
else:
    log("info", f"Mesh ready, address {oct(mesh.mesh_address)}")

# Note: channel 97 and 1MBPS are RF24Mesh defaults set by mesh.begin()
# Only set PA level (does not interfere with mesh internals)
radio.setPALevel(RF24_PA_MAX)

# =============================================================================
# Socket Server (for mobile/remote clients)
# =============================================================================

server_thread = threading.Thread(target=start_server, daemon=True)
server_thread.start()

# =============================================================================
# Database Functions
# =============================================================================


def get_db_connection():
    """Create and return a new database connection."""
    return psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )


def get_last_ac_state():
    """
    Retrieve the most recent AC state from the database.

    Returns:
        tuple: (state: bool or None, timestamp: datetime or None)
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT date, time, ac_state FROM ac_data "
            "ORDER BY date DESC, time DESC LIMIT 1;"
        )
        result = cur.fetchone()

        if result:
            timestamp = datetime.strptime(
                f"{result['date']} {result['time']}",
                '%Y-%m-%d %H:%M:%S.%f'
            )
            return result['ac_state'], timestamp
        return None, None

    except Exception as error:
        log("error", f"DB read error: {error}")
        return None, None

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def get_ac_state() -> bool:
    """
    Get the current AC state (simple boolean).

    Returns:
        bool: True if AC is on, False otherwise
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT ac_state FROM ac_data "
            "ORDER BY date DESC, time DESC LIMIT 1;"
        )
        result = cur.fetchone()
        return result['ac_state'] if result else False

    except Exception as error:
        log("error", f"DB get AC state error: {error}")
        return False

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def database_log(state: bool) -> None:
    """
    Log an AC state change to the database.

    Skips logging if the state hasn't changed (prevents duplicate entries).

    Args:
        state: True for AC on, False for AC off
    """
    last_state, _ = get_last_ac_state()

    # Avoid duplicate entries
    if last_state == state:
        return

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO ac_data (date, time, ac_state) VALUES (%s, %s, %s);',
            (
                datetime.today().strftime('%Y-%m-%d'),
                datetime.now().strftime('%H:%M:%S.%f'),
                state
            )
        )
        conn.commit()
        log("db", f"AC state logged: {'ON' if state else 'OFF'}")

    except Exception as error:
        log("error", f"DB write error: {error}")

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def save_temps(max_temp: str, min_temp: str) -> bool:
    """
    Save temperature thresholds to the database.

    Uses upsert (INSERT ... ON CONFLICT) to handle both new and existing values.

    Args:
        max_temp: Maximum temperature threshold (AC turns on above this)
        min_temp: Minimum temperature threshold (AC turns off below this)

    Returns:
        bool: True if saved successfully, False otherwise
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ac_settings (key, value)
            VALUES ('max_temp', %s), ('min_temp', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
        """, (str(max_temp), str(min_temp)))
        conn.commit()
        log("db", f"Temps saved: max={max_temp}, min={min_temp}")
        return True

    except Exception as error:
        log("error", f"DB save temps error: {error}")
        return False

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def get_temps() -> tuple:
    """
    Read temperature thresholds from the database.

    Returns:
        tuple: (max_temp: float, min_temp: float) or defaults (78.0, 72.0)
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT key, value FROM ac_settings "
            "WHERE key IN ('max_temp', 'min_temp');"
        )
        results = cur.fetchall()

        temps = {row['key']: float(row['value']) for row in results}
        max_temp = temps.get('max_temp')
        min_temp = temps.get('min_temp')

        if max_temp is not None and min_temp is not None:
            return max_temp, min_temp

        log("warn", "Temps not in database, using defaults (78/72)")
        return 78.0, 72.0

    except Exception as error:
        log("error", f"DB read temps error: {error}")
        return 78.0, 72.0

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def save_ac_allowed(allowed: bool) -> bool:
    """
    Save AC allowed state to the database.

    Args:
        allowed: True if AC operation is permitted, False otherwise

    Returns:
        bool: True if saved successfully, False otherwise
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ac_settings (key, value)
            VALUES ('ac_allowed', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
        """, (str(allowed),))
        conn.commit()
        log("db", f"AC allowed saved: {allowed}")
        return True

    except Exception as error:
        log("error", f"DB save ac_allowed error: {error}")
        return False

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def get_ac_allowed() -> bool:
    """
    Read AC allowed state from the database.

    Returns:
        bool: True if AC operation is permitted, False otherwise (default: False)
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT value FROM ac_settings WHERE key = 'ac_allowed';"
        )
        result = cur.fetchone()

        if result:
            return result['value'] == 'True'

        log("info", "ac_allowed not in database, defaulting to False")
        return False

    except Exception as error:
        log("error", f"DB read ac_allowed error: {error}")
        return False

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# =============================================================================
# Node Tracking
# =============================================================================


def update_node_status(node_id: int, message: str = None) -> None:
    """
    Update a node's last_seen timestamp, status, and last message in the database.

    Throttled to one DB write per node per NODE_STATUS_DB_INTERVAL seconds
    to avoid slowing the main loop with frequent PostgreSQL connections.

    Args:
        node_id: Mesh node ID
        message: Last message received from this node (optional)
    """
    now = time.time()
    last_update = _node_status_last_update.get(node_id, 0)
    if now - last_update < NODE_STATUS_DB_INTERVAL:
        return  # Skip DB update, too recent

    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE mesh_nodes
            SET last_seen = NOW(), status = 'online', last_message = COALESCE(%s, last_message)
            WHERE node_id = %s;
        """, (message, node_id))
        conn.commit()
        _node_status_last_update[node_id] = now

    except Exception as error:
        log("error", f"DB update node status error: {error}")

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def mark_node_offline(node_id: int) -> None:
    """Mark a node as offline in the database."""
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE mesh_nodes SET status = 'offline' WHERE node_id = %s;",
            (node_id,)
        )
        conn.commit()

    except Exception as error:
        log("error", f"DB mark node offline error: {error}")

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def get_known_nodes() -> list:
    """
    Get all known nodes from the database.

    Returns:
        list of dicts: [{node_id, name, last_seen, status, last_message}, ...]
    """
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM mesh_nodes ORDER BY node_id;")
        return cur.fetchall()

    except Exception as error:
        log("error", f"DB get known nodes error: {error}")
        return []

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


# =============================================================================
# Mesh Network Communication
# =============================================================================


def send_message_to_node(node_id: int, message: str) -> bool:
    """
    Send a message to a mesh node with automatic retries.

    Refreshes mesh state between retry attempts to handle transient
    connection issues. Uses 3 retries with short delays to minimize
    blocking time (keeps mesh responsive).

    Args:
        node_id: Target node ID (1-255)
        message: Message string to send (max 24 bytes after encoding)

    Returns:
        bool: True if message sent successfully, False after 3 failed attempts
    """
    for attempt in range(3):
        # Refresh mesh state before each attempt
        mesh.update()
        if mesh.node_id == 0:
            mesh.dhcp()

        if mesh.write(message.encode('utf-8'), ord("M"), node_id):
            log("tx", describe_message(message), node=node_id)
            return True

        if attempt < 2:  # Don't sleep after last attempt
            time.sleep(0.25)

    log("error", f"Failed to send '{describe_message(message)}' after 3 attempts", node=node_id)
    return False


def send_settings_to_node() -> str:
    """
    Fetch current settings from database and send to Node 2 (LCD display)
    as a compact packet.

    Returns:
        str: The packet message sent, or empty string on failure
    """
    max_temp, min_temp = get_temps()
    if max_temp is not None and min_temp is not None:
        packet = build_packet(
            x=int(max_temp),
            n=int(min_temp),
            l=1 if ac_allowed else 0,
            a=1 if get_ac_state() else 0
        )
        send_message_to_node(NODE_TEMP_LCD, packet)
        return packet
    return ''


# =============================================================================
# Packet Protocol Functions
# =============================================================================


def build_packet(**kwargs) -> str:
    """
    Build a compact packet message from key-value pairs.

    Uses single-char keys for efficiency (32-byte RF24 limit):
        s=sync, t=temp, h=humidity, x=max, n=min,
        a=ac state, l=allow, b=brightness,
        k=heartbeat, q=query, r=reset, g=toggle perm

    Args:
        **kwargs: Key-value pairs to include in packet

    Returns:
        str: Formatted packet string "key1val1,key2val2,..."

    Example:
        build_packet(x=78, n=62, a=1, l=1) -> "x78,n62,a1,l1"
    """
    pairs = [f"{k}{v}" for k, v in kwargs.items()]
    return ",".join(pairs)


def is_packet(message: str) -> bool:
    """
    Check if a message is in the compact packet format.

    Packets start with a letter followed by a digit or minus sign.
    Legacy messages start with letter+letter (e.g., "TurnOnAC", "AC is ON").

    Args:
        message: Message string to check

    Returns:
        bool: True if message is a packet
    """
    if len(message) < 2:
        return False
    return message[0].isalpha() and (message[1].isdigit() or message[1] == '-')


def parse_packet(message: str) -> dict | None:
    """
    Parse a compact packet message into a dictionary.

    Args:
        message: Packet string "key1val1,key2val2,..."

    Returns:
        dict: Parsed key-value pairs, or None if invalid format

    Example:
        parse_packet("x78,n62,a1,l1") -> {"x": "78", "n": "62", "a": "1", "l": "1"}
        parse_packet("t62.5,h45.2") -> {"t": "62.5", "h": "45.2"}
    """
    if not is_packet(message):
        return None

    try:
        result = {}
        for pair in message.split(","):
            if len(pair) >= 2:
                key = pair[0]
                value = pair[1:]
                result[key] = value
        return result
    except Exception:
        return None


def describe_packet(packet: dict) -> str:
    """
    Return a human-readable description of a parsed packet.

    Args:
        packet: Parsed packet dict from parse_packet()

    Returns:
        str: Human-readable summary, e.g. "Temp 59.7°F, Humidity 52.0%"
    """
    parts = []
    if "s" in packet:
        parts.append("Sync")
    if "t" in packet:
        parts.append(f"Temp {packet['t']}\u00b0F")
    if "h" in packet:
        parts.append(f"Humidity {packet['h']}%")
    if "x" in packet:
        parts.append(f"Max {packet['x']}")
    if "n" in packet:
        parts.append(f"Min {packet['n']}")
    if "a" in packet:
        parts.append(f"AC {'ON' if packet['a'] == '1' else 'OFF'}")
    if "l" in packet:
        parts.append(f"Allow {'Yes' if packet['l'] == '1' else 'No'}")
    if "b" in packet:
        parts.append(f"Brightness {packet['b']}%")
    if "k" in packet:
        parts.append("Heartbeat")
    if "q" in packet:
        parts.append("Query State")
    if "r" in packet:
        parts.append("Reset")
    if "g" in packet:
        parts.append("Toggle Perm")
    return ", ".join(parts) if parts else "Unknown"


def describe_message(message: str) -> str:
    """
    Add a human-readable description to a message if it's a packet.

    Non-packet messages are returned unchanged.

    Args:
        message: Raw message string

    Returns:
        str: "raw (description)" for packets, or raw message for legacy
    """
    if is_packet(message):
        packet = parse_packet(message)
        if packet:
            return f"{message} ({describe_packet(packet)})"
    return message


# =============================================================================
# AC Control Functions
# =============================================================================


def toggle_ac_allowed() -> None:
    """Toggle the AC permission flag, save to DB, and notify Node 2."""
    global ac_allowed
    ac_allowed = not ac_allowed
    save_ac_allowed(ac_allowed)
    status = "enabled" if ac_allowed else "disabled"
    log("info", f"AC permission {status}")
    send_message_to_node(NODE_TEMP_LCD, build_packet(l=1 if ac_allowed else 0))


# =============================================================================
# Node Health Monitoring
# =============================================================================


def ping_node(node_id: int) -> None:
    """
    Send a health check ping to a node.

    Skips nodes that have sent us a message recently (within PING_INTERVAL),
    since heartbeat reception already proves they're alive. This avoids
    false-negative disconnections from mesh.write() ACK loss.

    Args:
        node_id: Node to ping
    """
    # Skip if we've heard from this node recently (heartbeat = proof of life)
    last_heard = _node_last_heard.get(node_id, 0)
    if time.time() - last_heard < PING_INTERVAL:
        return

    if not send_message_to_node(node_id, build_packet(k=1)):
        connect_fail_clients.append(node_id)
        if node_id in connected_clients:
            connected_clients.remove(node_id)
        mark_node_offline(node_id)
    else:
        if node_id not in connected_clients:
            connected_clients.append(node_id)
        if node_id in connect_fail_clients:
            connect_fail_clients.remove(node_id)


def start_waiting_for_ack(node_id: int, timeout: int = 15) -> None:
    """Initialize ACK wait state for a node."""
    global waiting_for_ack_state
    waiting_for_ack_state = {
        'node_id': node_id,
        'start_time': time.time(),
        'timeout': timeout
    }


def wait_for_ack():
    """
    Non-blocking check for ACK from a failed node.

    Returns:
        True: ACK received (node recovered)
        False: Timeout expired (node still failed)
        None: Still waiting
    """
    global waiting_for_ack_state
    if not waiting_for_ack_state:
        return None

    node_id = waiting_for_ack_state['node_id']
    elapsed = time.time() - waiting_for_ack_state['start_time']

    if node_id not in connect_fail_clients:
        waiting_for_ack_state = None
        return True

    if elapsed >= waiting_for_ack_state['timeout']:
        waiting_for_ack_state = None
        return False

    return None


def handle_failed_clients() -> None:
    """Start ACK wait process for all failed clients."""
    for node_id in connect_fail_clients:
        log("warn", f"Waiting for ACK from Node {node_id}")
        start_waiting_for_ack(node_id)


def handle_client_disconnection(client) -> None:
    """Remove a client from the connected list."""
    if client in connected_clients:
        connected_clients.remove(client)


# =============================================================================
# Main Event Loop
# =============================================================================


def main() -> None:
    """
    Main event loop for the mesh controller.

    Handles:
        - Periodic temperature polling and safety checks
        - Mesh network updates and message processing
        - Socket server message processing
        - Node health monitoring
    """
    global connected_clients, connect_fail_clients, waiting_for_ack_state
    global last_known_temp
    global ac_allowed

    # Load AC permission state from database
    ac_allowed = get_ac_allowed()
    log("info", f"AC permission loaded: {'enabled' if ac_allowed else 'disabled'}")

    # Load known nodes from database
    known_nodes = get_known_nodes()
    if known_nodes:
        log("info", f"Known nodes: {[n['name'] for n in known_nodes]}")
        log("info", "Waiting for nodes to check in...")

    last_ping_time = time.time()
    last_temp_received_time = time.time()
    warning_printed = False
    shutdown_executed = False

    try:
        while True:
            current_time = time.time()

            # -----------------------------------------------------------------
            # Temperature Monitoring
            # -----------------------------------------------------------------
            # Temp is received passively via keypad heartbeat packets (t=XX,h=XX)
            # No polling needed - just monitor for timeout

            # Warn if no temperature received
            if not warning_printed and (current_time - last_temp_received_time > TEMP_WARNING_TIMEOUT):
                log("warn", f"No temperature received in {TEMP_WARNING_TIMEOUT}s")
                warning_printed = True

            # Safety shutoff if temperature sensor is unresponsive
            if not shutdown_executed and (current_time - last_temp_received_time > TEMP_SAFETY_TIMEOUT):
                log("error", "No temperature in 120s - safety check")
                if get_ac_state():
                    log("error", "Turning off AC due to temp timeout")
                    send_message_to_node(NODE_AC_RELAY, build_packet(a=0))
                    database_log(False)
                shutdown_executed = True

            # -----------------------------------------------------------------
            # Node Health Checks
            # -----------------------------------------------------------------

            if current_time - last_ping_time >= PING_INTERVAL:
                for client in connected_clients:
                    ping_node(client)
                last_ping_time = current_time
                if connect_fail_clients:
                    handle_failed_clients()

            # Check ACK wait state
            ack_result = wait_for_ack()
            if ack_result is True:
                log("info", "ACK received, node recovered")
            elif ack_result is False:
                log("warn", "ACK timeout - node may be offline")

            # -----------------------------------------------------------------
            # Mesh Network Updates
            # -----------------------------------------------------------------

            # mesh.update() calls network.update() internally - no separate call needed.
            # mesh.dhcp() must run every iteration so DHCP registrations are processed.
            mesh.update()
            if mesh.node_id == 0:
                mesh.dhcp()

            # Process incoming mesh messages
            while network.available():
                header, payload = network.read(MAX_PAYLOAD_SIZE)

                try:
                    message = payload.decode('utf-8', 'ignore').strip().replace('\x00', '')
                    current_node = mesh.get_node_id(header.from_node)
                    log("rx", describe_message(message), node=current_node)

                    # Track node in memory and database
                    _node_last_heard[current_node] = time.time()
                    if current_node not in connected_clients:
                        connected_clients.append(current_node)
                        log("info", f"Node {current_node} joined, clients: {connected_clients}")
                    if current_node in connect_fail_clients:
                        connect_fail_clients.remove(current_node)
                    update_node_status(current_node, message)

                    # --- Message Handlers ---

                    # Handle compact packet messages (letter + digit format)
                    # Keys: s=sync, t=temp, h=humidity, x=max, n=min,
                    #        a=ac state, l=allow, b=brightness,
                    #        k=heartbeat, q=query, r=reset, g=toggle perm
                    if is_packet(message):
                        packet = parse_packet(message)
                        if packet:
                            # s: Sync request (keypad boot handshake)
                            if "s" in packet:
                                log("info", "Sync request - sending settings", node=current_node)
                                max_temp, min_temp = get_temps()
                                response = build_packet(
                                    x=int(max_temp) if max_temp else 78,
                                    n=int(min_temp) if min_temp else 70,
                                    l=1 if ac_allowed else 0,
                                    a=1 if get_ac_state() else 0
                                )
                                send_message_to_node(current_node, response)

                            # t: Temperature update from keypad
                            if "t" in packet:
                                last_known_temp = packet["t"]
                                warning_printed = False
                                shutdown_executed = False
                                last_temp_received_time = time.time()
                                # Respond so keypad knows controller is alive
                                if "s" not in packet:  # sync already gets a response
                                    send_message_to_node(current_node, build_packet(a=1 if get_ac_state() else 0))

                            # a: AC state (meaning depends on source node)
                            if "a" in packet and "s" not in packet and "t" not in packet:
                                ac_state = int(packet["a"]) == 1
                                if current_node == NODE_AC_RELAY:
                                    # State confirmation from relay - just log
                                    database_log(ac_state)
                                elif current_node == NODE_TEMP_LCD:
                                    # Command from keypad - forward to relay
                                    if ac_state:
                                        if send_message_to_node(NODE_AC_RELAY, build_packet(a=1)):
                                            send_message_to_node(NODE_TEMP_LCD, build_packet(a=1))
                                            database_log(True)
                                        else:
                                            log("error", "Failed to turn ON AC - AC_Interface not responding")
                                    else:
                                        if send_message_to_node(NODE_AC_RELAY, build_packet(a=0)):
                                            send_message_to_node(NODE_TEMP_LCD, build_packet(a=0))
                                            database_log(False)
                                        else:
                                            log("error", "Failed to turn OFF AC - AC_Interface not responding")

                            # g: Toggle AC permission (from keypad)
                            if "g" in packet:
                                toggle_ac_allowed()
                                if not ac_allowed:
                                    send_message_to_node(NODE_AC_RELAY, build_packet(a=0))
                                    send_message_to_node(NODE_TEMP_LCD, build_packet(a=0))
                                    database_log(False)

                            # x/n: Temperature thresholds from keypad (save, don't echo back)
                            if "x" in packet and "n" in packet and "s" not in packet:
                                save_temps(packet["x"], packet["n"])

                            # q: State query (relay requesting current AC state from DB)
                            if "q" in packet:
                                log("info", "State query - sending AC state", node=current_node)
                                last_state, last_timestamp = get_last_ac_state()
                                if (last_state is not None and last_timestamp and
                                        datetime.now() - last_timestamp <= timedelta(minutes=DB_STALE_THRESHOLD)):
                                    send_message_to_node(current_node, build_packet(a=1 if last_state else 0))
                                else:
                                    database_log(False)
                                    send_message_to_node(current_node, build_packet(a=0))

                            # k: Heartbeat (no action needed, node already tracked above)

                    # No legacy mesh handlers remaining - all nodes use packet protocol

                except UnicodeDecodeError as e:
                    log("error", f"Decode error: {e}")

            # -----------------------------------------------------------------
            # Socket Server Messages
            # -----------------------------------------------------------------

            while not message_queue.empty():
                client_socket, user_input = message_queue.get()
                log("rx", user_input, node="Socket")

                if user_input == "AC_Status":
                    last_state, last_timestamp = get_last_ac_state()
                    if (last_state is not None and last_timestamp and
                            datetime.now() - last_timestamp <= timedelta(minutes=DB_STALE_THRESHOLD)):
                        send_message_to_client(client_socket, "AC is ON" if last_state else "AC is OFF")
                    else:
                        database_log(False)
                        send_message_to_client(client_socket, "AC is OFF")

                elif user_input == "AC_Perm_Status":
                    send_message_to_client(client_socket, str(ac_allowed))

                elif user_input == "ToggleAC":
                    toggle_ac_allowed()

                elif user_input == "TurnOnAC":
                    if send_message_to_node(NODE_AC_RELAY, build_packet(a=1)):
                        send_message_to_node(NODE_TEMP_LCD, build_packet(a=1))
                        database_log(True)
                        send_message_to_client(client_socket, "AC is ON")
                    else:
                        send_message_to_client(client_socket, "Failed - AC_Interface not responding")

                elif user_input == "TurnOffAC":
                    if send_message_to_node(NODE_AC_RELAY, build_packet(a=0)):
                        send_message_to_node(NODE_TEMP_LCD, build_packet(a=0))
                        database_log(False)
                        send_message_to_client(client_socket, "AC is OFF")
                    else:
                        send_message_to_client(client_socket, "Failed - AC_Interface not responding")

                elif user_input == "getTemps":
                    max_temp, min_temp = get_temps()
                    if max_temp is not None and min_temp is not None:
                        send_message_to_client(client_socket, f"Temps:{max_temp},{min_temp}")
                    else:
                        send_message_to_client(client_socket, "Temps:---,---")

                elif user_input == "ResetNode":
                    success = send_message_to_node(NODE_AC_RELAY, build_packet(r=1))
                    send_message_to_client(client_socket, "ResetNode Success" if success else "ResetNode Failed")

                elif user_input == "current_temp":
                    # Return cached temp from keypad heartbeat (no mesh polling needed)
                    temp = last_known_temp if last_known_temp else "---"
                    send_message_to_client(client_socket, temp)

                elif user_input == "shut_down":
                    log("info", "Socket client disconnected")
                    handle_client_disconnection('mobile')

                elif user_input.startswith("setBrightness:"):
                    try:
                        brightness = int(user_input.split(":")[1])
                        brightness = max(0, min(100, brightness))
                        send_message_to_node(NODE_TEMP_LCD, build_packet(b=brightness))
                        log("info", f"LED brightness set to {brightness}%")
                    except (ValueError, IndexError):
                        send_message_to_client(client_socket, "Invalid format: use setBrightness:0-100")

                elif user_input.startswith("setTemps:"):
                    try:
                        _, temps = user_input.split(":")
                        max_temp, min_temp = temps.split(",")
                        save_temps(max_temp.strip(), min_temp.strip())
                        send_settings_to_node()
                    except ValueError:
                        send_message_to_client(client_socket, "Invalid format: use setTemps:max,min")

                elif user_input == "status":
                    # Return all status info in one response (uses cached temp from regular polling)
                    temp = last_known_temp if last_known_temp else "---"
                    ac_state = get_ac_state()
                    ac_str = "ON" if ac_state else "OFF"
                    max_temp, min_temp = get_temps()
                    max_str = str(max_temp) if max_temp else "---"
                    min_str = str(min_temp) if min_temp else "---"
                    allow_str = "True" if ac_allowed else "False"
                    # Include node status
                    nodes = get_known_nodes()
                    node_parts = []
                    for n in nodes:
                        node_parts.append(f"{n['name']}={n['status']}")
                    nodes_str = ";".join(node_parts) if node_parts else "---"
                    status_msg = f"status:temp={temp},ac={ac_str},max={max_str},min={min_str},allow={allow_str},nodes={nodes_str}"
                    send_message_to_client(client_socket, status_msg)

                else:
                    send_message_to_client(client_socket, f"Unknown command: {user_input}")

    except KeyboardInterrupt:
        log("info", "Interrupted by user")
        stop_server()
        sys.exit()


if __name__ == "__main__":
    main()
