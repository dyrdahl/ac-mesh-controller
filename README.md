# AC Control System

A distributed home automation system for controlling an AC unit via an nRF24L01+ mesh network. A Raspberry Pi acts as the central controller, coordinating Arduino nodes that handle relay switching and temperature monitoring.

## Hardware

<p align="center">
  <img src="images/pi_controller.jpg" alt="Raspberry Pi Controller" width="600">
</p>
<p align="center"><em>Raspberry Pi controller with nRF24L01+ radio module</em></p>

| Keypad Node (Boot) | Keypad Node (Main Screen) |
|:------------------:|:-------------------------:|
| ![Boot screen](images/keypad_node_boot.jpg) | ![Main screen](images/keypad_node_main.jpg) |

### Keypad Node Case

3D printed enclosure for the keypad node.

| Front (Outside) | Front (Inside) |
|:---------------:|:--------------:|
| ![Front outside](images/keypad_case/front_display_outside.jpg) | ![Front inside](images/keypad_case/front_display_inside.jpg) |

| Sensor Side (Outside) | Sensor Side (Inside) |
|:---------------------:|:--------------------:|
| ![Sensor side outside](images/keypad_case/sensor_side_outside.jpg) | ![Sensor side inside](images/keypad_case/sensor_side_inside.jpg) |

| Logic Board Side (Outside) | Logic Board Side (Inside) |
|:--------------------------:|:-------------------------:|
| ![Logic board outside](images/keypad_case/logic_board_outside.jpg) | ![Logic board inside](images/keypad_case/logic_board_inside.jpg) |

### Radio Module Capacitor Mod

The nRF24L01+ PA+LNA modules draw up to **115mA peak** during transmit at max power. This causes voltage sag that disrupts the rapid packet exchanges required for mesh DHCP handshakes. Symptoms include unreliable initial connections (e.g., needing to touch the antenna to connect) even though normal operation works once established.

**Fix:** Add capacitors directly across the module's VCC and GND pins:

| Component | Value | Purpose                                                            |
|-----------|-------|--------------------------------------------------------------------|
| Electrolytic | **100µF** | Absorbs bulk current dips during TX bursts                         |
| Ceramic | **68nF (0.068µF)** | Filters high-frequency switching noise. Use up to 100nF capacitor. |

```
3.3V ──────┬─────────┬──────── nRF24L01+ VCC
           │         │
      ┌────┴──┐ ┌────┴──┐
      │100µF  │ │ 68nF  │
      │electro│ │ceramic│
      └────┬──┘ └────┬──┘
           │         │
GND ───────┴─────────┴──────── nRF24L01+ GND
```

- **Electrolytic:** long leg (+) to VCC, short leg (-) to GND
- **Ceramic:** no polarity
- Mount as close to the module pins as possible

<p align="center">
  <img src="images/radio_mod.jpg" alt="Capacitor mod on nRF24L01+" width="400">
</p>

## Architecture

```
                        Raspberry Pi (Node 0)
               ┌──────────────────────────────────┐
               │  controller.py                   │
               │    Mesh controller + DB logger    │
               │                                   │
               │  socket_server.py                 │
               │    TCP server (localhost:65432)    │
               ├──────────────────────────────────┤
               │  mobileConsole.py                 │
               │    Interactive CLI client         │
               └──────┬──────────────────┬─────────┘
                      │  nRF24L01+ Mesh  │
                      │  Channel 97      │
            ┌─────────┴───┐         ┌────┴──────────┐
            │  Arduino    │         │  Arduino      │
            │  Node 1     │         │  Node 2       │
            │             │         │               │
            │  AC Relay   │         │  DHT11 Sensor │
            │  Interface  │         │  16x2 LCD     │
            │             │         │  4-btn Keypad  │
            │             │         │  RGB LED      │
            └─────────────┘         └───────────────┘
```

The controller manages all communication between nodes, logs AC state changes to PostgreSQL, and exposes a socket interface for the interactive console client.

## Directory Structure

```
.
├── README.md
├── pi_controller/          Raspberry Pi software
│   ├── controller.py         Main server (runs 24/7)
│   ├── socket_server.py      TCP socket module (imported by controller)
│   ├── mobileConsole.py      Interactive CLI client
│   ├── table.SQL             Database schema
│   └── setup-pi.sh           System setup script
│
└── arduino_nodes/          Arduino firmware
    ├── AC_Interface/
    │   └── AC_Interface.ino  Node 1: AC relay controller
    └── keypadLCD/
        └── keypadLCD.ino     Node 2: Temp sensor + LCD + keypad
```

## Mesh Network

| Node | Device | Role |
|------|--------|------|
| 0 | Raspberry Pi 3 | Controller, database, socket server |
| 1 | Arduino Nano | AC relay switching |
| 2 | Arduino Nano | Temperature/humidity sensor, LCD display, keypad input |

All nodes communicate through Node 0 using [RF24Mesh](https://nrf24.github.io/RF24Mesh/) on channel 97 at 1 Mbps with maximum transmit power.

## Compact Packet Protocol

All mesh communication uses a compact key-value format designed to fit within the 32-byte RF24 payload limit.

**Format:** `key1value1,key2value2,...` (single-character keys, no delimiters between key and value)

| Key | Meaning | Example | Direction |
|-----|---------|---------|-----------|
| `s` | Sync request | `s1` | Node 2 &rarr; Controller |
| `t` | Temperature (&deg;F) | `t62.5` | Node 2 &rarr; Controller |
| `h` | Humidity (%) | `h45.2` | Node 2 &rarr; Controller |
| `x` | Max temp threshold | `x78` | Both directions |
| `n` | Min temp threshold | `n66` | Both directions |
| `a` | AC state (1=on, 0=off) | `a1` | Both directions |
| `l` | AC allowed (1=yes, 0=no) | `l1` | Controller &rarr; Node 2 |
| `b` | LED brightness (0-100) | `b75` | Controller &rarr; Node 2 |
| `k` | Heartbeat | `k1` | Both directions |
| `q` | Query state | `q1` | Node 1 &rarr; Controller |
| `r` | Reset node | `r1` | Controller &rarr; Node 1 |
| `g` | Toggle AC permission | `g1` | Node 2 &rarr; Controller |

**Examples:**
- `t62.5,h45.2` -- Temperature 62.5&deg;F, humidity 45.2% (heartbeat from Node 2)
- `x78,n66,a1,l1` -- Settings sync from controller to Node 2
- `a0` -- Turn AC off / report AC is off

## Quick Start

### Prerequisites

- Raspberry Pi with nRF24L01+ module connected via SPI
- PostgreSQL server running locally
- Python 3.10+ with `pyrf24`, `psycopg2-binary`, `colorama`, `termcolor`

### Database Setup

```bash
psql -U pi -d postgres -f pi_controller/table.SQL
```

### Running

Start the controller (must run continuously):

```bash
python3 pi_controller/controller.py
```

Connect with the interactive console (on demand):

```bash
python3 pi_controller/mobileConsole.py
```

### Arduino Nodes

Open the `.ino` files in Arduino IDE, install the [required libraries](arduino_nodes/), select your board, and upload.

## Safety Features

- **Temperature timeout** -- AC shuts off automatically if no temperature data is received for 3 minutes
- **AC permission flag** -- Global enable/disable prevents unintended AC operation; persisted in database
- **Stale state detection** -- Database entries older than 40 minutes are treated as stale; AC defaults to off
- **Mesh retries** -- All sends retry up to 3 times with 250ms delays
- **Node health checks** -- Controller pings nodes every 60 seconds and tracks online/offline status

## Further Reading

- [`pi_controller/`](pi_controller/) -- Server software details, database schema, socket protocol
- [`arduino_nodes/`](arduino_nodes/) -- Hardware wiring, firmware details, required libraries
