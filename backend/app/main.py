"""VIKELA native backend — FastAPI application entrypoint.

Run from the backend/ directory:
    uvicorn app.main:app --reload
Interactive API docs: http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.routers import alerts, contacts, devices, hardware, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="VIKELA backend",
    version="1.0.0",
    description="Native replacement for the Firebase VIKELA backend.",
    lifespan=lifespan,
)

app.include_router(hardware.router)
app.include_router(users.router)
app.include_router(devices.router)
app.include_router(contacts.router)
app.include_router(alerts.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
