# MicroPython LILYGO T-SIM7000G Panic Firmware

Main firmware for the VIKELA standalone panic device on the LILYGO T-SIM7000G ESP32 LTE/GPRS/GPS board.

This project uses MicroPython as the primary implementation path. It controls the SIM7000G with AT commands over UART instead of using the Arduino/TinyGSM stack.

## Hardware

- Board: LILYGO T-SIM7000G ESP32 LTE/GPRS/GPS
- Panic button: GPIO 32 wired to GND, using internal pull-up
- Status LED: onboard LED on GPIO 12
- SIM7000G UART: ESP32 GPIO 26/27
- Modem power control: GPIO 4 power key, GPIO 23 modem power, GPIO 5 reset

Avoid using the board's SD-card SPI pins for external button or LED wiring.

## Files

```text
main.py
README.md
```

Edit the configuration section at the top of `main.py` and update:

- SIM APN credentials
- backend HTTP alert URL
- device ID
- user ID/display name
- emergency contact phone numbers used as local fallback
- backend contact-number fetch settings
- boot SMS setting and startup message
- dev serial trigger setting, used when no physical button is attached
- reset/power-on panic behavior and GPS cache timing

## Install MicroPython on the ESP32

Install `esptool` if needed:

```bash
python3 -m pip install esptool
```

Download the ESP32 MicroPython firmware from the official MicroPython site, then flash it. Replace the `.bin` filename and serial port as needed:

```bash
python3 -m esptool --chip esp32 --port /dev/cu.usbserial-58EF0511901 erase_flash
python3 -m esptool --chip esp32 --port /dev/cu.usbserial-58EF0511901 --baud 460800 write_flash -z 0x1000 ESP32_GENERIC.bin
```

## Upload VIKELA files

Install `mpremote` if needed:

```bash
python3 -m pip install mpremote
```

Upload the firmware files:

```bash
cd firmware/micropython_lilygo_t_sim7000g_panic
../../scripts/upload_micropython.sh /dev/cu.usbserial-58EF0511901
```

## Alert flow

On startup, the firmware wakes the modem, waits for network registration, attempts GPS for `BOOT_GPS_TIMEOUT_MS`, and sends a boot SMS notification with coordinates when `SEND_BOOT_SMS_ON_START` is enabled.

If `SEND_PANIC_ON_BOOT` is enabled, pressing reset or switching the board on sends a panic alert immediately. The alert uses `last_gps.json` when a saved location exists, so reset-triggered alerts do not need to wait for a fresh GPS fix.

While the device stays powered on, it periodically refreshes `last_gps.json` using `GPS_REFRESH_INTERVAL_MS`.

For development without a physical button, leave `DEV_SERIAL_TRIGGER_ENABLED = True` and type `p` in the serial console to trigger the panic flow.

1. User holds the panic button.
2. Firmware powers/wakes the SIM7000G modem.
3. Firmware waits for network registration.
4. Firmware attempts to acquire GPS location with `AT+CGNSINF`.
5. Firmware posts a JSON alert to the backend with SIM7000 HTTP AT commands.
6. If HTTP delivery fails, firmware fetches enabled panic numbers from `/api/panic-contacts/numbers`.
7. If backend contact fetch succeeds, firmware updates `panic_contacts.json` on the ESP32.
8. If backend contact fetch fails or returns no numbers, firmware uses the saved `panic_contacts.json` list.
9. If no saved contacts exist, firmware uses the local `EMERGENCY_CONTACTS` fallback list.
10. Firmware sends SMS messages to the selected panic contacts.
11. LED feedback shows waiting, sending, success, or failure.

## Backend payload

The HTTP POST body is JSON:

```json
{
  "device_id": "VIKELA-T-SIM7000G-001",
  "user_id": "user-001",
  "trigger_type": "hardware",
  "latitude": 5.6037,
  "longitude": -0.187,
  "location_source": "sim7000g_gps",
  "delivery_attempt": "cellular_http",
  "battery_level": -1,
  "timestamp": "unavailable",
  "message": "VIKELA EMERGENCY ALERT"
}
```

When GPS times out, latitude and longitude are sent as `null`, and SMS fallback says location is unavailable.

## Backend Panic Contacts

When `FETCH_CONTACTS_FROM_BACKEND = True`, the firmware derives the contact-number endpoint from `BACKEND_ALERT_URL`.

For example:

```python
BACKEND_ALERT_URL = "http://YOUR_VPS_IP:8100/api/alerts/hardware"
```

The firmware will fetch:

```text
http://YOUR_VPS_IP:8100/api/panic-contacts/numbers
```

Set `BACKEND_CONTACT_NUMBERS_URL` only if the contacts endpoint is hosted somewhere different.

Fetched contacts are cached on the ESP32 in `panic_contacts.json`, so the device can keep sending SMS fallback to the last known backend contacts if the backend is temporarily unreachable.

## Notes

- This build supports plain `http://` backend URLs. HTTPS support on SIM7000G firmware varies and should be tested separately.
- Some SIM7000G firmware revisions or carriers may require a different PDP/HTTP command sequence. The implementation uses common `SAPBR` plus `HTTPACTION` AT commands as a starting point.
- Keep Bluetooth pairing out of this build; the priority is standalone cellular reliability.
