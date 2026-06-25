import json
from pathlib import Path
from typing import List

from app.models import AlertRecord, EmergencyContact, NotificationRecord, ValidationError


class AlertStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, alert: AlertRecord) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(alert.to_dict(), separators=(",", ":")) + "\n")

    def list_recent(self, limit: int = 50) -> List[AlertRecord]:
        if not self.path.exists():
            return []

        with self.path.open("r", encoding="utf-8") as handle:
            lines = [line.strip() for line in handle if line.strip()]

        records = []
        for line in lines[-limit:]:
            records.append(AlertRecord.from_dict(json.loads(line)))
        return list(reversed(records))


class ContactStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def list_all(self) -> List[EmergencyContact]:
        if not self.path.exists():
            return []

        with self.path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        if not isinstance(data, list):
            raise ValidationError("contact store is not a JSON list.")

        return [EmergencyContact.from_dict(item) for item in data]

    def add(self, contact: EmergencyContact) -> EmergencyContact:
        contacts = self.list_all()
        if any(existing.phone_number == contact.phone_number for existing in contacts):
            raise ValidationError("phone_number already exists.")

        contacts.append(contact)
        self._write_all(contacts)
        return contact

    def delete(self, contact_id: str) -> bool:
        contacts = self.list_all()
        remaining = [contact for contact in contacts if contact.contact_id != contact_id]
        if len(remaining) == len(contacts):
            return False

        self._write_all(remaining)
        return True

    def _write_all(self, contacts: List[EmergencyContact]) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(
                [contact.to_dict() for contact in contacts],
                handle,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")


class NotificationStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, notification: NotificationRecord) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(notification.to_dict(), separators=(",", ":")) + "\n")

    def list_recent(self, limit: int = 50) -> List[NotificationRecord]:
        if not self.path.exists():
            return []

        with self.path.open("r", encoding="utf-8") as handle:
            lines = [line.strip() for line in handle if line.strip()]

        records = []
        for line in lines[-limit:]:
            records.append(NotificationRecord.from_dict(json.loads(line)))
        return list(reversed(records))
