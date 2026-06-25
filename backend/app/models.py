from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4


class ValidationError(ValueError):
    pass


@dataclass
class HardwareAlertIn:
    device_id: str
    message: str
    user_id: Optional[str] = None
    trigger_type: str = "hardware"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_source: str = "sim7000g_gps"
    delivery_attempt: str = "cellular_http"
    battery_level: Optional[float] = None
    timestamp: Optional[str] = None

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        expected_trigger_type: str = "hardware",
    ) -> "HardwareAlertIn":
        if not isinstance(data, dict):
            raise ValidationError("JSON body must be an object.")

        device_id = clean_required_string(data.get("device_id"), "device_id", 100)
        message = clean_required_string(data.get("message"), "message", 500)
        trigger_type = (
            clean_optional_string(data.get("trigger_type"), "trigger_type", 30)
            or expected_trigger_type
        )
        if trigger_type != expected_trigger_type:
            raise ValidationError("trigger_type must be '{}'.".format(expected_trigger_type))

        timestamp = clean_optional_string(data.get("timestamp"), "timestamp", 100)
        if timestamp in ("", "unavailable"):
            timestamp = None
        default_location_source = (
            "mobile_gps" if expected_trigger_type == "mobile" else "sim7000g_gps"
        )
        default_delivery_attempt = (
            "mobile_http" if expected_trigger_type == "mobile" else "cellular_http"
        )

        return cls(
            device_id=device_id,
            message=message,
            user_id=clean_optional_string(data.get("user_id"), "user_id", 100),
            trigger_type=trigger_type,
            latitude=clean_coordinate(data.get("latitude"), "latitude", -90, 90),
            longitude=clean_coordinate(data.get("longitude"), "longitude", -180, 180),
            location_source=clean_optional_string(
                data.get("location_source"), "location_source", 80
            ) or default_location_source,
            delivery_attempt=clean_optional_string(
                data.get("delivery_attempt"), "delivery_attempt", 80
            ) or default_delivery_attempt,
            battery_level=clean_optional_float(data.get("battery_level"), "battery_level"),
            timestamp=timestamp,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AlertRecord(HardwareAlertIn):
    alert_id: str = ""
    received_at: str = ""
    status: str = "triage_pending"
    maps_url: Optional[str] = None
    location_anomaly: bool = False
    anomaly_level: str = "unknown"
    anomaly_score: int = 0
    anomaly_reasons: Optional[List[str]] = None
    distance_from_previous_km: Optional[float] = None
    speed_from_previous_kmh: Optional[float] = None

    @classmethod
    def from_hardware_alert(cls, alert: HardwareAlertIn) -> "AlertRecord":
        maps_url = None
        if alert.latitude is not None and alert.longitude is not None:
            maps_url = f"https://maps.google.com/?q={alert.latitude:.6f},{alert.longitude:.6f}"

        return cls(
            **alert.to_dict(),
            alert_id=str(uuid4()),
            received_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            status="triage_pending",
            maps_url=maps_url,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AlertRecord":
        data.setdefault("location_anomaly", False)
        data.setdefault("anomaly_level", "unknown")
        data.setdefault("anomaly_score", 0)
        data.setdefault("anomaly_reasons", [])
        data.setdefault("distance_from_previous_km", None)
        data.setdefault("speed_from_previous_kmh", None)
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EmergencyContact:
    phone_number: str
    name: Optional[str] = None
    relationship: Optional[str] = None
    enabled: bool = True
    contact_id: str = ""
    created_at: str = ""

    @classmethod
    def create(cls, data: Dict[str, Any]) -> "EmergencyContact":
        if not isinstance(data, dict):
            raise ValidationError("JSON body must be an object.")

        enabled = data.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValidationError("enabled must be a boolean.")

        return cls(
            contact_id=str(uuid4()),
            phone_number=clean_phone_number(data.get("phone_number")),
            name=clean_optional_string(data.get("name"), "name", 100),
            relationship=clean_optional_string(data.get("relationship"), "relationship", 100),
            enabled=enabled,
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmergencyContact":
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NotificationRecord:
    alert_id: str
    contact_id: str
    phone_number: str
    message: str
    channel: str = "sms_webhook"
    status: str = "pending"
    provider_status: Optional[int] = None
    provider_response: Optional[str] = None
    notification_id: str = ""
    created_at: str = ""

    @classmethod
    def create(
        cls,
        alert: AlertRecord,
        contact: EmergencyContact,
        message: str,
        status: str,
        provider_status: Optional[int] = None,
        provider_response: Optional[str] = None,
    ) -> "NotificationRecord":
        return cls(
            notification_id=str(uuid4()),
            alert_id=alert.alert_id,
            contact_id=contact.contact_id,
            phone_number=contact.phone_number,
            message=message,
            status=status,
            provider_status=provider_status,
            provider_response=provider_response,
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NotificationRecord":
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def clean_required_string(value: Any, field: str, max_length: int) -> str:
    value = clean_optional_string(value, field, max_length)
    if not value:
        raise ValidationError(f"{field} is required.")
    return value


def clean_optional_string(value: Any, field: str, max_length: int) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string.")
    value = value.strip()
    if len(value) > max_length:
        raise ValidationError(f"{field} is too long.")
    return value


def clean_phone_number(value: Any) -> str:
    phone_number = clean_required_string(value, "phone_number", 20)
    if (
        not phone_number.startswith("+")
        or not phone_number[1:].isdigit()
        or len(phone_number) < 8
    ):
        raise ValidationError(
            "phone_number must use international format, for example +233000000000."
        )
    return phone_number


def clean_coordinate(value: Any, field: str, minimum: float, maximum: float) -> Optional[float]:
    value = clean_optional_float(value, field)
    if value is None:
        return None
    if value < minimum or value > maximum:
        raise ValidationError(f"{field} is out of range.")
    return value


def clean_optional_float(value: Any, field: str) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValidationError(f"{field} must be a number.")
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a number.")
