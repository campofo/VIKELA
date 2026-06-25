# VIKELA Flask Backend

Flask backend for receiving VIKELA hardware panic alerts from the LILYGO T-SIM7000G device.

## Endpoints

- `GET /` - simple development dashboard
- `GET /health` - service health check
- `GET /openapi.json` - OpenAPI/Swagger spec for mobile and backend integration
- `POST /api/alerts/hardware` - receive hardware panic alert JSON from the device
- `POST /api/alerts/mobile` - receive mobile app panic alert JSON
- `GET /api/alerts` - list recent received alerts for development review
- `GET /api/notifications` - list backend responder notification attempts
- `POST /api/panic-contacts` - add a phone number for panic notifications
- `GET /api/panic-contacts` - list configured panic contacts
- `GET /api/panic-contacts/numbers` - list enabled phone numbers only
- `DELETE /api/panic-contacts/<contact_id>` - remove a panic contact

## Run Locally

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app app.main run --host 0.0.0.0 --port 8001
```

## Run With Docker

```bash
cd backend
docker compose up --build -d
```

The container serves the Flask app with Gunicorn on container port `8000`.
This compose file maps it to host port `8100` locally to avoid common development port conflicts:

```text
http://YOUR_VPS_IP:8100
http://YOUR_VPS_IP:8100/api/alerts/hardware
```

Alert data, panic contacts, and notification attempts are persisted in the Docker volume `vikela_alert_data`, mounted at `/app/data`.

Useful commands:

```bash
docker compose logs -f
docker compose ps
docker compose down
```

The firmware backend URL should point to an address the SIM network can reach:

```python
BACKEND_ALERT_URL = "http://YOUR_VPS_IP:8100/api/alerts/hardware"
```

If you put Nginx/Caddy in front of the container on port 80, use:

```python
BACKEND_ALERT_URL = "http://YOUR_DOMAIN/api/alerts/hardware"
```

## PythonAnywhere

Upload the `backend` folder to PythonAnywhere, install `requirements.txt`, then configure the WSGI file to import the Flask app:

```python
import sys

project_home = "/home/YOUR_USERNAME/VIKELA/backend"
if project_home not in sys.path:
    sys.path.insert(0, project_home)

from app.main import app as application
```

Then set the firmware URL to:

```python
BACKEND_ALERT_URL = "http://YOUR_USERNAME.pythonanywhere.com/api/alerts/hardware"
```

Use `http://` unless you confirm your SIM7000G firmware supports HTTPS with `AT+HTTPSSL=1`.

## Example Payload

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

## Mobile App Panic Payload

Swagger/OpenAPI for the mobile developer is available at:

```text
GET /openapi.json
```

The mobile app should send panic alerts to:

```text
POST /api/alerts/mobile
```

Example:

```json
{
  "device_id": "VIKELA-MOBILE-APP-001",
  "user_id": "mobile-user-001",
  "trigger_type": "mobile",
  "latitude": 5.6037,
  "longitude": -0.187,
  "battery_level": 78,
  "timestamp": "2026-06-25T16:00:00Z",
  "message": "VIKELA MOBILE PANIC"
}
```

If omitted, `location_source` defaults to `mobile_gps` and `delivery_attempt` defaults to `mobile_http`.

Mobile and hardware alerts share the same anomaly detection, responder notification, alert history, and panic contact endpoints.

## Location Anomaly Detection

When an alert is received, the backend compares its GPS coordinates with the most recent previous GPS alert from the same device.

The response and stored alert include:

```json
{
  "location_anomaly": true,
  "anomaly_level": "high",
  "anomaly_score": 90,
  "anomaly_reasons": [
    "large location jump from previous alert",
    "movement speed is unusually high"
  ],
  "distance_from_previous_km": 425.5,
  "speed_from_previous_kmh": 1200.0
}
```

The first known GPS alert for a device becomes the baseline. Later alerts are flagged when the device appears to move an unusually large distance or at an unusually high speed between alerts.

## Backend Responder Notifications

After each hardware alert is received, the backend builds a responder message for every enabled panic contact. The message includes:

- alert ID
- device ID
- GPS coordinates and map link
- anomaly level and score
- anomaly reasons when a location anomaly is detected

Notification attempts are stored in `data/notifications.jsonl` and can be reviewed with:

```bash
curl http://YOUR_VPS_IP:8100/api/notifications
```

If no SMS provider is configured, notifications are stored with status `queued_no_provider`.

To connect an SMS provider, set `VIKELA_SMS_WEBHOOK_URL` to an endpoint that accepts:

```json
{
  "to": "+233000000000",
  "message": "VIKELA EMERGENCY ALERT...",
  "alert_id": "alert uuid",
  "device_id": "VIKELA-T-SIM7000G-001",
  "anomaly_level": "high",
  "anomaly_score": 90
}
```

If the provider endpoint needs a bearer token, set `VIKELA_SMS_WEBHOOK_TOKEN`.

## Add Panic Contact

```bash
curl -X POST http://YOUR_VPS_IP:8100/api/panic-contacts \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+233000000000",
    "name": "Primary responder",
    "relationship": "family"
  }'
```

Phone numbers must use international format, for example `+233000000000`.

To list the enabled numbers only:

```bash
curl http://YOUR_VPS_IP:8100/api/panic-contacts/numbers
```

## Test

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

Alerts are stored locally as JSON lines in `data/alerts.jsonl`. Panic contacts are stored in `data/contacts.json`. Notification attempts are stored in `data/notifications.jsonl`.
