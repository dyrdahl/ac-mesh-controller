/**
 * Node 2: Temperature/LCD Controller
 *
 * This node handles:
 *   - DHT11 temperature/humidity sensor readings
 *   - 16x2 LCD display with menu navigation
 *   - 4-button analog keypad for user input
 *   - Temperature threshold management (max/min temps)
 *   - AC control commands based on temperature
 *
 * Hardware Connections:
 *   - DHT11 Sensor: Pin 2
 *   - RGB Red (temp): Pin 3
 *   - AC State LED: Pin 4
 *   - RGB Green (temp): Pin 5
 *   - RGB Blue (temp): Pin 6
 *   - nRF24L01+ CE: Pin 9
 *   - nRF24L01+ CSN: Pin 10
 *   - Analog Keypad: A0
 *   - LCD: I2C (0x27)
 *
 * Serial: 115200 baud
 *
 * Author: Shane Dyrdahl
 */

#include <SPI.h>
#include <RF24.h>
#include <RF24Network.h>
#include <RF24Mesh.h>
#include <ezAnalogKeypad.h>
#include <DHT.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// =============================================================================
// Pin Definitions
// =============================================================================

#define DHTPIN 2
#define RGB_RED 3        // RGB LED red (PWM)
#define LED_PIN 4        // AC state indicator
#define RGB_GREEN 5      // RGB LED green (PWM)
#define RGB_BLUE 6       // RGB LED blue (PWM)
#define CE_PIN 9
#define CSN_PIN 10

// =============================================================================
// Configuration Constants
// =============================================================================

#define DHTTYPE DHT11
#define NODE_ID 2

// Analog keypad ADC values (hardware-specific)
#define KEY1_ADC 117
#define KEY2_ADC 252
#define KEY3_ADC 336
#define KEY4_ADC 507

// Timing intervals (milliseconds)
const unsigned long INACTIVITY_TIMEOUT = 14000;   // LCD backlight timeout
const unsigned long DHT_INTERVAL = 20000;         // Temperature reading interval
const unsigned long ACK_INTERVAL = 20000;         // Heartbeat ACK interval (20s for debugging)
const unsigned long ACK_INTERVAL_RETRY = 10000;   // Disconnected: 10 seconds

// =============================================================================
// Hardware Initialization
// =============================================================================

DHT dht(DHTPIN, DHTTYPE);
LiquidCrystal_I2C lcd(0x27, 16, 2);
ezAnalogKeypad buttonArray(A0);

RF24 radio(CE_PIN, CSN_PIN);
RF24Network network(radio);
RF24Mesh mesh(radio, network);

// =============================================================================
// LCD Frame Indices
// =============================================================================

#define FRAME_TEMP       0
#define FRAME_THRESHOLDS 1
#define FRAME_AC         2
#define FRAME_BRIGHTNESS 3
#define FRAME_SLEEP      4
#define NUM_ACTIVE_FRAMES 4  // Frames 0-3; sleep is entered via inactivity only

// =============================================================================
// State Variables
// =============================================================================

// Temperature thresholds
float maxTemp = 99.0;
float minTemp = 20.0;

// Sensor readings
float temperatureValue = NAN;
float humidityValue = NAN;

// AC state
bool acState = false;
bool acAllowed = false;
bool syncPending = true;  // Send sync packet on first loop iteration

// UI state
int currentFrame = FRAME_TEMP;
int rgbBrightness = 100;  // RGB LED brightness (0-100%)
bool editMode = false;
bool editingMaxTemp = true;
int customCursorLine = 0;

// Timing trackers
unsigned long lastActivityMillis = 0;
unsigned long dhtPreviousMillis = 0;
unsigned long lastAckTime = 0;
unsigned long lastControllerRx = 0;    // Last message received from controller
bool controllerOnline = false;
bool hasConnected = false;             // True after first successful controller contact
bool settingsDirty = false;            // Settings changed while offline, need resync

const unsigned long CONTROLLER_TIMEOUT = 45000;   // 45s without response = offline (debugging)

// Packet buffer for compact message protocol
String packetBuffer = "";

// Custom LCD character (selection arrow)
byte selectChar[] = {
  B00000, B00001, B00011, B00111,
  B01111, B00111, B00011, B00001
};

// =============================================================================
// Setup
// =============================================================================

void setup() {
  Serial.begin(115200);
  Serial.println(F("\n -----===== Node 2: Temp/LCD Controller =====----- "));
  Serial.flush();

  // Initialize pins
  pinMode(LED_PIN, OUTPUT);
  pinMode(RGB_RED, OUTPUT);
  pinMode(RGB_GREEN, OUTPUT);
  pinMode(RGB_BLUE, OUTPUT);
  analogWrite(RGB_RED, 0);
  analogWrite(RGB_GREEN, 0);
  analogWrite(RGB_BLUE, 0);

  // Initialize LCD with splash screen
  lcd.init();
  lcd.backlight();
  lcd.createChar(0, selectChar);
  lcd.clear();
  lcd.setCursor(3, 0);
  lcd.print("AC Control");
  lcd.setCursor(4, 1);
  lcd.print("Booting...");

  // Initialize keypad
  Serial.println(F("   Initializing keypad..."));
  buttonArray.setNoPressValue(0);
  buttonArray.registerKey('1', KEY1_ADC);
  buttonArray.registerKey('2', KEY2_ADC);
  buttonArray.registerKey('3', KEY3_ADC);
  buttonArray.registerKey('4', KEY4_ADC);
  buttonArray.setDebounceTime(50);

  // Initialize radio hardware
  if (!radio.begin()) {
    Serial.println(F("   ERROR: Radio hardware not responding!"));
    while (1) {}
  }

  // Initialize mesh network
  Serial.println(F("   Initializing mesh network..."));
  mesh.setNodeID(NODE_ID);
  while (!mesh.begin()) {
    Serial.println(F("   Mesh init failed, retrying..."));
    Serial.flush();
    delay(5000);
  }

  // Only set PA level and retries - mesh.begin() handles channel and data rate
  radio.setPALevel(RF24_PA_MAX);
  radio.setRetries(15, 15);

  Serial.print(F("   Node "));
  Serial.print(NODE_ID);
  Serial.print(F(" connected, address: "));
  Serial.println(mesh.mesh_address, OCT);
  Serial.flush();
  // RGB will show temperature color after first DHT read

  // Initialize temperature sensor first (need temp for sync packet)
  Serial.println(F("   Initializing DHT sensor..."));
  dht.begin();
  updateDHTSensor();

  // Sync packet will be sent on first loop() iteration (needs mesh.update() running to receive response)

  // LED reflects AC state
  digitalWrite(LED_PIN, acState ? HIGH : LOW);
  Serial.println(F("   Setup complete.\n"));
  Serial.flush();

  // Show main display now that boot is complete
  displayFrame(currentFrame);
}

// =============================================================================
// Mesh Communication
// =============================================================================

/**
 * Send a message to a mesh node.
 * Skips immediately if controller is known offline.
 * Tries up to 3 times, returns false on failure.
 */
bool sendMessageToNode(int node, String message) {
  // Don't block if controller is known to be offline
  if (!controllerOnline && hasConnected) {
    return false;
  }

  char text[32];
  message.toCharArray(text, sizeof(text));

  for (int attempt = 0; attempt < 3; attempt++) {
    mesh.update();
    if (mesh.write(text, 'M', strlen(text), node)) {
      Serial.print(F("    >>> TX: "));
      Serial.println(message);
      Serial.flush();
      return true;
    }
    if (attempt < 2) delay(250);
  }

  // All attempts failed
  Serial.print(F("   TX FAIL: "));
  Serial.println(message);
  Serial.flush();
  setRGBOff();

  if (!mesh.checkConnection()) {
    Serial.println(F("   Mesh connection lost, reconnecting..."));
    mesh.renewAddress();
    if (mesh.mesh_address != MESH_DEFAULT_ADDRESS) {
      Serial.println(F("   Mesh reconnected"));
    }
  }

  return false;
}

/**
 * Send heartbeat with current sensor data to controller.
 * Always attempts to send (even when offline) so we can detect
 * when the controller comes back via its response packet.
 * Uses single attempt when offline to avoid blocking.
 */
void sendHeartbeat() {
  updateDHTSensor();

  // Build the message
  char msg[32];
  if (isnan(temperatureValue) && isnan(humidityValue)) {
    strcpy(msg, "ACK");
  } else {
    beginPacket();
    if (!isnan(temperatureValue)) addPacketFloat('t', temperatureValue);
    if (!isnan(humidityValue)) addPacketFloat('h', humidityValue);
    packetBuffer.toCharArray(msg, sizeof(msg));
  }

  // When offline, do a single non-blocking attempt
  if (!controllerOnline && hasConnected) {
    mesh.update();
    if (mesh.write(msg, 'M', strlen(msg), 0)) {
      Serial.print(F("    >>> TX: "));
      Serial.println(msg);
    }
    return;
  }

  // When online, use full send with retries
  sendMessageToNode(0, msg);
}

/**
 * Send temperature thresholds to controller as a compact packet.
 */
bool sendTempsToNode0() {
  beginPacket();
  addPacketFloat('x', maxTemp);
  addPacketFloat('n', minTemp);
  return sendPacket(0);
}

/**
 * Send current AC state to controller as a compact packet.
 */
void sendCurrentACState() {
  if (acAllowed) {
    sendMessageToNode(0, acState ? "a1" : "a0");
  }
}

// =============================================================================
// Compact Packet Protocol Functions
// =============================================================================
// Format: "key1value1,key2value2,..." (no = signs, single-char keys)
// Keys: s=sync, t=temp, h=humidity, x=max, n=min, a=ac, l=allow, g=toggle perm
// Max 32 bytes for RF24

void beginPacket() {
  packetBuffer = "";
}

void addPacketFloat(char key, float value) {
  if (packetBuffer.length() > 0) {
    packetBuffer += ",";
  }
  packetBuffer += key;
  packetBuffer += String(value, 1);  // 1 decimal place
}

void addPacketInt(char key, int value) {
  if (packetBuffer.length() > 0) {
    packetBuffer += ",";
  }
  packetBuffer += key;
  packetBuffer += String(value);
}

bool sendPacket(int node) {
  return sendMessageToNode(node, packetBuffer);
}

/**
 * Check if message is a compact packet.
 * Packets start with letter + digit (e.g., "s1" or "t62.5")
 * Legacy messages start with letter + letter (e.g., "TurnOnAC")
 */
bool isPacket(const char* payload) {
  if (strlen(payload) < 2) return false;
  return isalpha(payload[0]) && (isdigit(payload[1]) || payload[1] == '-');
}

/**
 * Get a value from a compact packet by single-char key.
 * Example: getPacketValue("x78,n62,a1", 'x') returns "78"
 */
String getPacketValue(const char* payload, char key) {
  String msg = payload;
  int i = 0;

  while (i < msg.length()) {
    // Check if this position has our key
    if (msg[i] == key) {
      // Extract value (from next char to comma or end)
      int valueStart = i + 1;
      int valueEnd = msg.indexOf(',', valueStart);
      if (valueEnd == -1) {
        valueEnd = msg.length();
      }
      return msg.substring(valueStart, valueEnd);
    }

    // Skip to next comma
    int nextComma = msg.indexOf(',', i);
    if (nextComma == -1) break;
    i = nextComma + 1;
  }

  return "";
}

/**
 * Send sync packet with current sensor data.
 */
void sendSyncPacket() {
  beginPacket();
  addPacketInt('s', 1);
  addPacketFloat('t', temperatureValue);
  addPacketFloat('h', humidityValue);
  sendPacket(0);
}

// =============================================================================
// RGB Temperature Display
// =============================================================================

void updateTempRGB(float tempF) {
  if (!controllerOnline || isnan(tempF)) {
    analogWrite(RGB_RED, 0);
    analogWrite(RGB_GREEN, 0);
    analogWrite(RGB_BLUE, 0);
    return;
  }

  int r = 0, g = 0, b = 0;

  if (tempF <= 50.0) {
    // Pure blue
    b = 255;
  } else if (tempF <= 65.0) {
    // Blue fades out, green fades in
    float t = (tempF - 50.0) / 15.0;
    g = (int)(255 * t);
    b = (int)(255 * (1.0 - t));
  } else if (tempF <= 80.0) {
    // Green fades out, red fades in
    float t = (tempF - 65.0) / 15.0;
    r = (int)(255 * t);
    g = (int)(255 * (1.0 - t));
  } else {
    // Pure red
    r = 255;
  }

  analogWrite(RGB_RED, r * rgbBrightness / 100);
  analogWrite(RGB_GREEN, g * rgbBrightness / 100);
  analogWrite(RGB_BLUE, b * rgbBrightness / 100);
}

void setRGBOff() {
  analogWrite(RGB_RED, 0);
  analogWrite(RGB_GREEN, 0);
  analogWrite(RGB_BLUE, 0);
}

// =============================================================================
// Temperature Sensor
// =============================================================================

void updateDHTSensor() {
  float newTemp = dht.readTemperature(true);  // Fahrenheit
  float newHumidity = dht.readHumidity();

  if (!isnan(newTemp)) {
    temperatureValue = newTemp;

    // Auto AC control based on temperature thresholds
    if (!acState && temperatureValue > maxTemp && acAllowed) {
      Serial.println(F("   Temp > max, turning AC ON"));
      Serial.flush();
      sendMessageToNode(0, "a1");
      acState = true;
    } else if (acState && temperatureValue < minTemp) {
      Serial.println(F("   Temp < min, turning AC OFF"));
      Serial.flush();
      sendMessageToNode(0, "a0");
      acState = false;
    }
  } else {
    temperatureValue = NAN;
  }

  humidityValue = !isnan(newHumidity) ? newHumidity : NAN;

  // Update RGB LED with current temperature
  updateTempRGB(temperatureValue);

  // Update display if on temperature frame
  if (currentFrame == FRAME_TEMP) {
    displayFrame(currentFrame);
  }
}

// =============================================================================
// LCD Display
// =============================================================================

void displayFrame(int frame) {
  lcd.clear();

  switch (frame) {
    case FRAME_TEMP:  // Temperature/Humidity
      lcd.setCursor(0, 0);
      lcd.print("Temp: ");
      if (isnan(temperatureValue)) {
        lcd.print("NaN");
      } else {
        lcd.print(temperatureValue, 1);
        lcd.print(" F");
      }
      lcd.setCursor(0, 1);
      lcd.print("Humidity: ");
      if (isnan(humidityValue)) {
        lcd.print("NaN");
      } else {
        lcd.print(humidityValue, 1);
        lcd.print("%");
      }
      break;

    case FRAME_THRESHOLDS:  // Temperature Thresholds
      lcd.setCursor(0, 0);
      lcd.print("Max Temp: ");
      lcd.print(maxTemp, 1);
      if (editMode && editingMaxTemp) {
        lcd.setCursor(15, 0);
        lcd.write(byte(0));
      }
      lcd.setCursor(0, 1);
      lcd.print("Min Temp: ");
      lcd.print(minTemp, 1);
      if (editMode && !editingMaxTemp) {
        lcd.setCursor(15, 1);
        lcd.write(byte(0));
      }
      break;

    case FRAME_AC:  // AC Control
      lcd.setCursor(0, 0);
      lcd.print("AC: ");
      lcd.print(acAllowed ? "Enable" : "Disable");
      if (customCursorLine == 0) {
        lcd.setCursor(15, 0);
        lcd.write(byte(0));
      }
      lcd.setCursor(0, 1);
      lcd.print("Current AC: ");
      lcd.print(acState ? "ON" : "OFF");
      if (customCursorLine == 1) {
        lcd.setCursor(15, 1);
        lcd.write(byte(0));
      }
      break;

    case FRAME_BRIGHTNESS:  // LED Brightness
      lcd.setCursor(0, 0);
      lcd.print("LED Brightness");
      lcd.setCursor(0, 1);
      lcd.print("Level: ");
      lcd.print(rgbBrightness);
      lcd.print("%");
      break;

    case FRAME_SLEEP:  // Sleep mode (blank)
      lcd.clear();
      break;
  }
}

// =============================================================================
// Keypad Handling
// =============================================================================

void buttonCheck() {
  unsigned char button = buttonArray.getKey();

  if (!button) return;

  // Wake up on any button press
  lastActivityMillis = millis();
  lcd.backlight();

  // If waking from sleep, just return to frame 0 without other actions
  if (currentFrame == FRAME_SLEEP) {
    currentFrame = FRAME_TEMP;
    displayFrame(currentFrame);
    return;
  }

  switch (button) {
    case '1':  // Next frame (cycles through active frames only)
      currentFrame = (currentFrame + 1) % NUM_ACTIVE_FRAMES;
      editMode = false;
      displayFrame(currentFrame);
      if (currentFrame == FRAME_AC) {
        sendTempsToNode0();
      }
      break;

    case '2':  // Select/Toggle
      if (currentFrame == FRAME_THRESHOLDS) {
        if (!editMode) {
          editMode = true;
        } else {
          editingMaxTemp = !editingMaxTemp;
          if (editingMaxTemp) {
            editMode = false;
            if (!sendTempsToNode0()) {
              settingsDirty = true;
            }
          }
        }
        displayFrame(currentFrame);
      } else if (currentFrame == FRAME_AC) {
        customCursorLine = !customCursorLine;
        displayFrame(currentFrame);
      }
      break;

    case '3':  // Decrease / Action
    case '4':  // Increase / Action
      if (currentFrame == FRAME_THRESHOLDS && editMode) {
        float delta = (button == '4') ? 1.0 : -1.0;
        if (editingMaxTemp) {
          maxTemp += delta;
        } else {
          minTemp += delta;
        }
        displayFrame(currentFrame);
      } else if (currentFrame == FRAME_AC) {
        if (customCursorLine == 0) {
          acAllowed = !acAllowed;
          sendMessageToNode(0, "g1");
        } else if (customCursorLine == 1 && acAllowed) {
          acState = !acState;
          sendCurrentACState();
        }
        displayFrame(currentFrame);
      } else if (currentFrame == FRAME_BRIGHTNESS) {
        int step = (rgbBrightness < 10 || (rgbBrightness == 10 && button == '3')) ? 1 : 10;
        int delta = (button == '4') ? step : -step;
        rgbBrightness = constrain(rgbBrightness + delta, 0, 100);
        updateTempRGB(temperatureValue);
        displayFrame(currentFrame);
      }
      break;
  }
}

// =============================================================================
// Message Handler
// =============================================================================

void handleIncomingMessage(char* payload) {
  Serial.print(F("   <<< RX: "));
  Serial.println(payload);

  lastControllerRx = millis();
  if (!controllerOnline) {
    controllerOnline = true;
    hasConnected = true;
    updateTempRGB(temperatureValue);
    Serial.println(F("   Controller online"));
    // Resync temp thresholds if they changed while offline
    if (settingsDirty) {
      settingsDirty = false;
      Serial.println(F("   Resyncing settings to controller..."));
      sendTempsToNode0();
    }
  }

  // Handle compact packet messages (letter + digit format)
  // Keys: s=sync, t=temp, h=humidity, x=max, n=min, a=ac, l=allow, b=brightness, g=toggle perm
  if (isPacket(payload)) {
    Serial.println(F("   Packet received!"));

    // Parse settings from packet
    String maxVal = getPacketValue(payload, 'x');
    String minVal = getPacketValue(payload, 'n');
    String allowVal = getPacketValue(payload, 'l');
    String acVal = getPacketValue(payload, 'a');

    bool settingsUpdated = false;

    if (maxVal.length() > 0) {
      maxTemp = maxVal.toFloat();
      settingsUpdated = true;
    }
    if (minVal.length() > 0) {
      minTemp = minVal.toFloat();
      settingsUpdated = true;
    }
    if (allowVal.length() > 0) {
      acAllowed = (allowVal.toInt() == 1);
      settingsUpdated = true;
    }
    if (acVal.length() > 0) {
      acState = (acVal.toInt() == 1);
      digitalWrite(LED_PIN, acState ? HIGH : LOW);
      settingsUpdated = true;
    }

    String brightnessVal = getPacketValue(payload, 'b');
    if (brightnessVal.length() > 0) {
      rgbBrightness = constrain(brightnessVal.toInt(), 0, 100);
      updateTempRGB(temperatureValue);
      settingsUpdated = true;
    }

    if (settingsUpdated) {
      Serial.print(F("   Settings: x="));
      Serial.print(maxTemp, 0);
      Serial.print(F(" n="));
      Serial.print(minTemp, 0);
      Serial.print(F(" l="));
      Serial.print(acAllowed);
      Serial.print(F(" a="));
      Serial.println(acState);

      // Refresh display if on a relevant frame
      if (currentFrame == FRAME_THRESHOLDS || currentFrame == FRAME_AC) {
        displayFrame(currentFrame);
      }
    }

    return;  // Packet handled
  }
}

// =============================================================================
// Main Loop
// =============================================================================

void loop() {
  unsigned long currentTime = millis();

  // Update mesh and network
  mesh.update();
  network.update();

  // Send sync packet on first iteration (after mesh.update() so we can receive response)
  if (syncPending) {
    Serial.println(F("   Sending sync packet to controller..."));
    sendSyncPacket();
    syncPending = false;
  }

  // Serial command for testing (type 's' to send sync packet)
  if (Serial.available()) {
    char cmd = Serial.read();
    if (cmd == 's' || cmd == 'S') {
      Serial.println(F("   Sending sync packet..."));
      sendSyncPacket();
    }
  }

  // Send periodic heartbeat with sensor data
  unsigned long ackInterval = controllerOnline ? ACK_INTERVAL : ACK_INTERVAL_RETRY;
  if (currentTime - lastAckTime >= ackInterval) {
    sendHeartbeat();
    lastAckTime = currentTime;
  }

  // Check if controller has gone silent
  if (controllerOnline && lastControllerRx > 0 &&
      currentTime - lastControllerRx >= CONTROLLER_TIMEOUT) {
    controllerOnline = false;
    setRGBOff();
    Serial.println(F("   Controller offline (no response)"));
  }

  // Dim LCD after inactivity (but keep radio active for mesh communication)
  if (millis() - lastActivityMillis >= INACTIVITY_TIMEOUT) {
    if (currentFrame != FRAME_SLEEP) {
      lcd.noBacklight();
      currentFrame = FRAME_SLEEP;
      displayFrame(currentFrame);
    }
  }

  // Process incoming messages
  if (network.available()) {
    RF24NetworkHeader header;
    char payload[32] = {0};
    network.read(header, &payload, sizeof(payload));
    payload[sizeof(payload) - 1] = '\0';

    // Only process non-empty messages (skip mesh control packets, stale buffers)
    if (strlen(payload) > 0) {
      handleIncomingMessage(payload);
    }
  }

  // Update temperature sensor periodically
  if (currentTime - dhtPreviousMillis >= DHT_INTERVAL) {
    dhtPreviousMillis = currentTime;
    updateDHTSensor();
  }

  // Check keypad
  buttonCheck();

  delay(5);  // Small delay for stability
}
