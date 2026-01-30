# Pi Controller

The Raspberry Pi software that runs the AC control system. `controller.py` is the central server -- it manages the mesh network, processes commands from all sources, and logs state to PostgreSQL.

## Files

| File | Role | Runtime |
|------|------|---------|
| `controller.py` | Main server -- mesh controller, message router, DB logger | Must run 24/7 |
| `socket_server.py` | TCP socket module -- imported by controller | Starts with controller |
| `mobileConsole.py` | Interactive CLI client -- connects via socket | Run on demand |
| `table.SQL` | Database schema (two tables) | One-time setup |
| `setup-pi.sh` | System package/service installer | One-time setup |

## controller.py

The main event loop that ties everything together:

- Initializes the RF24Mesh network as Node 0 (master)
- Starts a TCP socket server on `localhost:65432` in a background thread
- Receives mesh messages from Arduino nodes and routes/processes them
- Receives socket commands from `mobileConsole.py` and executes them
- Logs AC state changes to PostgreSQL
- Monitors node health with periodic pings (60s interval)
- Implements temperature safety timeout (shuts off AC after 3 minutes without sensor data)

### Packet Logging

All mesh messages are logged with human-readable descriptions:

```
[04:59:36] RX  Node 2 → t59.7,h52.0 (Temp 59.7°F, Humidity 52.0%)
[04:59:36] TX  Node 2 ← a0 (AC OFF)
[04:59:39] RX  Socket → TurnOnAC
[04:59:39] TX  Node 1 ← a1 (AC ON)
[04:59:39] DB  AC state logged: ON
[04:59:40] RX  Node 1 → k1 (Heartbeat)
```

### Configuration

Constants defined at the top of `controller.py`:

| Constant | Value | Description |
|----------|-------|-------------|
| `MESH_CHANNEL` | 97 | RF24 radio channel |
| `RF24_CE_PIN` | 22 | GPIO pin for nRF24 Chip Enable |
| `RF24_CSN_PIN` | 0 | SPI CE0 for nRF24 Chip Select |
| `PING_INTERVAL` | 60s | Node health check interval |
| `TEMP_WARNING_TIMEOUT` | 90s | Warn if no temperature received |
| `TEMP_SAFETY_TIMEOUT` | 180s | Shut off AC if no temperature received |
| `DB_STALE_THRESHOLD` | 40 min | Ignore DB state older than this |

## socket_server.py

TCP server module imported by `controller.py`. Listens on `127.0.0.1:65432` and handles multiple concurrent clients via threading. Messages from clients are placed in a thread-safe queue for the controller's main loop to process.

Not intended to be run standalone.

## mobileConsole.py

Interactive terminal client that connects to the controller's socket server. Provides a full-screen TUI with Unicode box-drawing borders, live status display, and a menu for all system operations.

### Socket Commands

Commands sent over the socket connection (used by `mobileConsole.py`):

| Command | Response | Description |
|---------|----------|-------------|
| `status` | `status:temp=X,ac=X,...` | Full system status |
| `current_temp` | Temperature value | Latest cached temperature |
| `AC_Status` | `AC is ON` / `AC is OFF` | Current AC state |
| `AC_Perm_Status` | `True` / `False` | AC permission flag |
| `TurnOnAC` | `AC is ON` / failure msg | Turn AC on |
| `TurnOffAC` | `AC is OFF` / failure msg | Turn AC off |
| `ToggleAC` | *(none)* | Toggle AC permission flag |
| `getTemps` | `Temps:max,min` | Read temperature thresholds |
| `setTemps:max,min` | *(none)* | Update temperature thresholds |
| `setBrightness:0-100` | *(none)* | Set Node 2 RGB LED brightness |
| `ResetNode` | `ResetNode Success/Failed` | Restart AC relay node |
| `shut_down` | *(none)* | Graceful client disconnect |

## Database

PostgreSQL on localhost, database `postgres`, user `pi`.

### Schema (`table.SQL`)

**`ac_data`** -- AC state change log

| Column | Type | Description |
|--------|------|-------------|
| `date` | DATE | Date of state change (PK) |
| `time` | TIME | Time of state change (PK) |
| `ac_state` | BOOLEAN | true = ON, false = OFF |

**`ac_settings`** -- Key-value configuration store

| Column | Type | Description |
|--------|------|-------------|
| `key` | VARCHAR(50) | Setting name (PK) |
| `value` | VARCHAR(100) | Setting value |

Settings stored: `max_temp`, `min_temp`, `ac_allowed`

**`mesh_nodes`** -- Node status tracking

| Column | Type | Description |
|--------|------|-------------|
| `node_id` | INT | Mesh node ID (PK) |
| `name` | VARCHAR | Human-readable node name |
| `last_seen` | TIMESTAMP | Last message timestamp |
| `status` | VARCHAR | `online` / `offline` |
| `last_message` | VARCHAR | Last message content |

### Setup

```bash
psql -U pi -d postgres -f table.SQL
```

## Dependencies

### Python Packages

| Package | Purpose |
|---------|---------|
| `pyrf24` | RF24Mesh networking |
| `psycopg2-binary` | PostgreSQL driver |
| `colorama` | Cross-platform ANSI color support |
| `termcolor` | Colored terminal output |

### System Requirements

- Raspberry Pi with SPI enabled (`raspi-config`)
- PostgreSQL 9.5+
- Python 3.10+
- nRF24L01+ radio module wired to SPI bus

## Running

```bash
# Start the controller (in tmux or as a service)
python3 controller.py

# Connect with the interactive console
python3 mobileConsole.py
```

The controller logs to stdout. Use `tmux` or redirect to a file for persistent logging.
