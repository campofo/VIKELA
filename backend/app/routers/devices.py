"""Device registration + pairing (Firestore `devices/{deviceId}` replacement)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.database import get_session
from app.models import Alert, Device, User
from app.schemas import DeviceCreate, DeviceOut, DevicePair

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.post("", response_model=DeviceOut, status_code=201)
def register_device(payload: DeviceCreate, session: Session = Depends(get_session)):
    if session.get(Device, payload.device_id) is not None:
        raise HTTPException(status_code=409, detail="Device already registered")
    if payload.user_id is not None and session.get(User, payload.user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    device = Device(
        device_id=payload.device_id,
        label=payload.label,
        user_id=payload.user_id,
        paired_at=datetime.now(timezone.utc) if payload.user_id is not None else None,
    )
    session.add(device)
    session.commit()
    session.refresh(device)
    return device


@router.get("", response_model=list[DeviceOut])
def list_devices(session: Session = Depends(get_session)):
    return session.exec(select(Device)).all()


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(device_id: str, session: Session = Depends(get_session)):
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.post("/{device_id}/pair", response_model=DeviceOut)
def pair_device(
    device_id: str, payload: DevicePair, session: Session = Depends(get_session)
):
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    if session.get(User, payload.user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    device.user_id = payload.user_id
    device.paired_at = datetime.now(timezone.utc)
    session.add(device)
    session.commit()
    session.refresh(device)
    return device


@router.post("/{device_id}/resolve", response_model=DeviceOut)
def resolve_device(device_id: str, session: Session = Depends(get_session)):
    # Stop live tracking for a device (panic resolved). Also marks the device's
    # most recent unresolved alert as resolved. Use this when there is no single
    # alert_id to resolve by (e.g. the original alert POST never reached us).
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    device.tracking_stop_requested = True
    session.add(device)
    latest = session.exec(
        select(Alert)
        .where(Alert.device_id == device_id, Alert.status != "resolved")
        .order_by(Alert.created_at.desc())
    ).first()
    if latest is not None:
        latest.status = "resolved"
        session.add(latest)
    session.commit()
    session.refresh(device)
    return device
