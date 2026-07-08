"""Alert history reads (Firestore alert documents replacement)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.database import get_session
from app.models import Alert
from app.schemas import AlertOut

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts/{alert_id}", response_model=AlertOut)
def get_alert(alert_id: int, session: Session = Depends(get_session)):
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.get("/users/{user_id}/alerts", response_model=list[AlertOut])
def list_user_alerts(
    user_id: int,
    limit: int = Query(default=50, le=200),
    session: Session = Depends(get_session),
):
    return session.exec(
        select(Alert)
        .where(Alert.user_id == user_id)
        .order_by(Alert.created_at.desc())
        .limit(limit)
    ).all()


@router.get("/devices/{device_id}/alerts", response_model=list[AlertOut])
def list_device_alerts(
    device_id: str,
    limit: int = Query(default=50, le=200),
    session: Session = Depends(get_session),
):
    return session.exec(
        select(Alert)
        .where(Alert.device_id == device_id)
        .order_by(Alert.created_at.desc())
        .limit(limit)
    ).all()
