"""VIKELA native backend (FastAPI + SQLite).

Replaces the Firebase Cloud Functions + Firestore backend. Receives hardware
panic alerts from the SIM7000G firmware, resolves the device to its user, stores
alert history, and exposes a REST data API for the mobile app.

SMS is deliberately not sent here: the ESP32's SIM7000G sends the SMS. The alert
endpoint returns the resolved emergency contacts so the firmware can do so.
"""
