# Deploying the VIKELA backend (VPS + Docker)

This runs the backend as a single Docker container on a VPS. It serves plain
**HTTP** on a local port; **you** put HTTPS in front of it with your own reverse
proxy / load balancer / CDN. SQLite data lives on a persistent Docker volume.

## Why HTTPS is still required

The SIM7000G firmware POSTs to an `https://` URL. It performs a real TLS
handshake and sends **SNI**, but uses `authmode 0`, so it does **not** verify the
server certificate. That means:

- TLS must be terminated **somewhere in front of** this app (the app itself only
  speaks HTTP on the private port).
- The certificate does not need to be trusted by the device, but a valid
  Let's Encrypt / CDN cert is still recommended for the mobile app and browsers.

## Prerequisites

- A VPS with **Docker** and the **Docker Compose** plugin installed.
- A **domain** (e.g. `api.vikela.example`) with a **DNS A record** pointing at
  wherever TLS is terminated (your VPS, or your CDN/load balancer).
- An HTTPS front-end. Any of:
  - an existing **nginx**/**Traefik** on the box,
  - a **cloud load balancer** (terminates TLS, forwards to the VPS),
  - **Cloudflare** (proxied DNS with an origin cert / Flexible-to-Full TLS).

## 1. Deploy the app

```bash
git clone <your repo> && cd VIKELA/backend
cp .env.example .env          # adjust VIKELA_BIND / VIKELA_CORS_ORIGINS if needed
docker compose up -d --build
```

Verify on the VPS itself:

```bash
curl http://127.0.0.1:8000/health      # -> {"status":"ok"}
```

By default the container binds to `127.0.0.1:8000` (private to the host), so only
a reverse proxy on the same machine can reach it. To expose it directly (e.g. you
front it from another host or a cloud LB), set `VIKELA_BIND=0.0.0.0:8000` in
`.env` and re-run `docker compose up -d`.

## 2. Put HTTPS in front

Proxy `https://<domain>` to `http://127.0.0.1:8000`.

### Option A — nginx (on the same VPS)

```nginx
server {
    listen 443 ssl;
    server_name api.vikela.example;

    ssl_certificate     /etc/letsencrypt/live/api.vikela.example/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.vikela.example/privkey.pem;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

Obtain the cert with `certbot --nginx -d api.vikela.example`. The app is started
with `--proxy-headers`, so it honours the `X-Forwarded-*` headers above.

### Option B — Cloudflare

Point the domain's proxied (orange-cloud) DNS at the VPS, set SSL mode to
**Full**, and either open 443 with a self-signed/Let's Encrypt origin cert or use
a Cloudflare Origin Certificate. Cloudflare terminates TLS for clients and
forwards to your origin.

### Option C — cloud load balancer

Terminate TLS at the LB, forward to the VPS on port 8000 (set
`VIKELA_BIND=0.0.0.0:8000`), and restrict the security group to the LB.

Confirm end to end:

```bash
curl https://api.vikela.example/health
```

## 3. Seed initial data (optional)

```bash
docker compose exec app python -m app.seed
```

Creates a demo user, device `VIKELA-T-SIM7000G-001`, and two contacts. In
production, create real users/devices/contacts via the data API (`/docs`).

## 4. Point the firmware at the backend

In `firmware/micropython_lilygo_t_sim7000g_panic/main.py`:

```python
BACKEND_ALERT_URL = "https://api.vikela.example/api/hardware/alert"
```

Re-upload `main.py` to the device. Fire a test panic and confirm the alert was
recorded:

```bash
curl https://api.vikela.example/api/devices/VIKELA-T-SIM7000G-001/alerts
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

WAL mode is enabled; back up while running is generally safe, but for a
consistent copy prefer the SQL dump above.

## Notes

- **No auth**: the API is open. Restrict network access (firewall/proxy allowlist)
  or add an API key before exposing sensitive data publicly.
- **CORS**: defaults to `*`. Set `VIKELA_CORS_ORIGINS` to your app/dashboard
  origins in production.
- **Scaling**: a single uvicorn process is intentional (panic volume is tiny and
  it avoids SQLite multi-writer contention). If you ever need more, move to
  Postgres first.
