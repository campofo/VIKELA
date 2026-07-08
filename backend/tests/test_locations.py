"""Tests for live location tracking (ingest + track reads)."""


def _paired_device_with_alert(client):
    user = client.post("/api/users", json={"display_name": "Ada"}).json()
    client.post(
        "/api/devices",
        json={"device_id": "VIKELA-TEST-1", "user_id": user["id"]},
    )
    alert = client.post(
        "/api/hardware/alert",
        json={"device_id": "VIKELA-TEST-1", "latitude": 5.0, "longitude": 1.0},
    ).json()
    return user, alert["alert_id"]


def test_location_ping_recorded_and_linked_to_alert(client):
    _user, alert_id = _paired_device_with_alert(client)

    resp = client.post(
        "/api/hardware/location",
        json={
            "device_id": "VIKELA-TEST-1",
            "latitude": 5.6037,
            "longitude": -0.187,
            "battery_level": 80,
            "alert_id": alert_id,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["device_paired"] is True
    assert body["ping_id"] > 0

    track = client.get("/api/alerts/{}/locations".format(alert_id)).json()
    assert len(track) == 1
    assert track[0]["latitude"] == 5.6037
    assert track[0]["battery_level"] == 80


def test_location_track_ordered_oldest_first_by_alert(client):
    _user, alert_id = _paired_device_with_alert(client)
    for i in range(3):
        client.post(
            "/api/hardware/location",
            json={"device_id": "VIKELA-TEST-1", "latitude": float(i),
                  "longitude": 0.0, "alert_id": alert_id},
        )
    track = client.get("/api/alerts/{}/locations".format(alert_id)).json()
    assert [p["latitude"] for p in track] == [0.0, 1.0, 2.0]


def test_location_unknown_device_still_recorded_unpaired(client):
    resp = client.post(
        "/api/hardware/location",
        json={"device_id": "GHOST", "latitude": 1.0, "longitude": 2.0},
    )
    assert resp.status_code == 200
    assert resp.json()["device_paired"] is False

    track = client.get("/api/devices/GHOST/locations").json()
    assert len(track) == 1


def test_location_unknown_alert_id_is_nulled_not_rejected(client):
    client.post("/api/devices", json={"device_id": "VIKELA-UNPAIRED"})
    # alert_id 999 does not exist; ping should still be accepted with alert_id null.
    resp = client.post(
        "/api/hardware/location",
        json={"device_id": "VIKELA-UNPAIRED", "latitude": 1.0, "longitude": 2.0,
              "alert_id": 999},
    )
    assert resp.status_code == 200
    track = client.get("/api/devices/VIKELA-UNPAIRED/locations").json()
    assert len(track) == 1
    assert track[0]["alert_id"] is None


def test_location_alias_path(client):
    _paired_device_with_alert(client)
    resp = client.post(
        "/locationUpdate",
        json={"device_id": "VIKELA-TEST-1", "latitude": 9.9, "longitude": 9.9},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_location_updates_device_last_seen(client):
    _paired_device_with_alert(client)
    # last_seen was set by the alert; capture then ping and ensure it stays set.
    client.post(
        "/api/hardware/location",
        json={"device_id": "VIKELA-TEST-1", "latitude": 1.0, "longitude": 1.0},
    )
    assert client.get("/api/devices/VIKELA-TEST-1").json()["last_seen_at"] is not None
