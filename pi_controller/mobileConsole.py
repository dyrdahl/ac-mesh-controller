#!/usr/bin/env python3
"""
Mobile Console - AC Control System Client

Interactive terminal client for controlling the AC system remotely.
Connects to the controller's socket server and provides a menu-driven
interface for:
    - Viewing current temperature
    - Checking AC status (on/off)
    - Viewing/adjusting temperature thresholds
    - Manually cycling AC on/off
    - Resetting nodes
    - Toggling AC permissions

Usage:
    python mobileConsole.py

    Requires the main controller (controller.py) to be running.

Author: Shane Dyrdahl
"""

import os
import re
import socket
import sys
import threading
import time
from queue import Queue, Empty

from colorama import init
from termcolor import colored

# =============================================================================
# Configuration
# =============================================================================

HOST = 'localhost'
PORT = 65432

# =============================================================================
# Global State
# =============================================================================

init()  # Initialize colorama for cross-platform colored output

response_queue = Queue()
interrupt_event = threading.Event()

# =============================================================================
# Network Communication
# =============================================================================


def listen_for_responses(client_socket: socket.socket) -> None:
    """
    Background thread to receive responses from the server.

    Places received messages in the response queue for processing.
    Sets interrupt_event on shutdown/restart commands.

    Args:
        client_socket: Connected socket to the controller
    """
    while True:
        try:
            response = client_socket.recv(1024).decode('utf-8')
            if response:
                response_queue.put(response)
                if response.lower() in ["shutdown", "restart"]:
                    interrupt_event.set()
            else:
                break
        except Exception as e:
            print(f"Error receiving response: {e}")
            break


def clear_response_queue() -> None:
    """Drain any pending responses from the queue."""
    try:
        while True:
            response_queue.get_nowait()
    except Empty:
        pass


def wait_for_response(timeout: int = 5, expected: list[str] = None) -> str | None:
    """
    Wait for a response from the server.

    Args:
        timeout: Maximum seconds to wait
        expected: Optional list of expected response keywords

    Returns:
        The response string, or None on timeout
    """
    try:
        response = response_queue.get(timeout=timeout)
        if expected and not any(keyword in response for keyword in expected):
            print(colored(f"[UNEXPECTED] Received: {response}", 'yellow'))
        return response
    except Exception:
        print(colored(f"[TIMEOUT] No response after {timeout} seconds.", 'red', attrs=['bold']))
        return None


# =============================================================================
# Program Control
# =============================================================================


def restart_program() -> None:
    """Restart this client program."""
    python = sys.executable
    os.execl(python, python, *sys.argv)


def handle_interrupt() -> None:
    """
    Background thread to handle server-initiated shutdown/restart.

    Waits for interrupt_event and processes shutdown or restart commands.
    """
    while True:
        interrupt_event.wait()
        response = wait_for_response()
        if response is None:
            interrupt_event.clear()
            continue

        if response.lower() == "shutdown":
            print("Received shutdown command. Exiting...")
            os._exit(0)
        elif response.lower() == "restart":
            print("Received restart command. Restarting...")
            restart_program()

        interrupt_event.clear()


# =============================================================================
# Display Helpers
# =============================================================================

BOX_W = 48  # Total width including border characters


def box_top(title: str = "") -> str:
    """Top border: ╔═══ TITLE ═══╗"""
    if title:
        inner = f" {title} "
        pad = BOX_W - 2 - 2 - len(inner)
        return "╔" + "═" * 2 + inner + "═" * pad + "╗"
    return "╔" + "═" * (BOX_W - 2) + "╗"


def box_mid(heavy: bool = True) -> str:
    """Mid separator: ╠══════╣ (heavy) or ╠──────╣ (light)"""
    char = "═" if heavy else "─"
    return "╠" + char * (BOX_W - 2) + "╣"


def box_bot() -> str:
    """Bottom border: ╚══════╝"""
    return "╚" + "═" * (BOX_W - 2) + "╝"


def box_row(text: str = "") -> str:
    """Content row: ║ text padded ║"""
    inner = BOX_W - 2
    # Strip ANSI codes to calculate visible length
    visible = re.sub(r'\x1b\[[0-9;]*m', '', text)
    padding = inner - len(visible)
    if padding < 0:
        padding = 0
    return "║ " + text + " " * (padding - 1) + "║"


def display_response_block(response: str, color: str = "white", title: str = "SERVER RESPONSE") -> None:
    """
    Display a formatted response box in the terminal.

    Args:
        response: The message to display
        color: Terminal color for the response text
        title: Header text for the box
    """
    print(box_top(title))
    print(box_row())
    print(box_row("  " + colored(response, color)))
    print(box_row())
    print(box_bot())


def fetch_status(send_command_func) -> dict:
    """
    Fetch current system status from the controller.

    Args:
        send_command_func: Function to send commands to server

    Returns:
        dict with keys: temp, ac_status, max_temp, min_temp, ac_allowed
    """
    status = {
        'temp': None,
        'ac_status': None,
        'max_temp': None,
        'min_temp': None,
        'ac_allowed': None,
        'nodes': {}
    }

    # Fetch all status in one request
    clear_response_queue()
    send_command_func("status")

    # Keep reading until we get a status response (skip stale responses)
    start_time = time.time()
    while time.time() - start_time < 3:
        try:
            response = response_queue.get(timeout=0.5)
            if response and response.startswith("status:"):
                # Parse: status:temp=XX,ac=ON,max=XX,min=XX,allow=True
                data = response[7:]  # Remove "status:" prefix
                for part in data.split(","):
                    if "=" in part:
                        key, value = part.split("=", 1)
                        if key == "temp" and value != "---":
                            status['temp'] = value
                        elif key == "ac":
                            status['ac_status'] = f"AC is {value}"
                        elif key == "max" and value != "---":
                            status['max_temp'] = value
                        elif key == "min" and value != "---":
                            status['min_temp'] = value
                        elif key == "allow":
                            status['ac_allowed'] = value
                        elif key == "nodes" and value != "---":
                            for node_entry in value.split(";"):
                                if "=" in node_entry:
                                    name, node_status = node_entry.split("=", 1)
                                    status['nodes'][name] = node_status
                break  # Got status, exit loop
            # else: skip non-status response and keep looking
        except Empty:
            continue

    return status


def display_status_header(status: dict) -> None:
    """
    Display the status dashboard above the menu.

    Args:
        status: dict from fetch_status()
    """
    print(box_top("SYSTEM STATUS"))

    # Current temperature
    temp_str = f"{float(status['temp']):.1f}\u00b0F" if status['temp'] else "---"
    temp_color = 'blue'
    label_w = 10
    print(box_row(f" {'Temp:':<{label_w}}" + colored(temp_str, temp_color)))

    # AC Status
    if status['ac_status'] == "AC is ON":
        ac_val = "ON"
        ac_color = 'light_blue'
    elif status['ac_status'] == "AC is OFF":
        ac_val = "OFF"
        ac_color = 'red'
    else:
        ac_val = "---"
        ac_color = 'white'
    print(box_row(f" {'AC:':<{label_w}}" + colored(ac_val, ac_color)))

    # Min/Max thresholds
    if status['max_temp'] and status['min_temp']:
        thresh_str = f"{float(status['min_temp']):.0f} - {float(status['max_temp']):.0f}"
    else:
        thresh_str = "---"
    print(box_row(f" {'Range:':<{label_w}}" + colored(thresh_str, 'cyan')))

    # AC Allowed
    if status['ac_allowed'] == "True":
        allow_str = "Yes"
        allow_color = 'green'
    elif status['ac_allowed'] == "False":
        allow_str = "No"
        allow_color = 'red'
    else:
        allow_str = "---"
        allow_color = 'white'
    print(box_row(f" {'Allow:':<{label_w}}" + colored(allow_str, allow_color)))

    # Node status
    if status.get('nodes'):
        print(box_mid(heavy=False))
        print(box_row(" NODES"))
        for name, node_status in status['nodes'].items():
            if node_status == "online":
                indicator = colored("\u25cf", 'green')
                state_str = colored("online", 'green')
            else:
                indicator = colored("\u25cf", 'red')
                state_str = colored("offline", 'red')
            # Pad name to align state column
            name_padded = f"{name:<28}"
            print(box_row(f"   {indicator} {name_padded}{state_str}"))

    print(box_mid(heavy=True))


def wait_for_menu() -> None:
    """Pause and wait for user to press Enter."""
    input(colored("     Press Enter...", "cyan", attrs=["bold"]))


# =============================================================================
# Main Application
# =============================================================================


def main() -> None:
    """
    Main application loop.

    Connects to the controller server and presents an interactive menu
    for controlling the AC system.
    """
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Connection retry loop
    while True:
        try:
            client.connect((HOST, PORT))
            break
        except (ConnectionRefusedError, ConnectionResetError):
            print(f"Could not connect to server at {HOST}:{PORT}, retrying in 5 seconds...")
            time.sleep(5)

    os.system('clear')

    # Start background threads
    listener_thread = threading.Thread(target=listen_for_responses, args=(client,), daemon=True)
    listener_thread.start()

    interrupt_thread = threading.Thread(target=handle_interrupt, daemon=True)
    interrupt_thread.start()

    def send_command(text: str) -> None:
        """Send a command to the server with error handling."""
        try:
            client.sendall(text.encode('utf-8'))
        except BrokenPipeError:
            print(colored("Lost connection to server (Broken pipe).", 'red', attrs=['bold']))
            choice = input(colored("Reconnect? (y/n): ", 'yellow')).strip().lower()
            if choice == 'y':
                restart_program()
            else:
                sys.exit(1)
        except Exception as e:
            print(colored(f"ERROR: Failed to send message: {e}", 'red', attrs=['bold']))
            sys.exit(1)

    try:
        while True:
            # Move cursor to top-left and overwrite in place (avoids blank flash)
            print("\033[H", end="")

            # Fetch and display current status
            status = fetch_status(send_command)
            display_status_header(status)

            # Display menu
            print(box_row())
            print(box_row("  [a] Current Temperature"))
            print(box_row("  [b] Check Status of AC"))
            print(box_row("  [c] Current AC Min/Max"))
            print(box_row("  [d] Adjust AC Thresholds"))
            print(box_row("  [e] Cycle AC"))
            print(box_row("  [f] Reset AC Node"))
            print(box_row("  [g] Toggle AC Permissions"))
            print(box_row("  [h] LED Brightness"))
            print(box_row())
            print(box_row("  [z] Exit"))
            print(box_bot())
            # Clear any leftover lines from previous frame
            print("\033[J", end="")

            user_input = input(colored("  >>> ", 'light_green', attrs=['bold'])).lower()

            # --- Option A: Current Temperature ---
            if user_input == 'a':
                clear_response_queue()
                send_command("current_temp")

                response = None
                for attempt in range(3):
                    try:
                        response = response_queue.get(timeout=3)
                        break
                    except Empty:
                        print(colored(f"  [Attempt {attempt + 1}] No response received...", 'yellow'))

                if response:
                    display_response_block(response, 'blue')
                else:
                    display_response_block("Failed to get temp after multiple attempts.", 'red', title="ERROR")
                wait_for_menu()

            # --- Option B: AC Status ---
            elif user_input == 'b':
                clear_response_queue()
                send_command('AC_Status')

                response = wait_for_response()
                if response is None:
                    continue

                if response in ["AC is ON", "AC is OFF"]:
                    color = 'light_blue' if response == "AC is ON" else 'red'
                    display_response_block(response, color)
                else:
                    print(colored(f"Unexpected server response: {response}", 'red'))
                wait_for_menu()

            # --- Option C: Temperature Thresholds ---
            elif user_input == 'c':
                clear_response_queue()
                send_command('getTemps')

                response = wait_for_response()
                if response is None:
                    continue

                match = re.match(r"Temps:\s*([\d.]+),([\d.]+)", response)
                if match:
                    max_temp = float(match.group(1))
                    min_temp = float(match.group(2))
                    temp_summary = f"Max: {max_temp:.1f} | Min: {min_temp:.1f}"
                    display_response_block(temp_summary, color='blue', title="TEMP THRESHOLDS")
                else:
                    display_response_block("Failed to parse temperatures", color='red', title="ERROR")
                wait_for_menu()

            # --- Option D: Adjust Temperature Thresholds ---
            elif user_input == 'd':
                clear_response_queue()

                print(box_top("ADJUST THRESHOLDS"))
                print(box_row())

                while True:
                    try:
                        max_temp = int(input(colored("  Max Temp >>> ", 'light_blue', attrs=['bold'])))
                        min_temp = int(input(colored("  Min Temp >>> ", 'light_yellow', attrs=['bold'])))

                        if max_temp <= 0 or min_temp <= 0:
                            raise ValueError("Temperatures must be positive integers.")

                        if max_temp >= min_temp:
                            break
                        else:
                            print(colored("  Error: MAX must be >= MIN", 'red', attrs=['bold']))
                    except ValueError:
                        print(colored("  Error: Please input a valid integer", 'red', attrs=['bold']))

                print(box_row(f"  Max: {max_temp}"))
                print(box_row(f"  Min: {min_temp}"))
                print(box_bot())

                confirm = input(colored("  Lock in temps? (y/n) >>> ", 'light_green', attrs=['bold'])).lower()
                if confirm == 'y':
                    send_command(f"setTemps: {max_temp},{min_temp}")

            # --- Option E: Cycle AC On/Off ---
            elif user_input == 'e':
                clear_response_queue()
                send_command('AC_Status')

                response = wait_for_response()
                if response is None:
                    continue

                if response in ["AC is ON", "AC is OFF"]:
                    if response == "AC is ON":
                        color = 'light_blue'
                        target_state = 'off'
                    else:
                        color = 'red'
                        target_state = 'on'

                    display_response_block(response, color)
                else:
                    display_response_block(f"Unexpected response: {response}", 'red')
                    continue

                confirm = input(colored(f"     Turn {target_state} AC? (y or n) >> ", 'light_green', attrs=['bold'])).lower()

                if confirm == 'y':
                    action = 'TurnOnAC' if target_state == 'on' else 'TurnOffAC'
                    send_command(action)
                    print(f"   Turning {target_state} AC...")
                else:
                    print("   Keeping current AC State")

            # --- Option F: Reset AC Node ---
            elif user_input == 'f':
                clear_response_queue()
                send_command("ResetNode")

                response = wait_for_response()
                if response is None:
                    continue

                if response in ["ResetNode Success", "ResetNode Failed"]:
                    color = 'light_blue' if response == "ResetNode Success" else 'red'
                    display_response_block(response, color)
                else:
                    print(colored(f"Unexpected server response: {response}", 'red'))
                wait_for_menu()

            # --- Option G: Toggle AC Permissions ---
            elif user_input == 'g':
                clear_response_queue()
                send_command('AC_Perm_Status')

                response = wait_for_response()
                if response is None:
                    continue

                if response in ["True", "False"]:
                    if response == "True":
                        color = 'light_blue'
                        target_action = 'disable'
                    else:
                        color = 'red'
                        target_action = 'enable'

                    display_response_block(f"AC Allowed: {response}", color)
                else:
                    display_response_block(f"Unexpected server response: {response}", 'red')
                    continue

                confirm = input(colored(f"     {target_action.capitalize()} AC? (y or n) >> ", 'light_green', attrs=['bold'])).lower()

                if confirm == 'y':
                    send_command('ToggleAC')
                    print(f"   {target_action.capitalize()}ing AC...")
                else:
                    print("   Keeping current AC permissions")

            # --- Option H: LED Brightness ---
            elif user_input == 'h':
                print(box_top("LED BRIGHTNESS"))
                print(box_row("  Range: 0 - 100%"))
                print(box_bot())
                while True:
                    try:
                        brightness = int(input(colored("  Brightness >>> ", 'light_blue', attrs=['bold'])))
                        if 0 <= brightness <= 100:
                            break
                        else:
                            print(colored("  Error: Must be between 0 and 100", 'red', attrs=['bold']))
                    except ValueError:
                        print(colored("  Error: Please input a valid integer", 'red', attrs=['bold']))

                send_command(f"setBrightness:{brightness}")
                display_response_block(f"Brightness set to {brightness}%", 'cyan', title="LED BRIGHTNESS")
                wait_for_menu()

            # --- Option Z: Exit ---
            elif user_input == 'z':
                print("   Now Exiting...")
                sys.exit()

            else:
                print(colored("   INVALID CHOICE", 'red'))

    except KeyboardInterrupt:
        print("\n   Exiting Mobile Console")
        send_command("shut_down")
        sys.exit()


if __name__ == "__main__":
    main()
