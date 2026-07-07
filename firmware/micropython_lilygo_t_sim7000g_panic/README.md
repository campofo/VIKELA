# MicroPython LILYGO T-SIM7000G Panic Firmware

Main firmware for the VIKELA standalone panic device on the LILYGO T-SIM7000G ESP32 LTE/GPRS/GPS board.

This project uses MicroPython as the primary implementation path. It controls the SIM7000G with AT commands over UART instead of using the Arduino/TinyGSM stack.

## Hardware

- Board: LILYGO T-SIM7000G ESP32 LTE/GPRS/GPS
- Status LED: onboard LED on GPIO 12
- SIM7000G UART: ESP32 GPIO 26/27
- Modem power control: GPIO 4 power key, GPIO 23 modem power, GPIO 5 reset

No external button is required. An optional external panic button can still be
wired to GPIO 32 (to GND, internal pull-up) and added to `PANIC_BUTTON_PINS`.

## Triggering a panic

A panic can be raised without attaching any hardware, using either:

- **RST triple-press** — press the onboard RST button `PANIC_RESET_COUNT` (default 3)
  times in a row. The firmware counts qualifying resets (via `machine.reset_cause()`
  plus a small flash counter) and fires once the count is reached. Each press
  reboots the board, so the alert is sent after the final press.
- **Remote SMS** — text the device's SIM from a number in `PANIC_CALLER_NUMBERS`.
  The firmware polls for new messages and fires when an authorised sender is seen
  (optionally requiring `PANIC_SMS_KEYWORD` in the body). An incoming *call* from a
  whitelisted number is also detected, but the SIM7000G usually lacks voice, so
  SMS is the reliable remote path.

Held button on GPIO 32 (if wired) and the dev serial `p` key also work.

## Files

```text
main.py
README.md
```

Edit the configuration section at the top of `main.py` and update:

- SIM APN credentials
- `BACKEND_ALERT_URL` (Firebase `hardwareAlert` endpoint)
- device ID
- user ID/display name
- emergency contact phone numbers used as the offline SMS fallback
- `SMSC_NUMBER` (only needed if SMS sends fail with `CMS ERROR: 500`)
- RST trigger: `PANIC_RESET_COUNT`, `RESET_MULTIPRESS_WINDOW_MS`, `COUNT_RESET_CAUSE`
- remote trigger: `PANIC_CALLER_NUMBERS`, `PANIC_SMS_KEYWORD`, `REMOTE_TRIGGER_POLL_MS`
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

> **Verify `COUNT_RESET_CAUSE` once per board.** Boards differ in whether the RST
> button reports as `HARD_RESET` or `PWRON_RESET`. Print `machine.reset_cause()`
> at boot, press RST, and confirm it matches. Default is `"hard"`; set it to
> `"pwron"` if your board reports the RST button as a power-on reset (note that
> the power switch then also counts toward the gesture).

1. A trigger fires (RST x3, an authorised SMS, a held GPIO-32 button, or serial `p`).
2. Firmware powers/wakes the SIM7000G modem.
3. Firmware waits for network registration.
4. Firmware attempts to acquire GPS location with `AT+CGNSINF`.
5. Firmware reads the battery level with `AT+CBC`.
6. Firmware activates the data context (`AT+CNACT`) and POSTs a JSON alert to the Firebase `hardwareAlert` function over TLS using the SIM7000 `AT+SH*` HTTP commands.
7. Firebase resolves the device to its owner, creates the alert document, and (via `onAlertCreated`) sends SMS to the user's emergency contacts through Agoo SMS.
8. If Firebase is unreachable, the firmware falls back to sending SMS directly through the SIM7000G (`AT+CMGS`) to the locally cached `panic_contacts.json` list, or the built-in `EMERGENCY_CONTACTS`.
9. LED feedback shows waiting, sending, success, or failure.

## Alert payload

The firmware sends the minimal documented `hardwareAlert` contract as JSON:

```json
{
  "device_id": "VIKELA-T-SIM7000G-001",
  "latitude": 5.6037,
  "longitude": -0.187,
  "battery_level": 78
}
```

Firebase resolves the user from `device_id` and builds the emergency message itself. When GPS times out, `latitude` and `longitude` are sent as `null`, and the SMS fallback says location is unavailable. `battery_level` is the charge percentage from `AT+CBC`, or `-1` if it could not be read.

## Offline SMS fallback

Emergency contacts are owned by Firestore (managed by the mobile app). The firmware keeps local numbers only for the offline SMS fallback used when Firebase cannot be reached: a locally-provisioned `panic_contacts.json` cache if present, otherwise the built-in `EMERGENCY_CONTACTS` list.

## Notes

- HTTPS to Firebase uses the SIM7000-native `AT+CNACT` + `AT+SH*` (SHSSL/SHCONN/SHREQ) command set, which does TLS reliably on this modem — unlike the legacy `SAPBR` + `AT+HTTPSSL` bearer path.
- The exact `AT+CNACT` argument form can vary by modem firmware revision; the firmware tries the newer `=0,1,"apn"` form then the legacy `=1,"apn"` form.
- If SMS fallback fails with `CMS ERROR: 500`, set `SMSC_NUMBER` to the SIM network's service-centre number (a data-only SIM may not support SMS at all).
- Keep Bluetooth pairing out of this build; the priority is standalone cellular reliability.
