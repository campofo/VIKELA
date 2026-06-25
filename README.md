# VIKELA

VIKELA is a community safety system that combines a mobile app, backend services, AI-assisted alert prioritization, and a standalone hardware panic device.

This first implementation uses MicroPython as the main LILYGO T-SIM7000G ESP32 panic-device firmware path.

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
  app/
    main.py
    models.py
    storage.py
  README.md
```

## Main firmware build

The MicroPython firmware supports:

- physical panic button on GPIO 32
- onboard status LED on GPIO 12
- SIM7000G modem UART on GPIO 26/27
- cellular HTTP alert delivery
- SMS fallback when HTTP delivery fails
- GPS location acquisition through the SIM7000G modem

Start with `firmware/micropython_lilygo_t_sim7000g_panic/main.py`. The Arduino/TinyGSM sketch is kept as an alternate implementation for Arduino IDE users.

## MicroPython quick start

1. Flash ESP32 MicroPython firmware to the board.
2. Edit the configuration section at the top of `firmware/micropython_lilygo_t_sim7000g_panic/main.py`.
3. Fill in the SIM APN, backend URL, device/user identity, and emergency contacts.
4. Upload `main.py` to the ESP32 with `mpremote`.
5. Reset the board and watch the serial logs while testing the panic button.

After MicroPython is flashed to the board, upload the VIKELA firmware with:

```bash
./scripts/upload_micropython.sh /dev/cu.usbserial-58EF0511901
```

## Backend quick start

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app app.main run --host 0.0.0.0 --port 8001
```

Docker on a VPS:

```bash
cd backend
docker compose up --build -d
```

The hardware alert endpoint is:

```text
http://YOUR_COMPUTER_OR_SERVER_IP:8100/api/alerts/hardware
```
