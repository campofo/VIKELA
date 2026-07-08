# VIKELA HTTP relay

A lightweight relay for the VIKELA panic device.

```
Hardware --HTTP--> VPS relay (:8081) --HTTPS--> Firebase Cloud Function
```

The LILYGO T-SIM7000G modem cannot reliably establish HTTPS/TLS, so the hardware
sends **plain HTTP** to this relay and the relay forwards the request to the
Firebase `hardwareAlert` Cloud Function over HTTPS. It is **stateless**: it
forwards the JSON body verbatim and returns Firebase's status and body to the
device. Heartbeats (`{"type":"heartbeat"}`) are acknowledged locally.

> This is the relay-to-Firebase architecture. It does **not** use Traefik or
> terminate TLS on the device path — the device talks plain HTTP on port 8081.

## Requirements

- A VPS with **Docker** + the **Docker Compose** plugin.
- The Firebase Cloud Function URL (defaults to the VIKELA `hardwareAlert`).
- Inbound **TCP 8081** open (see Firewall).

## Deploy

```bash
git clone <your repo> && cd VIKELA/relay
cp .env.example .env          # set FIREBASE_FUNCTION_URL if different
docker compose up -d --build
docker compose ps
docker compose logs -f
```

Verify on the VPS:

```bash
curl http://127.0.0.1:8081/health      # -> {"status":"ok"}
```

## Firewall

Open TCP **8081** to the internet.

- **Hostinger hPanel:** add a rule — TCP, port 8081, source `0.0.0.0/0`.
- **UFW (if active):** `ufw allow 8081/tcp`

## External test (from a laptop)

Heartbeat (acked locally, not forwarded):

```bash
curl -X POST http://YOUR_SERVER_IP:8081/hardwareAlert \
  -H "Content-Type: application/json" \
  -d '{"device_id":"VIKELA-T-SIM7000G-001","type":"heartbeat","battery_level":85}'
# -> {"accepted":true,"type":"heartbeat"}
```

Alert (forwarded to Firebase; you get Firebase's response back):

```bash
curl -X POST http://YOUR_SERVER_IP:8081/hardwareAlert \
  -H "Content-Type: application/json" \
  -d '{"device_id":"VIKELA-T-SIM7000G-001","latitude":5.6,"longitude":-0.1,"battery_level":85}'
```

`docker compose logs -f` shows both the incoming request and the Firebase
response.

## Firmware change

In `firmware/micropython_lilygo_t_sim7000g_panic/main.py`:

```python
BACKEND_ALERT_URL = "http://YOUR_SERVER_IP:8081/hardwareAlert"
```

Reflash the device. No other firmware change is required — over an `http://`
URL the modem skips all TLS setup.

## Configuration

| Env var                 | Default                                | Purpose                                  |
| ----------------------- | -------------------------------------- | ---------------------------------------- |
| `FIREBASE_FUNCTION_URL` | VIKELA `hardwareAlert` URL             | HTTPS target the alert is forwarded to.  |
| `RELAY_BIND`            | `0.0.0.0:8081`                         | Host bind for the published HTTP port.   |
| `RELAY_FORWARD_TIMEOUT` | `30`                                   | Seconds to wait for Firebase (else 502). |

## Tests

```bash
cd relay
pip install -r requirements-dev.txt
pytest
```

## Troubleshooting

- **Laptop test works but the device can't connect:** the mobile carrier is
  likely blocking port 8081. Switch to port 80 by setting `RELAY_BIND=0.0.0.0:80`
  in `.env` and re-running `docker compose up -d` (open port 80 in the firewall).
- **Relay returns 502:** it could not reach Firebase — check the VPS has
  outbound HTTPS and that `FIREBASE_FUNCTION_URL` is correct
  (`docker compose logs -f relay`).
