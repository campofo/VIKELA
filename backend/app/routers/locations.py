"""Live location track reads (for the mobile app / dashboard).

Pings are written by the device via POST /api/hardware/location (see
hardware.py). These endpoints return them oldest-first so a client can draw the
movement track for a panic incident or a device.
"""

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.database import get_session
from app.models import LocationPing
from app.schemas import LocationPingOut

router = APIRouter(prefix="/api", tags=["locations"])


@router.get("/alerts/{alert_id}/locations", response_model=list[LocationPingOut])
def list_alert_locations(
    alert_id: int,
    limit: int = Query(default=500, le=2000),
    session: Session = Depends(get_session),
):
    return session.exec(
        select(LocationPing)
        .where(LocationPing.alert_id == alert_id)
        .order_by(LocationPing.created_at)
        .limit(limit)
    ).all()


@router.get("/devices/{device_id}/locations", response_model=list[LocationPingOut])
def list_device_locations(
    device_id: str,
    limit: int = Query(default=500, le=2000),
    session: Session = Depends(get_session),
):
    return session.exec(
        select(LocationPing)
        .where(LocationPing.device_id == device_id)
        .order_by(LocationPing.created_at.desc())
        .limit(limit)
    ).all()
