"""Firmware-facing hardware alert endpoint.

This is the native replacement for the Firebase `hardwareAlert` Cloud Function.
It records the alert and resolves the device to its user's emergency contacts,
which it returns so the SIM7000G firmware can send the SMS itself.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.database import get_session
from app.models import Alert, Device, EmergencyContact
from app.schemas import AlertUser, HardwareAlertIn, HardwareAlertOut

router = APIRouter(prefix="/api/hardware", tags=["hardware"])


@router.post("/alert", response_model=HardwareAlertOut)
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
