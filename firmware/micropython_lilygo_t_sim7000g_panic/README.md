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

- **RST multi-press (classified)** — the number of RST presses selects the
  emergency type:

  | Presses | Emergency type    | `emergency_type`    |
  |---------|-------------------|---------------------|
  | 1       | Security Threat   | `security_threat`   |
  | 2       | Medical Emergency | `medical_emergency` |
  | 3       | Accident / Crash  | `accident_crash`    |

  Each press reboots the board and increments a flash counter. After the last
  press the firmware waits `RESET_MULTIPRESS_WINDOW_MS` for another press, then
  fires with the matching type; a 3rd press fires immediately (highest category).

  **Warm-reset guard:** on this board an RST press and a real power-on both report
  `PWRON_RESET`, so a naive counter would treat every power-on as a single press
  (a false Security Threat on each boot). The modem keeps power across an RST
  (ESP32-only) reset but is off on a cold power-on, so the firmware treats
  "modem already awake at boot" as a genuine press and ignores cold power-ons.
  Governed by `RESET_WARM_GUARD_ENABLED`. This makes single-press classification
  inherently best-effort — a warm reset from a crash/watchdog/re-flash can also be
  counted.

- **Remote SMS** — text the device's SIM from a number in `PANIC_CALLER_NUMBERS`.
  The firmware polls for new messages and fires when an authorised sender is seen
  (optionally requiring `PANIC_SMS_KEYWORD` in the body). An incoming *call* from a
  whitelisted number is also detected, but the SIM7000G usually lacks voice, so
  SMS is the reliable remote path.

Remote SMS, a held GPIO-32 button (if wired), and the dev serial `p` key carry no
press count, so they use `DEFAULT_EMERGENCY_TYPE`.

> **Backend note:** the firmware sends `emergency_type` in the alert payload, but
> the Firebase `hardwareAlert` / `onAlertCreated` functions must be updated to read
> it for the classification to affect the emergency message/response.

## Files

```text
main.py
README.md
```

Edit the configuration section at the top of `main.py` and update:

- SIM APN credentials
- `BACKEND_ALERT_URL` (the VPS relay endpoint, e.g. `http://YOUR_SERVER_IP:8081/hardwareAlert`)
- device ID
- user ID/display name
- emergency contact phone numbers used as the offline SMS fallback
- `SMSC_NUMBER` (only needed if SMS sends fail with `CMS ERROR: 500`)
- RST trigger: `PANIC_RESET_COUNT`, `RESET_MULTIPRESS_WINDOW_MS`, `COUNT_RESET_CAUSE`, `RESET_WARM_GUARD_ENABLED`
- emergency classification: `EMERGENCY_TYPES`, `EMERGENCY_LABELS`, `EMERGENCY_MESSAGES`, `DEFAULT_EMERGENCY_TYPE`
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

1. A trigger fires (RST 1x/2x/3x for Security/Medical/Accident, an authorised SMS, a held GPIO-32 button, or serial `p`).
2. Firmware powers/wakes the SIM7000G modem.
3. Firmware waits for network registration.
4. Firmware attempts to acquire GPS location with `AT+CGNSINF`.
5. Firmware reads the battery level with `AT+CBC`.
6. Firmware activates the data context (`AT+CNACT`) and POSTs a JSON alert over **plain HTTP** to the VPS relay (`http://YOUR_SERVER_IP:8081/hardwareAlert`) using the SIM7000 `AT+SH*` HTTP commands. The relay forwards it to the Firebase `hardwareAlert` function over HTTPS (see `relay/`).
7. Firebase resolves the device to its owner, creates the alert document, and (via `onAlertCreated`) sends SMS to the user's emergency contacts through Agoo SMS.
8. If the relay/Firebase is unreachable, the firmware falls back to sending SMS directly through the SIM7000G (`AT+CMGS`) to the locally cached `panic_contacts.json` list, or the built-in `EMERGENCY_CONTACTS`.
9. LED feedback shows waiting, sending, success, or failure.

## Alert payload

The firmware sends the `hardwareAlert` contract as JSON:

```json
{
  "device_id": "VIKELA-T-SIM7000G-001",
  "latitude": 5.6037,
  "longitude": -0.187,
  "battery_level": 78,
  "emergency_type": "security_threat",
  "message": "SECURITY THREAT: VIKELA user triggered a security emergency and may be in danger."
}
```

Firebase resolves the user from `device_id`. `emergency_type` is one of `security_threat`, `medical_emergency`, or `accident_crash` (see the classification table above), and `message` is the matching tailored text from `EMERGENCY_MESSAGES` — the same text is used as the fallback SMS headline, so the alert wording differs per trigger type. When GPS times out, `latitude` and `longitude` are sent as `null`, and the SMS fallback says location is unavailable. `battery_level` is the charge percentage from `AT+CBC`, or `-1` if it could not be read.

## Offline SMS fallback

Emergency contacts are owned by Firestore (managed by the mobile app). The firmware keeps local numbers only for the offline SMS fallback used when Firebase cannot be reached: a locally-provisioned `panic_contacts.json` cache if present, otherwise the built-in `EMERGENCY_CONTACTS` list.

## Notes

- The device posts over **plain HTTP** to the VPS relay using the SIM7000-native `AT+CNACT` + `AT+SH*` (SHCONN/SHREQ) command set. TLS is handled by the relay (HTTPS to Firebase), not the modem, which cannot do TLS reliably. Over an `http://` URL the firmware skips all `SHSSL`/`AT+CSSLCFG` setup.
- The exact `AT+CNACT` argument form can vary by modem firmware revision; the firmware tries the newer `=0,1,"apn"` form then the legacy `=1,"apn"` form.
- If SMS fallback fails with `CMS ERROR: 500`, set `SMSC_NUMBER` to the SIM network's service-centre number (a data-only SIM may not support SMS at all).
- Keep Bluetooth pairing out of this build; the priority is standalone cellular reliability.
