"""Firmware-facing hardware alert endpoint.

This is the native replacement for the Firebase `hardwareAlert` Cloud Function.
It records the alert and resolves the device to its user's emergency contacts,
which it returns so the SIM7000G firmware can send the SMS itself.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.database import get_session
from app.models import Alert, Device, EmergencyContact, LocationPing
from app.schemas import (
    AlertUser,
    HardwareAlertIn,
    HardwareAlertOut,
    LocationPingAck,
    LocationPingIn,
)

router = APIRouter(tags=["hardware"])


# Canonical REST path plus the /hardwareAlert alias used by the deployment guide
# and older firmware URLs. Both hit the same handler; the alias is hidden from
# the OpenAPI docs to avoid duplication.
@router.post("/api/hardware/alert", response_model=HardwareAlertOut)
@router.post("/hardwareAlert", response_model=HardwareAlertOut, include_in_schema=False)
def receive_alert(payload: HardwareAlertIn, session: Session = Depends(get_session)):
    device = session.get(Device, payload.device_id)

    user = None
    contacts: list[str] = []
    if device is not None:
        device.last_seen_at = datetime.now(timezone.utc)
        session.add(device)
        if device.user_id is not None:
            from app.models import User

            user = session.get(User, device.user_id)
            rows = session.exec(
                select(EmergencyContact)
                .where(EmergencyContact.user_id == device.user_id)
                .order_by(EmergencyContact.priority)
            ).all()
            contacts = [c.phone for c in rows]

    alert = Alert(
        device_id=payload.device_id,
        user_id=device.user_id if device is not None else None,
        latitude=payload.latitude,
        longitude=payload.longitude,
        battery_level=payload.battery_level,
    )
    session.add(alert)
    session.commit()
    session.refresh(alert)

    return HardwareAlertOut(
        alert_id=alert.id,
        device_paired=user is not None,
        user=AlertUser(id=user.id, display_name=user.display_name) if user else None,
        contacts=contacts,
    )


@router.post("/api/hardware/location", response_model=LocationPingAck)
@router.post("/locationUpdate", response_model=LocationPingAck, include_in_schema=False)
def receive_location(payload: LocationPingIn, session: Session = Depends(get_session)):
    # A live location update streamed while a panic is active. Records a
    # LocationPing linked to the device's user (and the panic Alert when the
    # device sent an alert_id) so the app can show a live track.
    device = session.get(Device, payload.device_id)
    user_id = device.user_id if device is not None else None
    if device is not None:
        device.last_seen_at = datetime.now(timezone.utc)
        session.add(device)

    # Ignore an unknown alert_id (e.g. stale on the device) rather than fail the
    # FK constraint — a ping without a linked alert is still worth recording.
    alert_id = payload.alert_id
    if alert_id is not None and session.get(Alert, alert_id) is None:
        alert_id = None

    ping = LocationPing(
        alert_id=alert_id,
        device_id=payload.device_id,
        user_id=user_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        battery_level=payload.battery_level,
    )
    session.add(ping)
    session.commit()
    session.refresh(ping)

    return LocationPingAck(ok=True, ping_id=ping.id, device_paired=user_id is not None)
