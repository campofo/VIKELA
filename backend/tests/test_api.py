"""Tests for the app-facing data API: users, devices, contacts, alerts."""


def test_user_crud(client):
    created = client.post(
        "/api/users",
        json={"display_name": "Kofi", "phone": "+233111", "medical_info": "asthma"},
    )
    assert created.status_code == 201
    uid = created.json()["id"]

    got = client.get("/api/users/{}".format(uid))
    assert got.status_code == 200
    assert got.json()["display_name"] == "Kofi"

    patched = client.patch(
        "/api/users/{}".format(uid), json={"medical_info": "asthma, penicillin allergy"}
    )
    assert patched.json()["medical_info"] == "asthma, penicillin allergy"
    # Untouched field preserved.
    assert patched.json()["phone"] == "+233111"

    assert len(client.get("/api/users").json()) == 1


def test_get_missing_user_404(client):
    assert client.get("/api/users/999").status_code == 404


def test_device_registration_and_pairing(client):
    user = client.post("/api/users", json={"display_name": "Ama"}).json()

    reg = client.post(
        "/api/devices", json={"device_id": "DEV-1", "label": "belt clip"}
    )
    assert reg.status_code == 201
    assert reg.json()["user_id"] is None

    dup = client.post("/api/devices", json={"device_id": "DEV-1"})
    assert dup.status_code == 409

    paired = client.post("/api/devices/DEV-1/pair", json={"user_id": user["id"]})
    assert paired.status_code == 200
    assert paired.json()["user_id"] == user["id"]
    assert paired.json()["paired_at"] is not None


def test_pair_missing_device_or_user_404(client):
    assert client.post("/api/devices/NOPE/pair", json={"user_id": 1}).status_code == 404
    client.post("/api/devices", json={"device_id": "DEV-2"})
    assert (
        client.post("/api/devices/DEV-2/pair", json={"user_id": 999}).status_code == 404
    )


def test_contacts_crud(client):
    user = client.post("/api/users", json={"display_name": "Yaa"}).json()

    c = client.post(
        "/api/users/{}/contacts".format(user["id"]),
        json={"name": "Mum", "phone": "+2330000", "priority": 0},
    )
    assert c.status_code == 201
    cid = c.json()["id"]

    listed = client.get("/api/users/{}/contacts".format(user["id"])).json()
    assert len(listed) == 1

    upd = client.patch("/api/contacts/{}".format(cid), json={"phone": "+2331111"})
    assert upd.json()["phone"] == "+2331111"

    assert client.delete("/api/contacts/{}".format(cid)).status_code == 204
    assert client.get("/api/users/{}/contacts".format(user["id"])).json() == []


def test_contacts_for_missing_user_404(client):
    assert client.get("/api/users/999/contacts").status_code == 404
    assert (
        client.post("/api/users/999/contacts", json={"name": "x", "phone": "y"}).status_code
        == 404
    )


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
