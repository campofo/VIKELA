# Deploying the VIKELA backend (VPS + Docker, plain HTTP)

This runs the backend as a single Docker container on a VPS, serving **plain
HTTP** on port **8081**. The SIM7000G hardware POSTs directly to it over HTTP —
there is **no TLS and no reverse proxy** (the modem cannot do TLS reliably).
SQLite data lives on a persistent Docker volume.

```
Hardware --HTTP--> VPS :8081 --> native FastAPI backend (SQLite)
```

> We do **not** deploy a separate relay: this backend is the endpoint (it already
> replaced Firebase). There is nothing to forward to.

## Prerequisites

- A VPS with **Docker** and the **Docker Compose** plugin installed.
- The VPS **public IP** (or a domain's A record pointing at it).
- Inbound **TCP 8081** allowed (see Firewall below).

## 1. Deploy

```bash
git clone <your repo> && cd VIKELA/backend
cp .env.example .env          # adjust VIKELA_BIND / VIKELA_CORS_ORIGINS if needed
docker compose up -d --build
docker compose ps
docker compose logs -f
```

Verify on the VPS itself:

```bash
curl http://127.0.0.1:8081/health      # -> {"status":"ok"}
```

The app binds to `0.0.0.0:8081` by default so the hardware can reach it directly.

## 2. Firewall

Open TCP **8081** to the internet.

### Hostinger hPanel

Add a firewall rule: **TCP**, port **8081**, source **0.0.0.0/0**.

### UFW (if active)

```bash
ufw status
ufw allow 8081/tcp
```

## 3. External test (from a laptop)

```bash
curl -X POST http://YOUR_SERVER_IP:8081/api/hardware/alert \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"VIKELA-T-SIM7000G-001","latitude":5.6,"longitude":-0.1,"battery_level":85}'
```

Expected (once the device is seeded/paired — see step 4):

```json
{
  "alert_id": 1,
  "device_paired": true,
  "user": { "id": 1, "display_name": "VIKELA User" },
  "contacts": ["+233504647863", "+233555192380"]
}
```

The guide's alias path also works: `POST http://YOUR_SERVER_IP:8081/hardwareAlert`.

## 4. Seed initial data (optional)

```bash
docker compose exec app python -m app.seed
```

Creates a demo user, device `VIKELA-T-SIM7000G-001`, and two contacts. In
production, create real users/devices/contacts via the data API (`/docs`).

## 5. Point the firmware at the backend

In `firmware/micropython_lilygo_t_sim7000g_panic/main.py`:

```python
BACKEND_ALERT_URL = "http://YOUR_SERVER_IP:8081/api/hardware/alert"
```

Re-upload `main.py` to the device (reflash). Fire a test panic and confirm the
alert was recorded:

```bash
curl http://YOUR_SERVER_IP:8081/api/devices/VIKELA-T-SIM7000G-001/alerts
```

## Operations

### Logs

```bash
docker compose logs -f app
```

### Updates

```bash
git pull
docker compose up -d --build      # data persists in the vikela-data volume
```

### Backups

The database is the `vikela-data` Docker volume, mounted at `/data/vikela.db`.

```bash
# SQL dump
docker compose exec app python -c "import sqlite3,sys; \
[sys.stdout.write(l+'\n') for l in sqlite3.connect('/data/vikela.db').iterdump()]" \
  > vikela-backup-$(date +%F).sql

# or copy the raw file out of the container
docker compose cp app:/data/vikela.db ./vikela-backup-$(date +%F).db
```

WAL mode is enabled; for a consistent copy prefer the SQL dump above.

## Troubleshooting

- **Laptop test works but the device can't connect:** the mobile carrier is
  likely blocking port 8081. Switch the service to port **80** by setting
  `VIKELA_BIND=0.0.0.0:80` in `.env` and re-running `docker compose up -d`
  (open port 80 in the firewall too). Still plain HTTP — no Traefik/TLS.
- **Connection refused from the internet:** confirm the firewall rule
  (hPanel + UFW) and that `docker compose ps` shows the app healthy.

## Notes

- **Plain HTTP only** — no TLS, by design (modem limitation). Alert payloads
  contain a device ID and GPS coordinates; treat the network path as untrusted.
- **No auth**: the API is open. Restrict access or add an API key before exposing
  sensitive data. CORS defaults to `*`; set `VIKELA_CORS_ORIGINS` in production.
- **Scaling**: a single uvicorn process is intentional (panic volume is tiny and
  it avoids SQLite multi-writer contention). If you ever need more, move to
  Postgres first.
