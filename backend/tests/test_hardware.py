"""Tests for the firmware-facing hardware alert endpoint."""


def _make_user_with_contacts(client):
    user = client.post(
        "/api/users", json={"display_name": "Ada", "phone": "+233504647863"}
    ).json()
    client.post(
        "/api/devices",
        json={"device_id": "VIKELA-TEST-1", "user_id": user["id"], "label": "test"},
    )
    # Add out of priority order to prove ordering in the response.
    client.post(
        "/api/users/{}/contacts".format(user["id"]),
        json={"name": "Second", "phone": "+233555192380", "priority": 5},
    )
    client.post(
        "/api/users/{}/contacts".format(user["id"]),
        json={"name": "First", "phone": "+233504647863", "priority": 1},
    )
    return user


def test_alert_paired_device_returns_contacts_in_priority_order(client):
    _make_user_with_contacts(client)

    resp = client.post(
        "/api/hardware/alert",
        json={
            "device_id": "VIKELA-TEST-1",
            "latitude": 5.6,
            "longitude": -0.1,
            "battery_level": 87,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["device_paired"] is True
    assert body["user"]["display_name"] == "Ada"
    # Priority 1 before priority 5.
    assert body["contacts"] == ["+233504647863", "+233555192380"]
    assert isinstance(body["alert_id"], int)


def test_alert_unknown_device_returns_200_and_empty_contacts(client):
    resp = client.post(
        "/api/hardware/alert",
        json={"device_id": "NOPE", "latitude": None, "longitude": None,
              "battery_level": -1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["device_paired"] is False
    assert body["contacts"] == []
    # Still recorded so an unpaired device shows up in history.
    assert body["alert_id"] > 0


def test_alert_unpaired_device_returns_empty_contacts(client):
    client.post("/api/devices", json={"device_id": "VIKELA-UNPAIRED"})
    resp = client.post(
        "/api/hardware/alert", json={"device_id": "VIKELA-UNPAIRED"}
    )
    assert resp.status_code == 200
    assert resp.json()["contacts"] == []


def test_alert_is_recorded_in_history(client):
    user = _make_user_with_contacts(client)
    client.post(
        "/api/hardware/alert",
        json={"device_id": "VIKELA-TEST-1", "latitude": 1.0, "longitude": 2.0,
              "battery_level": 50},
    )

    dev_hist = client.get("/api/devices/VIKELA-TEST-1/alerts").json()
    assert len(dev_hist) == 1
    assert dev_hist[0]["latitude"] == 1.0
    assert dev_hist[0]["battery_level"] == 50

    user_hist = client.get("/api/users/{}/alerts".format(user["id"])).json()
    assert len(user_hist) == 1


def test_hardware_alert_alias_path(client):
    # The /hardwareAlert alias (deployment guide / legacy firmware URL) hits the
    # same handler as /api/hardware/alert.
    _make_user_with_contacts(client)
    resp = client.post(
        "/hardwareAlert",
        json={"device_id": "VIKELA-TEST-1", "battery_level": 85},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["device_paired"] is True
    assert body["contacts"] == ["+233504647863", "+233555192380"]


def test_alert_updates_device_last_seen(client):
    _make_user_with_contacts(client)
    before = client.get("/api/devices/VIKELA-TEST-1").json()
    assert before["last_seen_at"] is None

    client.post("/api/hardware/alert", json={"device_id": "VIKELA-TEST-1"})
    after = client.get("/api/devices/VIKELA-TEST-1").json()
    assert after["last_seen_at"] is not None
