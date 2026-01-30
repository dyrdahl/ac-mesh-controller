"""
Socket Server Module for AC Control System

Provides a TCP socket server for mobile/remote client connections to the
AC control system. Clients can send commands and receive status updates
through this interface.

The server runs on localhost:65432 and handles multiple concurrent clients
using threading. Messages are queued for processing by the main controller.

Usage:
    This module is imported and started by controller.py. It should not
    be run directly.

    from socket_server import start_server, message_queue, send_message_to_client

Author: Shane Dyrdahl
"""

import socket
import threading
from queue import Queue

# =============================================================================
# Configuration
# =============================================================================

HOST = '127.0.0.1'  # Localhost only (use 0.0.0.0 for network access)
PORT = 65432        # Port for client connections

# =============================================================================
# Global State
# =============================================================================

server = None
server_thread = None
shutdown_event = threading.Event()
message_queue = Queue()  # Thread-safe queue for received messages
clients = []             # Active client connections

# =============================================================================
# Client Handler
# =============================================================================


def handle_client(client_socket: socket.socket) -> None:
    """
    Handle communication with a single connected client.

    Runs in a dedicated thread for each client. Receives messages and
    places them in the message queue for processing by the main controller.

    Args:
        client_socket: The connected client's socket object
    """
    while not shutdown_event.is_set():
        try:
            message = client_socket.recv(1024).decode('utf-8')
            if message:
                print(f"Received user input: {message}")
                message_queue.put((client_socket, message))
            else:
                break  # Empty message indicates client disconnected
        except (ConnectionResetError, BrokenPipeError, OSError):
            break

    client_socket.close()
    if client_socket in clients:
        clients.remove(client_socket)


# =============================================================================
# Server Control Functions
# =============================================================================


def start_server() -> None:
    """
    Start the socket server and begin accepting client connections.

    Runs in the calling thread (typically spawned as a daemon thread).
    Blocks until shutdown_event is set or server encounters an error.
    """
    global server

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind((HOST, PORT))
    except OSError as e:
        print(f"[FATAL] Failed to bind server: {e}")
        return

    server.listen(5)
    print(f"Server listening on {HOST}:{PORT}")

    while not shutdown_event.is_set():
        try:
            server.settimeout(1.0)  # Allow periodic shutdown checks
            client_socket, addr = server.accept()
            clients.append(client_socket)
            print(f"Accepted connection from {addr}")

            # Spawn handler thread for this client
            client_handler = threading.Thread(
                target=handle_client,
                args=(client_socket,),
                daemon=True
            )
            client_handler.start()

        except socket.timeout:
            continue
        except OSError:
            break


def stop_server() -> None:
    """
    Gracefully stop the socket server.

    Sets the shutdown event, closes the server socket, and waits for
    the server thread to terminate.
    """
    global server, server_thread

    print("\nShutting down server")
    shutdown_event.set()

    if server:
        server.close()
        server = None

    if server_thread:
        server_thread.join()
        server_thread = None


def restart_server() -> None:
    """Restart the server (soft restart - reuses existing state)."""
    start_server()


def hard_restart_server() -> None:
    """Full restart of the server (stops first, clears shutdown event)."""
    print("Restarting Server")
    stop_server()
    shutdown_event.clear()
    start_server()


# =============================================================================
# Client Communication
# =============================================================================


def send_message_to_client(client_socket: socket.socket, message: str) -> None:
    """
    Send a message to a connected client.

    Args:
        client_socket: The client's socket object
        message: The message string to send

    Note:
        On failure, triggers client disconnection handling in the main module.
    """
    try:
        client_socket.sendall(message.encode('utf-8'))
    except (BrokenPipeError, OSError) as e:
        print(f"[ERROR] Failed to send message to client: {e}")
        # Circular import handled at runtime
        from controller import handle_client_disconnection
        handle_client_disconnection(client_socket)
