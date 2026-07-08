"""Tests for the VIKELA HTTP relay."""

import httpx
import respx

from relay import FIREBASE_FUNCTION_URL


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


@respx.mock
def test_heartbeat_acked_locally_without_forwarding(client):
    route = respx.post(FIREBASE_FUNCTION_URL)
    resp = client.post(
        "/hardwareAlert",
        json={"device_id": "VIKELA-T-SIM7000G-001", "type": "heartbeat",
              "battery_level": 85},
    )
    assert resp.status_code == 200
    assert resp.json() == {"accepted": True, "type": "heartbeat"}
    # A heartbeat must not be forwarded to Firebase.
    assert not route.called


@respx.mock
def test_alert_forwarded_to_firebase_and_response_returned(client):
    route = respx.post(FIREBASE_FUNCTION_URL).mock(
        return_value=httpx.Response(200, json={"status": "queued", "alert": 7})
    )
    payload = {"device_id": "VIKELA-T-SIM7000G-001", "latitude": 5.6,
               "longitude": -0.1, "battery_level": 80}
    resp = client.post("/hardwareAlert", json=payload)

    assert route.called
    # The body reached Firebase unchanged.
    import json
    assert json.loads(route.calls.last.request.content) == payload
    # Firebase's status and body are returned to the device verbatim.
    assert resp.status_code == 200
    assert resp.json() == {"status": "queued", "alert": 7}


@respx.mock
def test_firebase_error_status_is_passed_through(client):
    respx.post(FIREBASE_FUNCTION_URL).mock(
        return_value=httpx.Response(403, text="forbidden")
    )
    resp = client.post("/hardwareAlert", json={"device_id": "x"})
    assert resp.status_code == 403


@respx.mock
def test_firebase_unreachable_returns_502(client):
    respx.post(FIREBASE_FUNCTION_URL).mock(side_effect=httpx.ConnectError("boom"))
    resp = client.post("/hardwareAlert", json={"device_id": "x"})
    assert resp.status_code == 502
    assert resp.json()["accepted"] is False
