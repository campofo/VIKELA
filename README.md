# VIKELA

VIKELA is a community safety system that combines a mobile app, a self-hosted native backend, and a standalone hardware panic device.

This first implementation uses MicroPython as the main LILYGO T-SIM7000G ESP32 panic-device firmware path.

## Architecture

The firmware is intentionally lightweight: its only job is to tell the backend *who it is and where it is*. The native backend (FastAPI + SQLite, in `backend/`) records the alert and resolves the device to its user's emergency contacts, then returns those contacts so the SIM7000G sends the SMS itself.

```text
Hardware device
  --> POST /api/hardware/alert (FastAPI)  # validates, resolves device -> user
  --> SQLite alert row (history)
  --> returns emergency contacts
  --> firmware sends SMS via the SIM7000G -> emergency contacts
```

The mobile app and firmware never talk directly; both interact with the same native backend. The app owns user accounts, medical info, emergency contacts, device pairing (assigns a user to `devices/{deviceId}`), and alert history via the backend's REST API. SMS is always sent from the device's SIM — the backend never sends SMS. If the firmware cannot reach the backend, it falls back to the emergency contacts cached locally on the device.

See `backend/README.md` for setup, endpoints, and the end-to-end test. Authentication is out of scope for this phase; the data API is unauthenticated.

## Project structure

```text
firmware/
  micropython_lilygo_t_sim7000g_panic/
    main.py
    README.md
  lilygo_t_sim7000g_panic/
    lilygo_t_sim7000g_panic.ino
    config.example.h
    README.md
backend/
  app/            # FastAPI app, SQLModel models, routers
  tests/
  requirements.txt
  README.md
```

The backend runs as a self-hosted FastAPI + SQLite service in `backend/`.

## Main firmware build

The MicroPython firmware supports:

- no-hardware panic triggers: press the onboard RST button 3x, or text the device from an authorised number
- optional external button (GPIO 32) and serial `p` dev trigger
- onboard status LED on GPIO 12
- SIM7000G modem UART on GPIO 26/27
- HTTPS alert delivery to the native backend's `/api/hardware/alert` endpoint (SIM7000 native TLS)
- SMS sent from the SIM7000G to the backend-resolved emergency contacts, with a local cached-contacts fallback when the backend is unreachable
- GPS location acquisition through the SIM7000G modem
- battery level reported via `AT+CBC`

Start with `firmware/micropython_lilygo_t_sim7000g_panic/main.py`. The Arduino/TinyGSM sketch is kept as an alternate implementation for Arduino IDE users.

## MicroPython quick start

1. Flash ESP32 MicroPython firmware to the board.
2. Edit the configuration section at the top of `firmware/micropython_lilygo_t_sim7000g_panic/main.py`.
3. Fill in the SIM APN, `BACKEND_ALERT_URL` (the native backend's `/api/hardware/alert` URL), device identity, and the offline-fallback emergency contacts.
4. Upload `main.py` to the ESP32 with `mpremote`.
5. Reset the board and watch the serial logs while testing the panic button.

After MicroPython is flashed to the board, upload the VIKELA firmware with:

```bash
./scripts/upload_micropython.sh /dev/cu.usbserial-58EF0511901
```
