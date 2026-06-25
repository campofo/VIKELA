import os
from html import escape
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request

from app.anomaly import analyze_location_anomaly
from app.notifier import notify_panic_contacts
from app.models import AlertRecord, EmergencyContact, HardwareAlertIn, ValidationError
from app.openapi import OPENAPI_SPEC
from app.storage import AlertStore, ContactStore, NotificationStore


DATA_FILE = Path(
    os.getenv("VIKELA_ALERT_STORE")
    or "data/alerts.jsonl"
)
CONTACT_FILE = Path(
    os.getenv("VIKELA_CONTACT_STORE")
    or "data/contacts.json"
)
NOTIFICATION_FILE = Path(
    os.getenv("VIKELA_NOTIFICATION_STORE")
    or "data/notifications.jsonl"
)

app = Flask(__name__)
store = AlertStore(DATA_FILE)
contact_store = ContactStore(CONTACT_FILE)
notification_store = NotificationStore(NOTIFICATION_FILE)


@app.get("/")
def dashboard():
    alerts = store.list_recent(limit=20)
    rows = []
    for alert in alerts:
        location = "Unavailable"
        if alert.maps_url:
            location = (
                f'<a href="{escape(alert.maps_url)}" target="_blank" '
                'rel="noreferrer">Map</a>'
            )
        rows.append(
            "<tr>"
            f"<td>{escape(alert.received_at)}</td>"
            f"<td>{escape(alert.device_id)}</td>"
            f"<td>{escape(alert.user_id or '')}</td>"
            f"<td>{escape(alert.message)}</td>"
            f"<td>{location}</td>"
            f"<td>{escape(alert.anomaly_level)} ({alert.anomaly_score})</td>"
            f"<td>{escape(alert.status)}</td>"
            "</tr>"
        )

    body = "\n".join(rows) or '<tr><td colspan="7">No alerts received yet.</td></tr>'
    return render_template_string(
        """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>VIKELA Alerts</title>
    <style>
      body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; }
      table { border-collapse: collapse; width: 100%; }
      th, td { border-bottom: 1px solid #ddd; padding: 10px; text-align: left; }
      th { background: #f6f6f6; }
      code { background: #f4f4f4; padding: 2px 4px; border-radius: 4px; }
    </style>
  </head>
  <body>
    <h1>VIKELA Alerts</h1>
    <p>Hardware endpoint: <code>/api/alerts/hardware</code></p>
    <table>
      <thead>
        <tr>
          <th>Received</th>
          <th>Device</th>
          <th>User</th>
          <th>Message</th>
          <th>Location</th>
          <th>Anomaly</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>{{ body|safe }}</tbody>
    </table>
  </body>
</html>""",
        body=body,
    )


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "vikela-backend"})


@app.get("/openapi.json")
def openapi_json():
    return jsonify(OPENAPI_SPEC)


@app.post("/api/alerts/hardware")
def receive_hardware_alert():
    return receive_alert("hardware")


@app.post("/api/alerts/mobile")
def receive_mobile_alert():
    return receive_alert("mobile")


def receive_alert(expected_trigger_type):
    try:
        alert = HardwareAlertIn.from_dict(
            request.get_json(silent=True),
            expected_trigger_type=expected_trigger_type,
        )
    except ValidationError as exc:
        return jsonify({"accepted": False, "error": str(exc)}), 400

    record = AlertRecord.from_hardware_alert(alert)
    anomaly = analyze_location_anomaly(record, store.list_recent(limit=200))
    record.location_anomaly = bool(anomaly["location_anomaly"])
    record.anomaly_level = str(anomaly["anomaly_level"])
    record.anomaly_score = int(anomaly["anomaly_score"])
    record.anomaly_reasons = list(anomaly["anomaly_reasons"])
    record.distance_from_previous_km = anomaly["distance_from_previous_km"]
    record.speed_from_previous_kmh = anomaly["speed_from_previous_kmh"]
    store.append(record)
    notifications = notify_panic_contacts(
        record,
        contact_store.list_all(),
        notification_store,
    )
    return (
        jsonify(
            {
                "accepted": True,
                "alert_id": record.alert_id,
                "status": record.status,
                "received_at": record.received_at,
                "maps_url": record.maps_url,
                "location_anomaly": record.location_anomaly,
                "anomaly_level": record.anomaly_level,
                "anomaly_score": record.anomaly_score,
                "anomaly_reasons": record.anomaly_reasons,
                "distance_from_previous_km": record.distance_from_previous_km,
                "speed_from_previous_kmh": record.speed_from_previous_kmh,
                "notifications_created": len(notifications),
            }
        ),
        202,
    )


@app.get("/api/alerts")
def list_alerts():
    try:
        limit = int(request.args.get("limit", 50))
    except ValueError:
        limit = 50
    limit = min(max(limit, 1), 200)
    return jsonify([alert.to_dict() for alert in store.list_recent(limit=limit)])


@app.get("/api/notifications")
def list_notifications():
    try:
        limit = int(request.args.get("limit", 50))
    except ValueError:
        limit = 50
    limit = min(max(limit, 1), 200)
    return jsonify(
        [notification.to_dict() for notification in notification_store.list_recent(limit=limit)]
    )


@app.get("/api/panic-contacts")
def list_panic_contacts():
    return jsonify([contact.to_dict() for contact in contact_store.list_all()])


@app.post("/api/panic-contacts")
def add_panic_contact():
    try:
        contact = EmergencyContact.create(request.get_json(silent=True))
        saved = contact_store.add(contact)
    except ValidationError as exc:
        return jsonify({"created": False, "error": str(exc)}), 400

    return jsonify({"created": True, "contact": saved.to_dict()}), 201


@app.get("/api/panic-contacts/numbers")
def list_panic_contact_numbers():
    phone_numbers = [
        contact.phone_number
        for contact in contact_store.list_all()
        if contact.enabled
    ]
    return jsonify({"phone_numbers": phone_numbers})


@app.delete("/api/panic-contacts/<contact_id>")
def delete_panic_contact(contact_id):
    if contact_store.delete(contact_id):
        return jsonify({"deleted": True})
    return jsonify({"deleted": False, "error": "contact not found"}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8001")), debug=True)
