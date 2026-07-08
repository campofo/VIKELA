"""VIKELA HTTP relay.

The LILYGO T-SIM7000G modem cannot reliably establish HTTPS/TLS, so the hardware
sends plain HTTP to this relay and the relay forwards the request to the Firebase
Cloud Function over HTTPS.

    Hardware --HTTP--> VPS relay --HTTPS--> Firebase Cloud Function

The relay is stateless: it forwards the JSON body verbatim and returns Firebase's
status code and body to the device. Heartbeats (``{"type": "heartbeat"}``) are
acknowledged locally without forwarding, since they only signal liveness.
"""

import json
import logging
import os

import httpx
from fastapi import FastAPI, Request, Response

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger("vikela-relay")

# The Firebase Cloud Function the alert is forwarded to (over HTTPS).
FIREBASE_FUNCTION_URL = os.environ.get(
    "FIREBASE_FUNCTION_URL",
    "https://europe-west1-dara-cd3e8.cloudfunctions.net/hardwareAlert",
)
# Seconds to wait for Firebase before giving up.
RELAY_FORWARD_TIMEOUT = float(os.environ.get("RELAY_FORWARD_TIMEOUT", "30"))

app = FastAPI(title="VIKELA HTTP relay", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/hardwareAlert")
async def relay_hardware_alert(request: Request):
    raw = await request.body()
    content_type = request.headers.get("content-type", "application/json")
    client_host = request.client.host if request.client else "?"

    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        data = None

    # Heartbeats just confirm the device is alive; ack locally, do not forward.
    if isinstance(data, dict) and data.get("type") == "heartbeat":
        logger.info("Heartbeat from %s (device %s)", client_host, data.get("device_id"))
        return {"accepted": True, "type": "heartbeat"}

    logger.info("Alert from %s -> Firebase: %s", client_host, raw.decode("utf-8", "ignore"))
    try:
        async with httpx.AsyncClient(timeout=RELAY_FORWARD_TIMEOUT) as client:
            firebase = await client.post(
                FIREBASE_FUNCTION_URL,
                content=raw,
                headers={"Content-Type": content_type},
            )
    except httpx.HTTPError as exc:
        logger.error("Forward to Firebase failed: %s", exc)
        return Response(
            content=json.dumps({"accepted": False, "error": "upstream_unreachable"}),
            status_code=502,
            media_type="application/json",
        )

    logger.info("Firebase responded %s: %s", firebase.status_code, firebase.text)
    # Return Firebase's response verbatim so the device sees the real status.
    return Response(
        content=firebase.content,
        status_code=firebase.status_code,
        media_type=firebase.headers.get("content-type", "application/json"),
    )
