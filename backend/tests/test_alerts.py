import os
from pathlib import Path

os.environ["VIKELA_ALERT_STORE"] = "data/test-alerts.jsonl"
os.environ["VIKELA_CONTACT_STORE"] = "data/test-contacts.json"
os.environ["VIKELA_NOTIFICATION_STORE"] = "data/test-notifications.jsonl"

for path in ("data/test-alerts.jsonl", "data/test-contacts.json", "data/test-notifications.jsonl"):
    Path(path).unlink(missing_ok=True)

from app.main import app  # noqa: E402


def test_health():
    client = app.test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "service": "vikela-backend"}


def test_openapi_includes_mobile_alert_endpoint():
    client = app.test_client()

    response = client.get("/openapi.json")

    assert response.status_code == 200
    spec = response.get_json()
    assert spec["openapi"] == "3.0.3"
    assert "/api/alerts/mobile" in spec["paths"]
    assert "MobileAlertRequest" in spec["components"]["schemas"]


def test_accepts_hardware_alert_with_location():
    client = app.test_client()
    payload = {
        "device_id": "VIKELA-T-SIM7000G-001",
        "user_id": "user-001",
        "trigger_type": "hardware",
        "latitude": 5.6037,
        "longitude": -0.187,
        "location_source": "sim7000g_gps",
        "delivery_attempt": "cellular_http",
        "battery_level": -1,
        "timestamp": "unavailable",
        "message": "VIKELA EMERGENCY ALERT",
    }

    response = client.post("/api/alerts/hardware", json=payload)

    assert response.status_code == 202
    data = response.get_json()
    assert data["accepted"] is True
    assert data["status"] == "triage_pending"
    assert data["maps_url"] == "https://maps.google.com/?q=5.603700,-0.187000"
    assert data["anomaly_level"] == "baseline"
    assert data["location_anomaly"] is False


def test_rejects_invalid_alert():
    client = app.test_client()

    response = client.post("/api/alerts/hardware", json={"message": "missing device"})

    assert response.status_code == 400
    assert response.get_json()["accepted"] is False


def test_accepts_mobile_alert_with_mobile_defaults():
    client = app.test_client()
    payload = {
        "device_id": "VIKELA-MOBILE-APP-001",
        "user_id": "mobile-user-001",
        "trigger_type": "mobile",
        "latitude": 5.6037,
        "longitude": -0.187,
        "battery_level": 78,
        "message": "VIKELA MOBILE PANIC",
    }

    response = client.post("/api/alerts/mobile", json=payload)

    assert response.status_code == 202
    data = response.get_json()
    assert data["accepted"] is True
    assert data["anomaly_level"] == "baseline"

    alerts_response = client.get("/api/alerts")
    mobile_alert = next(
        alert for alert in alerts_response.get_json()
        if alert["device_id"] == "VIKELA-MOBILE-APP-001"
    )
    assert mobile_alert["trigger_type"] == "mobile"
    assert mobile_alert["location_source"] == "mobile_gps"
    assert mobile_alert["delivery_attempt"] == "mobile_http"


def test_mobile_endpoint_rejects_hardware_trigger_type():
    client = app.test_client()
    payload = {
        "device_id": "VIKELA-MOBILE-APP-002",
        "trigger_type": "hardware",
        "message": "wrong endpoint",
    }

    response = client.post("/api/alerts/mobile", json=payload)

    assert response.status_code == 400
    assert response.get_json()["accepted"] is False


def test_lists_recent_alerts():
    client = app.test_client()

    response = client.get("/api/alerts")

    assert response.status_code == 200
    assert len(response.get_json()) >= 1


def test_flags_location_anomaly_for_large_jump():
    client = app.test_client()
    client.post(
        "/api/panic-contacts",
        json={"phone_number": "+233555192399", "name": "Responder"},
    )
    baseline = {
        "device_id": "VIKELA-ANOMALY-TEST",
        "user_id": "user-001",
        "trigger_type": "hardware",
        "latitude": 5.6037,
        "longitude": -0.187,
        "location_source": "sim7000g_gps",
        "delivery_attempt": "cellular_http",
        "battery_level": -1,
        "timestamp": "unavailable",
        "message": "VIKELA EMERGENCY ALERT",
    }
    jump = {**baseline, "latitude": 9.419444, "longitude": -0.821516}

    baseline_response = client.post("/api/alerts/hardware", json=baseline)
    jump_response = client.post("/api/alerts/hardware", json=jump)

    assert baseline_response.status_code == 202
    assert jump_response.status_code == 202
    data = jump_response.get_json()
    assert data["location_anomaly"] is True
    assert data["anomaly_level"] in ("high", "critical")
    assert data["distance_from_previous_km"] > 400
    assert "large location jump from previous alert" in data["anomaly_reasons"]
    assert data["notifications_created"] >= 1

    notifications_response = client.get("/api/notifications")
    assert notifications_response.status_code == 200
    notifications = notifications_response.get_json()
    assert notifications[0]["phone_number"] == "+233555192399"
    assert notifications[0]["status"] == "queued_no_provider"
    assert "Anomaly:" in notifications[0]["message"]
    assert "Reason:" in notifications[0]["message"]


def test_adds_and_lists_panic_contact():
    client = app.test_client()
    payload = {
        "phone_number": "+233000000000",
        "name": "Primary responder",
        "relationship": "family",
    }

    create_response = client.post("/api/panic-contacts", json=payload)

    assert create_response.status_code == 201
    created = create_response.get_json()
    assert created["created"] is True
    assert created["contact"]["phone_number"] == "+233000000000"
    assert created["contact"]["enabled"] is True
    assert created["contact"]["contact_id"]

    list_response = client.get("/api/panic-contacts")

    assert list_response.status_code == 200
    contacts = list_response.get_json()
    assert any(contact["phone_number"] == "+233000000000" for contact in contacts)


def test_lists_enabled_panic_numbers_only():
    client = app.test_client()
    client.post(
        "/api/panic-contacts",
        json={"phone_number": "+233555192383", "enabled": True},
    )
    client.post(
        "/api/panic-contacts",
        json={"phone_number": "+233555192381", "enabled": False},
    )

    response = client.get("/api/panic-contacts/numbers")

    assert response.status_code == 200
    numbers = response.get_json()["phone_numbers"]
    assert "+233555192383" in numbers
    assert "+233555192381" not in numbers


def test_rejects_invalid_panic_contact_number():
    client = app.test_client()

    response = client.post("/api/panic-contacts", json={"phone_number": "0500000000"})

    assert response.status_code == 400
    assert response.get_json()["created"] is False


def test_deletes_panic_contact():
    client = app.test_client()
    create_response = client.post(
        "/api/panic-contacts",
        json={"phone_number": "+233555192382"},
    )
    contact_id = create_response.get_json()["contact"]["contact_id"]

    delete_response = client.delete(f"/api/panic-contacts/{contact_id}")

    assert delete_response.status_code == 200
    assert delete_response.get_json()["deleted"] is True
