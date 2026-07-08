"""Seed the database with a demo user, device, and emergency contacts.

Usage (from the backend/ directory):
    python -m app.seed

Idempotent-ish: it registers the demo device only if it does not already exist.
Handy for the manual end-to-end curl test in the README.
"""

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.database import engine, init_db
from app.models import Device, EmergencyContact, User

DEMO_DEVICE_ID = "VIKELA-T-SIM7000G-001"


def seed():
    init_db()
    with Session(engine) as session:
        if session.get(Device, DEMO_DEVICE_ID) is not None:
            print("Demo device already present; nothing to seed.")
            return

        user = session.exec(
            select(User).where(User.display_name == "VIKELA User")
        ).first()
        if user is None:
            user = User(
                display_name="VIKELA User",
                phone="+233504647863",
                medical_info="Blood type O+, no known allergies",
            )
            session.add(user)
            session.commit()
            session.refresh(user)

        session.add_all(
            [
                EmergencyContact(
                    user_id=user.id, name="Primary Contact",
                    phone="+233504647863", priority=0,
                ),
                EmergencyContact(
                    user_id=user.id, name="Secondary Contact",
                    phone="+233555192380", priority=1,
                ),
            ]
        )
        session.add(
            Device(
                device_id=DEMO_DEVICE_ID,
                user_id=user.id,
                label="Demo panic device",
                paired_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
        print("Seeded user {}, device {}, and 2 contacts.".format(user.id, DEMO_DEVICE_ID))


if __name__ == "__main__":
    seed()
