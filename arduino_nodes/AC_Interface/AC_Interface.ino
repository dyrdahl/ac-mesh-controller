// Node 1: AC Interface (Relay Controller)
// Controls AC relay based on commands from mesh controller (Node 0)
// Author: Shane Dyrdahl
//
// Compact Packet Protocol:
//   Inbound keys:  a=AC state (1=on, 0=off), k=heartbeat, r=reset
//   Outbound keys: a=AC state report, k=heartbeat, q=query state from controller

#include <SPI.h>
#include <RF24.h>
#include <RF24Network.h>
#include <RF24Mesh.h>

// Pin definitions
#define CE_PIN 9
#define CSN_PIN 10
#define LED_PIN 2       // Connection status LED
#define RELAY_PIN 3     // AC relay control
#define DEBUG_LED 4     // AC state indicator

// Mesh network
RF24 radio(CE_PIN, CSN_PIN);
RF24Network network(radio);
RF24Mesh mesh(radio, network);

const int NODE_ID = 1;

// Timing
unsigned long lastAckTime = 0;
const unsigned long ACK_INTERVAL = 30000;         // Normal: 30 seconds
const unsigned long ACK_INTERVAL_RETRY = 10000;   // Disconnected: 10 seconds
bool connected = false;
bool syncPending = true;  // Request AC state on first loop iteration

// Software reset function
void(* resetFunc) (void) = 0;

// =============================================================================
// Compact Packet Protocol
// =============================================================================
// Format: "key1value1,key2value2,..." (single-char keys)
// Keys: a=AC state, k=heartbeat, q=query, r=reset

bool isPacket(const char* payload) {
  if (strlen(payload) < 2) return false;
  return isalpha(payload[0]) && (isdigit(payload[1]) || payload[1] == '-');
}

/**
 * Get a value from a compact packet by single-char key.
 * Returns empty string if key not found.
 */
String getPacketValue(const char* payload, char key) {
  String msg = payload;
  int i = 0;

  while (i < (int)msg.length()) {
    if (msg[i] == key) {
      int valueStart = i + 1;
      int valueEnd = msg.indexOf(',', valueStart);
      if (valueEnd == -1) valueEnd = msg.length();
      return msg.substring(valueStart, valueEnd);
    }
    int nextComma = msg.indexOf(',', i);
    if (nextComma == -1) break;
    i = nextComma + 1;
  }

  return "";
}

// =============================================================================
// Mesh Communication
// =============================================================================

/**
 * Send a message to the controller (Node 0) via mesh.write().
 */
bool sendToController(const char* message) {
  if (mesh.write(message, 'M', strlen(message), 0)) {
    Serial.print(F("   >>> TX: "));
    Serial.println(message);
    return true;
  } else {
    Serial.print(F("   Failed to send: "));
    Serial.println(message);
    return false;
  }
}

/**
 * Report current AC relay state to the controller as a compact packet.
 */
void sendStatus() {
  Serial.println(F("   Reporting AC status"));
  bool relayOn = (digitalRead(RELAY_PIN) == LOW);
  sendToController(relayOn ? "a1" : "a0");
}

// =============================================================================
// Setup
// =============================================================================

void setup() {
  Serial.begin(115200);
  Serial.println(F("\n -----===== Node 1: AC Interface =====----- "));
  Serial.flush();

  pinMode(RELAY_PIN, OUTPUT);
  pinMode(LED_PIN, OUTPUT);
  pinMode(DEBUG_LED, OUTPUT);

  // Set initial states
  digitalWrite(RELAY_PIN, HIGH);   // Relay off
  digitalWrite(LED_PIN, LOW);      // LED off
  digitalWrite(DEBUG_LED, LOW);    // Debug LED off

  // Initialize radio
  if (!radio.begin()) {
    Serial.println(F("   ERROR: Radio hardware not responding!"));
    Serial.flush();
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

  // AC state request will be sent on first loop() iteration
  Serial.println(F("   Setup complete.\n"));
  Serial.flush();
}

// =============================================================================
// Main Loop
// =============================================================================

void loop() {
  mesh.update();
  network.update();

  // Request AC state on first iteration (after mesh.update() so we can receive response)
  if (syncPending) {
    Serial.println(F("   Requesting AC state from controller..."));
    if (sendToController("q1")) {
      connected = true;
      digitalWrite(LED_PIN, HIGH);
    }
    syncPending = false;
  }

  // Periodic heartbeat (faster when disconnected)
  unsigned long currentTime = millis();
  unsigned long interval = connected ? ACK_INTERVAL : ACK_INTERVAL_RETRY;
  if (currentTime - lastAckTime >= interval) {
    if (sendToController("k1")) {
      if (!connected) {
        Serial.println(F("   Reconnected to controller"));
      }
      connected = true;
      digitalWrite(LED_PIN, HIGH);
    } else {
      if (connected) {
        Serial.println(F("   Lost connection to controller"));
      }
      connected = false;
      digitalWrite(LED_PIN, LOW);
    }
    lastAckTime = currentTime;
  }

  // Process incoming messages
  if (network.available()) {
    RF24NetworkHeader header;
    char payload[32] = {0};
    network.read(header, &payload, sizeof(payload));
    payload[sizeof(payload) - 1] = '\0';

    // Skip empty messages
    if (strlen(payload) == 0) return;

    // Message received = connection alive
    connected = true;
    digitalWrite(LED_PIN, HIGH);

    Serial.print(F("   <<< RX: "));
    Serial.println(payload);
    Serial.flush();

    // All messages should be compact packets now
    if (!isPacket(payload)) {
      Serial.println(F("   Unknown message format, ignoring"));
      return;
    }

    // Handle AC state command: a1 = on, a0 = off
    String acVal = getPacketValue(payload, 'a');
    if (acVal.length() > 0) {
      if (acVal.toInt() == 1) {
        Serial.println(F("   AC ON"));
        digitalWrite(RELAY_PIN, LOW);
        digitalWrite(DEBUG_LED, HIGH);
      } else {
        Serial.println(F("   AC OFF"));
        digitalWrite(RELAY_PIN, HIGH);
        digitalWrite(DEBUG_LED, LOW);
      }
      sendStatus();
    }

    // Handle heartbeat: k1 = ping from controller
    String kVal = getPacketValue(payload, 'k');
    if (kVal.length() > 0) {
      // No action needed - connection already marked alive above
    }

    // Handle reset: r1 = restart node
    String rVal = getPacketValue(payload, 'r');
    if (rVal.length() > 0) {
      Serial.println(F("   ==> Restarting Node"));
      Serial.flush();
      resetFunc();
    }
  }
}
