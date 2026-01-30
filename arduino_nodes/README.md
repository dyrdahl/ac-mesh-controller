# Arduino Mesh Nodes

Arduino firmware for the RF24 mesh network nodes. Each node communicates with the Raspberry Pi controller (Node 0) using the compact packet protocol over nRF24L01+ radios.

## Nodes

### Node 1: AC_Interface

Controls an AC relay based on commands from the controller.

**Wiring:**

| Pin | Function |
|-----|----------|
| 2 | Connection status LED |
| 3 | Relay control (active LOW) |
| 4 | AC state debug LED |
| 9 | nRF24L01+ CE |
| 10 | nRF24L01+ CSN |

**Behavior:**
- Joins mesh network on boot and queries controller for current AC state (`q1`)
- Listens for AC commands: `a1` (relay on), `a0` (relay off)
- Reports relay state back to controller after each change
- Sends heartbeat every 30 seconds (10s when disconnected)
- Supports remote reset via `r1` command

### Node 2: keypadLCD

Temperature/humidity sensor with LCD display and keypad for local control.

**Wiring:**

| Pin | Function |
|-----|----------|
| 2 | DHT11 temperature/humidity sensor |
| 3 | RGB LED red (PWM) |
| 4 | AC state indicator LED |
| 5 | RGB LED green (PWM) |
| 6 | RGB LED blue (PWM) |
| 9 | nRF24L01+ CE |
| 10 | nRF24L01+ CSN |
| A0 | 4-button analog keypad |
| SDA/SCL | I2C LCD 16x2 (address `0x27`) |

**Behavior:**
- Reads DHT11 sensor every 20 seconds
- Sends temperature/humidity to controller in heartbeat packets (`t62.5,h45.2`)
- Displays 4 navigable screens: temperature, thresholds, AC control, LED brightness
- Auto-dims LCD backlight after 14 seconds of inactivity
- RGB LED color reflects temperature (blue &rarr; green &rarr; red)
- Sends threshold changes to controller as packets (`x78.0,n66.0`)
- Sends AC commands as packets (`a1`, `a0`, `g1` for toggle permission)
- Requests full settings sync on boot (`s1`)

## Packet Protocol

All nodes use the same compact packet format. See the [root README](../README.md#compact-packet-protocol) for the full protocol specification.

**Detection:** Packets start with a letter followed by a digit (e.g., `a1`, `t62.5`). This distinguishes them from any other message format.

## Required Libraries

Install via **Arduino IDE &rarr; Sketch &rarr; Include Library &rarr; Manage Libraries**:

| Library | Author | Used By |
|---------|--------|---------|
| RF24 | TMRh20 | All nodes |
| RF24Network | TMRh20 | All nodes |
| RF24Mesh | TMRh20 | All nodes |
| DHT sensor library | Adafruit | keypadLCD |
| Adafruit Unified Sensor | Adafruit | keypadLCD (dependency) |
| LiquidCrystal I2C | Marco Schwartz | keypadLCD |
| ezAnalogKeypad | ArduinoGetStarted | keypadLCD |

## Radio Configuration

All nodes share these settings (managed by RF24Mesh):

| Setting | Value |
|---------|-------|
| Channel | 97 |
| Data Rate | 1 Mbps |
| PA Level | MAX |
| Retries | 15 count, 15 delay |
| Max payload | 32 bytes |

## Uploading

1. Open the `.ino` file in Arduino IDE
2. Select your board (Arduino Nano / Uno)
3. Select the correct serial port
4. Upload

Each node's ID is set in the firmware (`NODE_ID` constant). Do not assign duplicate IDs.
