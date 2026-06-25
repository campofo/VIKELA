# LILYGO T-SIM7000G Panic Firmware

Arduino IDE firmware for the VIKELA standalone hardware panic device.

## Hardware

- Board: LILYGO T-SIM7000G ESP32 LTE/GPRS/GPS
- Panic button: GPIO 32 wired to GND, using `INPUT_PULLUP`
- Status LED: GPIO 25 through a resistor
- SIM7000G UART: ESP32 GPIO 26/27, matching the board guide example
- Modem power control: GPIO 4 power key, GPIO 23 modem power, GPIO 5 reset

Avoid using the board's SD-card SPI pins for external button or LED wiring.

## Arduino IDE setup

Install these libraries from Arduino Library Manager:

- TinyGSM
- ArduinoHttpClient

Recommended Arduino IDE board target:

- ESP32 Dev Module, or the matching ESP32 board entry available in your ESP32 board package

## Configure

Copy `config.example.h` to `config.h` in this same folder and update:

- SIM APN credentials
- backend HTTP alert URL
- device ID
- user ID/display name
- emergency contact phone numbers

`config.h` is ignored by git so real numbers and credentials stay local.

## Alert flow

1. User holds the panic button.
2. Firmware powers/wakes the SIM7000G modem.
3. Firmware waits for network registration.
4. Firmware attempts to acquire GPS location.
5. Firmware posts the alert payload to the backend URL.
6. If HTTP delivery fails, firmware sends SMS messages to all configured emergency contacts.
7. LED feedback shows waiting, sending, success, or failure.

## Backend payload

The HTTP POST body is JSON:

```json
{
  "device_id": "VIKELA-T-SIM7000G-001",
  "user_id": "user-001",
  "trigger_type": "hardware",
  "latitude": 5.6037,
  "longitude": -0.1870,
  "location_source": "sim7000g_gps",
  "delivery_attempt": "cellular_http",
  "battery_level": -1,
  "timestamp": "unavailable",
  "message": "VIKELA EMERGENCY ALERT"
}
```

When GPS times out, latitude and longitude are sent as `null`, and SMS fallback says location is unavailable.
