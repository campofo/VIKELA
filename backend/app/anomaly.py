import math
from datetime import datetime
from typing import Dict, List, Optional

from app.models import AlertRecord


MAX_NORMAL_SPEED_KMH = 130
SUSPICIOUS_DISTANCE_KM = 5
CRITICAL_DISTANCE_KM = 20
RECENT_WINDOW_MINUTES = 10


def analyze_location_anomaly(
    current: AlertRecord,
    previous_alerts: List[AlertRecord],
) -> Dict[str, object]:
    if current.latitude is None or current.longitude is None:
        return {
            "location_anomaly": False,
            "anomaly_level": "unknown",
            "anomaly_score": 0,
            "anomaly_reasons": ["current alert has no GPS location"],
            "distance_from_previous_km": None,
            "speed_from_previous_kmh": None,
        }

    previous = last_alert_with_location(current.device_id, previous_alerts)
    if previous is None:
        return {
            "location_anomaly": False,
            "anomaly_level": "baseline",
            "anomaly_score": 10,
            "anomaly_reasons": ["first known GPS location for this device"],
            "distance_from_previous_km": None,
            "speed_from_previous_kmh": None,
        }

    distance_km = haversine_km(
        previous.latitude,
        previous.longitude,
        current.latitude,
        current.longitude,
    )
    minutes = minutes_between(previous.received_at, current.received_at)
    speed_kmh = None
    if minutes and minutes > 0:
        speed_kmh = distance_km / (minutes / 60)

    score = 0
    reasons = []
    if distance_km >= CRITICAL_DISTANCE_KM:
        score += 45
        reasons.append("large location jump from previous alert")
    elif distance_km >= SUSPICIOUS_DISTANCE_KM:
        score += 25
        reasons.append("noticeable location change from previous alert")

    if speed_kmh is not None and speed_kmh >= MAX_NORMAL_SPEED_KMH:
        score += 45
        reasons.append("movement speed is unusually high")

    if minutes is not None and minutes <= RECENT_WINDOW_MINUTES and distance_km >= SUSPICIOUS_DISTANCE_KM:
        score += 20
        reasons.append("large movement happened within a short time window")

    if not reasons:
        reasons.append("location movement is within expected range")

    score = min(score, 100)
    return {
        "location_anomaly": score >= 50,
        "anomaly_level": anomaly_level(score),
        "anomaly_score": score,
        "anomaly_reasons": reasons,
        "distance_from_previous_km": round(distance_km, 3),
        "speed_from_previous_kmh": round(speed_kmh, 1) if speed_kmh is not None else None,
    }


def last_alert_with_location(
    device_id: str,
    alerts: List[AlertRecord],
) -> Optional[AlertRecord]:
    for alert in alerts:
        if alert.device_id != device_id:
            continue
        if alert.latitude is None or alert.longitude is None:
            continue
        if not alert.received_at:
            continue
        return alert
    return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def minutes_between(start: str, end: str) -> Optional[float]:
    try:
        start_dt = parse_utc_timestamp(start)
        end_dt = parse_utc_timestamp(end)
    except ValueError:
        return None
    delta = end_dt - start_dt
    return max(delta.total_seconds() / 60, 0)


def parse_utc_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def anomaly_level(score: int) -> str:
    if score >= 80:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "watch"
    return "normal"
