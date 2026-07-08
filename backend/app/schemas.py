"""Pydantic request/response models for the VIKELA API.

Kept separate from the SQLModel tables so the wire contract is explicit — most
importantly the firmware-facing HardwareAlertIn/HardwareAlertOut pair, which must
stay compatible with firmware/micropython_lilygo_t_sim7000g_panic/main.py.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


# --- Hardware (firmware-facing) -------------------------------------------

class HardwareAlertIn(BaseModel):
    # Matches build_alert_payload() in the MicroPython firmware. latitude/
    # longitude are null when GPS timed out; battery_level is -1 when unknown.
    device_id: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    battery_level: Optional[int] = None


class AlertUser(BaseModel):
    id: Optional[int] = None
    display_name: Optional[str] = None


class HardwareAlertOut(BaseModel):
    alert_id: int
    device_paired: bool
    user: Optional[AlertUser] = None
    # Phone numbers ordered by priority; the firmware SMSs these over the SIM.
    contacts: List[str]


# --- Users ----------------------------------------------------------------

class UserCreate(BaseModel):
    display_name: str
    phone: Optional[str] = None
    medical_info: Optional[str] = None


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    phone: Optional[str] = None
    medical_info: Optional[str] = None


class UserOut(BaseModel):
    id: int
    display_name: str
    phone: Optional[str] = None
    medical_info: Optional[str] = None
    created_at: datetime


# --- Devices --------------------------------------------------------------

class DeviceCreate(BaseModel):
    device_id: str
    label: Optional[str] = None
    user_id: Optional[int] = None


class DevicePair(BaseModel):
    user_id: int


class DeviceOut(BaseModel):
    device_id: str
    user_id: Optional[int] = None
    label: Optional[str] = None
    paired_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    created_at: datetime


# --- Emergency contacts ---------------------------------------------------

class ContactCreate(BaseModel):
    name: str
    phone: str
    priority: int = 0


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    priority: Optional[int] = None


class ContactOut(BaseModel):
    id: int
    user_id: int
    name: str
    phone: str
    priority: int


# --- Live location tracking -----------------------------------------------

class LocationPingIn(BaseModel):
    # Streamed by the firmware every few seconds while a panic is active.
    device_id: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    battery_level: Optional[int] = None
    # The panic Alert this ping belongs to, when the device knows it.
    alert_id: Optional[int] = None


class LocationPingAck(BaseModel):
    ok: bool
    ping_id: int
    device_paired: bool


class LocationPingOut(BaseModel):
    id: int
    alert_id: Optional[int] = None
    device_id: str
    user_id: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    battery_level: Optional[int] = None
    created_at: datetime


# --- Alerts (history) -----------------------------------------------------

class AlertOut(BaseModel):
    id: int
    device_id: str
    user_id: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    battery_level: Optional[int] = None
    source: str
    status: str
    created_at: datetime
