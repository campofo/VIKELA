# VIKELA

VIKELA is a community safety system that combines a mobile app, a Firebase backend, and a standalone hardware panic device.

This first implementation uses MicroPython as the main LILYGO T-SIM7000G ESP32 panic-device firmware path.

## Architecture

The firmware is intentionally lightweight: its only job is to tell Firebase *who it is and where it is*. Everything else is handled by Firebase Cloud Functions and Firestore. Because the SIM7000G modem cannot reliably establish HTTPS/TLS, the device sends **plain HTTP** to a small **VPS relay** that forwards the request to Firebase over HTTPS.

```text
Hardware device
  --HTTP--> VPS relay (:8081)           # see relay/
  --HTTPS--> hardwareAlert (Cloud Function)   # validates, resolves device -> user
  --> Firestore alert document
  --> onAlertCreated (Cloud Function)  # reads emergency contacts, builds message
  --> Agoo SMS -> emergency contacts
```

The mobile app and firmware never talk directly; both interact with the same Firebase backend. The app owns user accounts, authentication, medical info, emergency contacts, device pairing (writes the user UID into `devices/{deviceId}`), and alert history. If the firmware cannot reach the relay/Firebase, it falls back to sending SMS directly through the SIM7000G.

The relay is a stateless HTTP→HTTPS forwarder. See `relay/` and `relay/README.md`.

**Team documentation:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) is a full
system guide with diagrams (topology, end-to-end panic flow, firmware/modem
internals, relay behaviour, deployment, failure handling).

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
relay/
  relay.py            # HTTP -> HTTPS forwarder to Firebase
  Dockerfile
  docker-compose.yml
  README.md
```

The backend runs as Firebase Cloud Functions + Firestore (managed outside this repo). The `relay/` service is the plain-HTTP entry point the hardware posts to; it forwards to Firebase over HTTPS.

## Main firmware build

The MicroPython firmware supports:

- no-hardware panic triggers: press the onboard RST button 3x, or text the device from an authorised number
- optional external button (GPIO 32) and serial `p` dev trigger
- onboard status LED on GPIO 12
- SIM7000G modem UART on GPIO 26/27
- plain-HTTP alert delivery to the VPS relay (default port 8081), which forwards to the Firebase `hardwareAlert` function over HTTPS
- SMS fallback when the relay/Firebase is unreachable
- GPS location acquisition through the SIM7000G modem
- battery level reported via `AT+CBC`

Start with `firmware/micropython_lilygo_t_sim7000g_panic/main.py`. The Arduino/TinyGSM sketch is kept as an alternate implementation for Arduino IDE users.

## MicroPython quick start

1. Flash ESP32 MicroPython firmware to the board.
2. Edit the configuration section at the top of `firmware/micropython_lilygo_t_sim7000g_panic/main.py`.
3. Fill in the SIM APN, `BACKEND_ALERT_URL` (the VPS relay endpoint, e.g. `http://YOUR_SERVER_IP:8081/hardwareAlert`), device identity, and the offline-fallback emergency contacts.
4. Upload `main.py` to the ESP32 with `mpremote`.
5. Reset the board and watch the serial logs while testing the panic button.

After MicroPython is flashed to the board, upload the VIKELA firmware with:

```bash
./scripts/upload_micropython.sh /dev/cu.usbserial-58EF0511901
```
