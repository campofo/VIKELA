"""VIKELA native backend — FastAPI application entrypoint.

Run from the backend/ directory:
    uvicorn app.main:app --reload
Interactive API docs: http://localhost:8000/docs
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import alerts, contacts, devices, hardware, locations, users


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

# CORS so the mobile app / a web dashboard can call the API cross-origin.
# VIKELA_CORS_ORIGINS is a comma-separated list, or "*" for any origin.
_origins = os.environ.get("VIKELA_CORS_ORIGINS", "*").strip()
_allow_origins = (
    ["*"] if _origins == "*" else [o.strip() for o in _origins.split(",") if o.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(hardware.router)
app.include_router(users.router)
app.include_router(devices.router)
app.include_router(contacts.router)
app.include_router(alerts.router)
app.include_router(locations.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
