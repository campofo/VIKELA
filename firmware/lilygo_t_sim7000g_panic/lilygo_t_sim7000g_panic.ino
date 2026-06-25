#define TINY_GSM_MODEM_SIM7000
#define TINY_GSM_RX_BUFFER 1024

#include <Arduino.h>
#include <TinyGsmClient.h>
#include <ArduinoHttpClient.h>
#include <string.h>

#if __has_include("config.h")
#include "config.h"
#else
#warning "Using config.example.h. Copy it to config.h and set real deployment values before field use."
#include "config.example.h"
#endif

// LILYGO T-SIM7000G pins from the board guide.
static const int MODEM_RX = 26;
static const int MODEM_TX = 27;
static const int MODEM_PWRKEY = 4;
static const int MODEM_POWER_ON = 23;
static const int MODEM_RST = 5;

// External VIKELA panic-device pins.
static const int PANIC_BUTTON_PIN = 32;
static const int STATUS_LED_PIN = 25;

static const unsigned long BUTTON_HOLD_MS = 1200;
static const unsigned long NETWORK_TIMEOUT_MS = 60000;
static const unsigned long GPS_TIMEOUT_MS = 90000;
static const unsigned long HTTP_TIMEOUT_MS = 30000;

HardwareSerial SerialAT(1);
TinyGsm modem(SerialAT);
TinyGsmClient client(modem);

struct GpsFix {
  bool valid;
  float latitude;
  float longitude;
};

struct ParsedUrl {
  bool valid;
  String host;
  int port;
  String path;
};

enum LedPattern {
  LED_IDLE,
  LED_WAITING,
  LED_SENDING,
  LED_SUCCESS,
  LED_ERROR
};

LedPattern currentPattern = LED_IDLE;
unsigned long lastLedTick = 0;
bool ledState = false;

void setLed(bool on) {
  digitalWrite(STATUS_LED_PIN, on ? HIGH : LOW);
  ledState = on;
}

void setPattern(LedPattern pattern) {
  currentPattern = pattern;
  lastLedTick = 0;

  if (pattern == LED_IDLE) {
    setLed(false);
  } else if (pattern == LED_SUCCESS) {
    setLed(true);
  }
}

void updateLed() {
  unsigned long now = millis();
  unsigned long interval = 0;

  switch (currentPattern) {
    case LED_WAITING:
      interval = 900;
      break;
    case LED_SENDING:
      interval = 180;
      break;
    case LED_ERROR:
      interval = 120;
      break;
    case LED_IDLE:
    case LED_SUCCESS:
    default:
      return;
  }

  if (now - lastLedTick >= interval) {
    lastLedTick = now;
    setLed(!ledState);
  }
}

void blinkPattern(LedPattern pattern, unsigned long durationMs) {
  setPattern(pattern);
  unsigned long start = millis();
  while (millis() - start < durationMs) {
    updateLed();
    delay(10);
  }
}

void modemPowerOn() {
  pinMode(MODEM_POWER_ON, OUTPUT);
  pinMode(MODEM_PWRKEY, OUTPUT);
  pinMode(MODEM_RST, OUTPUT);

  digitalWrite(MODEM_POWER_ON, HIGH);
  digitalWrite(MODEM_RST, HIGH);
  delay(100);

  // SIM7000G power-key pulse used by common LILYGO examples.
  digitalWrite(MODEM_PWRKEY, HIGH);
  delay(100);
  digitalWrite(MODEM_PWRKEY, LOW);
  delay(1000);
  digitalWrite(MODEM_PWRKEY, HIGH);
  delay(3000);
}

bool ensureModemAwake() {
  SerialAT.begin(115200, SERIAL_8N1, MODEM_RX, MODEM_TX);
  delay(300);

  if (modem.testAT(1000)) {
    Serial.println("Modem already awake.");
    return true;
  }

  Serial.println("Powering modem...");
  modemPowerOn();
  SerialAT.begin(115200, SERIAL_8N1, MODEM_RX, MODEM_TX);

  unsigned long startedAt = millis();
  while (millis() - startedAt < 10000) {
    if (modem.testAT(1000)) {
      Serial.println("Modem responded.");
      return true;
    }
    delay(500);
  }

  Serial.println("Modem did not respond after power sequence.");
  return false;
}

bool waitForButtonHold() {
  if (digitalRead(PANIC_BUTTON_PIN) == HIGH) {
    return false;
  }

  unsigned long pressedAt = millis();
  while (digitalRead(PANIC_BUTTON_PIN) == LOW) {
    updateLed();
    if (millis() - pressedAt >= BUTTON_HOLD_MS) {
      while (digitalRead(PANIC_BUTTON_PIN) == LOW) {
        updateLed();
        delay(10);
      }
      return true;
    }
    delay(10);
  }

  return false;
}

ParsedUrl parseHttpUrl(const char* rawUrl) {
  ParsedUrl parsed;
  parsed.valid = false;
  parsed.port = 80;

  String url(rawUrl);
  url.trim();

  const String prefix = "http://";
  if (!url.startsWith(prefix)) {
    Serial.println("Only plain HTTP URLs are supported in this first firmware build.");
    return parsed;
  }

  url.remove(0, prefix.length());
  int slashIndex = url.indexOf('/');
  String hostPort = slashIndex >= 0 ? url.substring(0, slashIndex) : url;
  parsed.path = slashIndex >= 0 ? url.substring(slashIndex) : "/";

  int colonIndex = hostPort.indexOf(':');
  if (colonIndex >= 0) {
    parsed.host = hostPort.substring(0, colonIndex);
    parsed.port = hostPort.substring(colonIndex + 1).toInt();
  } else {
    parsed.host = hostPort;
  }

  parsed.valid = parsed.host.length() > 0 && parsed.port > 0 && parsed.path.length() > 0;
  return parsed;
}

String jsonEscape(const String& value) {
  String escaped;
  escaped.reserve(value.length() + 8);
  for (size_t i = 0; i < value.length(); i++) {
    char c = value[i];
    if (c == '"' || c == '\\') {
      escaped += '\\';
      escaped += c;
    } else if (c == '\n') {
      escaped += "\\n";
    } else if (c == '\r') {
      escaped += "\\r";
    } else {
      escaped += c;
    }
  }
  return escaped;
}

String buildMapsLink(const GpsFix& fix) {
  if (!fix.valid) {
    return "Location unavailable";
  }
  return "https://maps.google.com/?q=" + String(fix.latitude, 6) + "," + String(fix.longitude, 6);
}

String buildSmsMessage(const GpsFix& fix) {
  String message = String(SMS_MESSAGE_PREFIX) + "\n";
  message += "User: " + String(USER_DISPLAY_NAME) + "\n";
  message += "User ID: " + String(USER_ID) + "\n";
  message += "Device: " + String(DEVICE_ID) + "\n";

  if (fix.valid) {
    message += "GPS: " + String(fix.latitude, 6) + "," + String(fix.longitude, 6) + "\n";
    message += buildMapsLink(fix);
  } else {
    message += "Location unavailable";
  }

  return message;
}

String buildAlertJson(const GpsFix& fix) {
  String payload = "{";
  payload += "\"device_id\":\"" + jsonEscape(DEVICE_ID) + "\",";
  payload += "\"user_id\":\"" + jsonEscape(USER_ID) + "\",";
  payload += "\"trigger_type\":\"hardware\",";

  if (fix.valid) {
    payload += "\"latitude\":" + String(fix.latitude, 6) + ",";
    payload += "\"longitude\":" + String(fix.longitude, 6) + ",";
  } else {
    payload += "\"latitude\":null,";
    payload += "\"longitude\":null,";
  }

  payload += "\"location_source\":\"sim7000g_gps\",";
  payload += "\"delivery_attempt\":\"cellular_http\",";
  payload += "\"battery_level\":-1,";
  payload += "\"timestamp\":\"unavailable\",";
  payload += "\"message\":\"" + jsonEscape(SMS_MESSAGE_PREFIX) + "\"";
  payload += "}";
  return payload;
}

bool waitForNetwork() {
  Serial.println("Waiting for cellular network...");
  setPattern(LED_WAITING);

  bool registered = modem.waitForNetwork(NETWORK_TIMEOUT_MS);
  if (!registered) {
    Serial.println("Network registration failed.");
    return false;
  }

  Serial.println("Network registered.");
  return true;
}

GpsFix acquireGps() {
  GpsFix fix = {false, 0.0, 0.0};

  Serial.println("Starting GPS...");
  modem.enableGPS();

  unsigned long startedAt = millis();
  while (millis() - startedAt < GPS_TIMEOUT_MS) {
    updateLed();

    float lat = 0;
    float lon = 0;
    if (modem.getGPS(&lat, &lon)) {
      fix.valid = true;
      fix.latitude = lat;
      fix.longitude = lon;
      Serial.print("GPS fix: ");
      Serial.print(lat, 6);
      Serial.print(",");
      Serial.println(lon, 6);
      return fix;
    }

    Serial.println("Waiting for GPS fix...");
    delay(2000);
  }

  Serial.println("GPS timeout. Continuing without coordinates.");
  return fix;
}

bool connectGprs() {
  Serial.println("Connecting GPRS/data...");
  setPattern(LED_SENDING);

  if (modem.isGprsConnected()) {
    Serial.println("GPRS already connected.");
    return true;
  }

  bool connected = modem.gprsConnect(CELLULAR_APN, CELLULAR_USER, CELLULAR_PASS);
  if (!connected) {
    Serial.println("GPRS connection failed.");
    return false;
  }

  Serial.println("GPRS connected.");
  return true;
}

bool sendHttpAlert(const GpsFix& fix) {
  ParsedUrl url = parseHttpUrl(BACKEND_ALERT_URL);
  if (!url.valid) {
    return false;
  }

  if (!connectGprs()) {
    return false;
  }

  String payload = buildAlertJson(fix);
  Serial.println("Posting alert to backend...");
  Serial.println(payload);

  HttpClient http(client, url.host.c_str(), url.port);
  http.setHttpResponseTimeout(HTTP_TIMEOUT_MS);
  http.beginRequest();
  http.post(url.path.c_str());
  http.sendHeader("Content-Type", "application/json");
  http.sendHeader("Connection", "close");
  http.sendHeader("Content-Length", payload.length());
  http.beginBody();
  http.print(payload);
  http.endRequest();

  int statusCode = http.responseStatusCode();
  String response = http.responseBody();

  Serial.print("HTTP status: ");
  Serial.println(statusCode);
  if (response.length() > 0) {
    Serial.println(response);
  }

  http.stop();
  return statusCode >= 200 && statusCode < 300;
}

bool sendSmsFallback(const GpsFix& fix) {
  if (EMERGENCY_CONTACT_COUNT <= 0) {
    Serial.println("No emergency contacts configured.");
    return false;
  }

  String message = buildSmsMessage(fix);
  bool anySent = false;

  Serial.println("Sending SMS fallback...");
  Serial.println(message);

  for (int i = 0; i < EMERGENCY_CONTACT_COUNT; i++) {
    const char* number = EMERGENCY_CONTACTS[i];
    if (number == nullptr || strlen(number) == 0) {
      continue;
    }

    Serial.print("SMS to ");
    Serial.println(number);
    bool sent = modem.sendSMS(number, message);
    Serial.println(sent ? "SMS sent." : "SMS failed.");
    anySent = anySent || sent;
    delay(1000);
  }

  return anySent;
}

void handlePanicAlert() {
  Serial.println("Panic button confirmed.");
  blinkPattern(LED_SENDING, 800);

  if (!ensureModemAwake()) {
    blinkPattern(LED_ERROR, 4000);
    setPattern(LED_IDLE);
    return;
  }

  Serial.println("Initializing modem...");
  if (!modem.restart()) {
    Serial.println("Modem restart failed. Trying init...");
    if (!modem.init()) {
      Serial.println("Modem init failed.");
      blinkPattern(LED_ERROR, 4000);
      setPattern(LED_IDLE);
      return;
    }
  }

  Serial.print("Modem: ");
  Serial.println(modem.getModemInfo());

  bool networkReady = waitForNetwork();
  GpsFix fix = acquireGps();

  bool delivered = false;
  if (networkReady) {
    delivered = sendHttpAlert(fix);
    if (!delivered) {
      Serial.println("HTTP delivery failed. Trying SMS fallback.");
      delivered = sendSmsFallback(fix);
    }
  } else {
    Serial.println("Network unavailable. Trying SMS fallback anyway.");
    delivered = sendSmsFallback(fix);
  }

  if (delivered) {
    Serial.println("Alert delivered.");
    setPattern(LED_SUCCESS);
    delay(5000);
  } else {
    Serial.println("All alert delivery attempts failed.");
    blinkPattern(LED_ERROR, 6000);
  }

  modem.disableGPS();
  if (modem.isGprsConnected()) {
    modem.gprsDisconnect();
  }
  setPattern(LED_IDLE);
}

void setup() {
  pinMode(PANIC_BUTTON_PIN, INPUT_PULLUP);
  pinMode(STATUS_LED_PIN, OUTPUT);
  setPattern(LED_IDLE);

  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("VIKELA LILYGO T-SIM7000G Panic Firmware");
  Serial.println("Hold the panic button to send an alert.");

  SerialAT.begin(115200, SERIAL_8N1, MODEM_RX, MODEM_TX);
}

void loop() {
  updateLed();

  if (waitForButtonHold()) {
    handlePanicAlert();
  }

  delay(20);
}
