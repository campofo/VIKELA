# VIKELA native backend

A self-hosted **FastAPI + SQLite** backend that replaces the Firebase
(Cloud Functions + Firestore) backend for VIKELA.

It does two jobs:

1. **Hardware alert pipeline** — receives panic alerts from the SIM7000G
   firmware, resolves the device to its user, records the alert, and returns the
   user's emergency contacts.
2. **Data API** — REST endpoints the mobile app uses for users, device pairing,
   emergency contacts, and alert history.

## SMS is sent by the device, not here

Unlike the Firebase backend (which sent SMS via Agoo), this backend never sends
SMS. The alert response returns the resolved emergency contacts and the ESP32's
SIM7000G sends the SMS itself. That keeps the backend free of any SMS-gateway
credentials or integration.

## Requirements

- Python 3.10+

## Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # runtime deps
# For running the tests, install the dev deps instead:
# pip install -r requirements-dev.txt
cp .env.example .env    # optional; adjust VIKELA_DB_PATH etc.
```

## Run

```bash
cd backend
uvicorn app.main:app --reload
```

- Interactive API docs (OpenAPI): http://localhost:8000/docs
- Health check: http://localhost:8000/health

The SQLite database (default `vikela.db`) and its tables are created
automatically on startup. Override the location with `VIKELA_DB_PATH`.

## Seed demo data

```bash
cd backend
python -m app.seed
```

Creates a demo user, the device `VIKELA-T-SIM7000G-001`, and two emergency
contacts.

## End-to-end check

```bash
curl -X POST http://localhost:8000/api/hardware/alert \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"VIKELA-T-SIM7000G-001","latitude":5.6,"longitude":-0.1,"battery_level":87}'
```

Expected response:

```json
{
  "alert_id": 1,
  "device_paired": true,
  "user": { "id": 1, "display_name": "VIKELA User" },
  "contacts": ["+233504647863", "+233555192380"]
}
```

Then confirm history:

```bash
curl http://localhost:8000/api/devices/VIKELA-T-SIM7000G-001/alerts
```

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

## Deploy (host it)

To run this on a VPS with Docker behind your own HTTPS reverse proxy, see
[DEPLOY.md](DEPLOY.md). Quick start:

```bash
cd backend
cp .env.example .env
docker compose up -d --build
curl http://127.0.0.1:8000/health
```

## Firmware configuration

Point the firmware at this backend by setting `BACKEND_ALERT_URL` in
`firmware/micropython_lilygo_t_sim7000g_panic/main.py` to your deployment's
`/api/hardware/alert` URL, e.g.:

```python
BACKEND_ALERT_URL = "https://your-host.example.com/api/hardware/alert"
```

The firmware reads the `contacts` list from the response and sends the SMS over
the SIM, caching the contacts to `panic_contacts.json` for offline fallback.

## API reference

Firmware-facing:

| Method | Path                    | Purpose                                  |
| ------ | ----------------------- | ---------------------------------------- |
| POST   | `/api/hardware/alert`   | Ingest a panic alert; returns contacts.  |

App data API:

| Method | Path                              | Purpose                     |
| ------ | --------------------------------- | --------------------------- |
| POST   | `/api/users`                      | Create user                 |
| GET    | `/api/users`                      | List users                  |
| GET    | `/api/users/{id}`                 | Get user                    |
| PATCH  | `/api/users/{id}`                 | Update user / medical info  |
| POST   | `/api/devices`                    | Register device             |
| GET    | `/api/devices`                    | List devices                |
| GET    | `/api/devices/{device_id}`        | Get device                  |
| POST   | `/api/devices/{device_id}/pair`   | Pair device to a user       |
| GET    | `/api/users/{user_id}/contacts`   | List a user's contacts      |
| POST   | `/api/users/{user_id}/contacts`   | Add a contact               |
| PATCH  | `/api/contacts/{id}`              | Update a contact            |
| DELETE | `/api/contacts/{id}`              | Delete a contact            |
| GET    | `/api/users/{user_id}/alerts`     | User alert history          |
| GET    | `/api/devices/{device_id}/alerts` | Device alert history        |
| GET    | `/api/alerts/{id}`                | Get a single alert          |

## Not included (was Firebase, now out of scope)

- **Authentication** — the data API is unauthenticated in this phase. Add API
  keys / JWT before exposing it publicly.
- **The mobile app** — it lives outside this repo and must be reworked to call
  this REST API instead of the Firestore SDK.
- **SMS gateway** — intentionally removed; the SIM sends SMS.
