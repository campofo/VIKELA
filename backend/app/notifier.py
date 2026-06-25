import json
import os
import urllib.error
import urllib.request
from typing import List, Tuple

from app.models import AlertRecord, EmergencyContact, NotificationRecord
from app.storage import NotificationStore


SMS_WEBHOOK_URL = os.getenv("VIKELA_SMS_WEBHOOK_URL", "").strip()
SMS_WEBHOOK_TOKEN = os.getenv("VIKELA_SMS_WEBHOOK_TOKEN", "").strip()


def notify_panic_contacts(
    alert: AlertRecord,
    contacts: List[EmergencyContact],
    store: NotificationStore,
) -> List[NotificationRecord]:
    notifications = []
    message = build_responder_message(alert)
    for contact in contacts:
        if not contact.enabled:
            continue
        status, provider_status, provider_response = send_sms_webhook(
            contact.phone_number,
            message,
            alert,
        )
        notification = NotificationRecord.create(
            alert=alert,
            contact=contact,
            message=message,
            status=status,
            provider_status=provider_status,
            provider_response=provider_response,
        )
        store.append(notification)
        notifications.append(notification)
    return notifications


def build_responder_message(alert: AlertRecord) -> str:
    lines = [
        "VIKELA EMERGENCY ALERT",
        "Trigger: {}".format(alert.trigger_type),
        "Device: {}".format(alert.device_id),
        "Alert: {}".format(alert.alert_id),
        "Anomaly: {} ({})".format(alert.anomaly_level, alert.anomaly_score),
    ]

    if alert.latitude is not None and alert.longitude is not None:
        lines.append("GPS: {:.6f},{:.6f}".format(alert.latitude, alert.longitude))
        lines.append("Map: {}".format(alert.maps_url))
    else:
        lines.append("Location unavailable")

    if alert.location_anomaly and alert.anomaly_reasons:
        lines.append("Reason: {}".format("; ".join(alert.anomaly_reasons[:2])))

    if alert.distance_from_previous_km is not None:
        lines.append("Moved: {} km".format(alert.distance_from_previous_km))

    return "\n".join(lines)


def send_sms_webhook(
    phone_number: str,
    message: str,
    alert: AlertRecord,
) -> Tuple[str, int, str]:
    if not SMS_WEBHOOK_URL:
        return "queued_no_provider", None, "VIKELA_SMS_WEBHOOK_URL is not configured"

    payload = json.dumps(
        {
            "to": phone_number,
            "message": message,
            "alert_id": alert.alert_id,
            "device_id": alert.device_id,
            "anomaly_level": alert.anomaly_level,
            "anomaly_score": alert.anomaly_score,
        }
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if SMS_WEBHOOK_TOKEN:
        headers["Authorization"] = "Bearer {}".format(SMS_WEBHOOK_TOKEN)

    request = urllib.request.Request(
        SMS_WEBHOOK_URL,
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read(300).decode("utf-8", "replace")
            status_code = response.getcode()
        if 200 <= status_code < 300:
            return "sent", status_code, body
        return "failed", status_code, body
    except urllib.error.HTTPError as exc:
        body = exc.read(300).decode("utf-8", "replace")
        return "failed", exc.code, body
    except urllib.error.URLError as exc:
        return "failed", None, str(exc.reason)
