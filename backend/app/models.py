"""SQLModel table definitions for the VIKELA backend.

Mirrors the Firestore collections the Firebase backend used:
  users              -> User
  devices/{deviceId} -> Device      (device_id is the firmware DEVICE_ID)
  emergency contacts -> EmergencyContact
  alerts             -> Alert
"""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    display_name: str
    phone: Optional[str] = None
    # Free-form medical info (allergies, blood type, notes); JSON or plain text.
    medical_info: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)


class Device(SQLModel, table=True):
    # device_id is the firmware's DEVICE_ID string, so it is the natural key.
    device_id: str = Field(primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    label: Optional[str] = None
    paired_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_utcnow)


class EmergencyContact(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str
    phone: str
    # Lower priority value = contacted first.
    priority: int = 0


class Alert(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    device_id: str = Field(index=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # Firmware reports -1 when the battery level is unavailable.
    battery_level: Optional[int] = None
    source: str = "hardware"
    status: str = "received"
    created_at: datetime = Field(default_factory=_utcnow)
