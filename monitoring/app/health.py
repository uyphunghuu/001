import os
import time

from fastapi import APIRouter
from sqlalchemy import text as sa_text

from app.database.session import SessionLocal

health_router = APIRouter(tags=["health"])

_startup_time = time.time()

HEALTH_QUERY = sa_text("SELECT 1")


@health_router.get("/health")
def health():
    status = "ok"
    components = {}

    try:
        with SessionLocal() as s:
            s.execute(HEALTH_QUERY)
        components["database"] = {"status": "ok"}
    except Exception as e:
        status = "degraded"
        components["database"] = {"status": "error", "message": str(e)}

    return {
        "status": status,
        "version": os.getenv("APP_VERSION", "0.1.0"),
        "uptime_seconds": int(time.time() - _startup_time),
        "components": components,
    }


@health_router.get("/ready")
def ready():
    try:
        with SessionLocal() as s:
            s.execute(HEALTH_QUERY)
        return {"status": "ready"}
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": str(e)},
        )


@health_router.get("/live")
def live():
    return {"status": "alive"}


@health_router.get("/startup")
def startup():
    elapsed = time.time() - _startup_time
    initialized = elapsed > 5
    return {
        "status": "started" if initialized else "starting",
        "elapsed_seconds": round(elapsed, 2),
    }
