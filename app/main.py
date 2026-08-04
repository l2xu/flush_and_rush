from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.responses import Response

from app.db import get_latest_session, init_db
from app.guest_frontend import render_guest_page
from app.services.sensor_service import SensorSessionService
from app.settings import load_settings


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    init_db()
    settings = load_settings()

    sensor_service = SensorSessionService(
        sensor_entity_id=settings.sensor_entity_id,
        sensor_inverted=settings.sensor_inverted,
    )
    app_instance.state.sensor_service = sensor_service
    await sensor_service.start()

    yield

    await sensor_service.stop()


app = FastAPI(title="Klo-Tracker", version="0.2.0", lifespan=lifespan, redirect_slashes=False)
SIDEBAR_ROUTE_PREFIX = "/local_flush_and_rush"


def _guest_session_payload() -> dict:
    session = get_latest_session()
    return {"session": session}


def _guest_config_payload() -> dict:
    settings = load_settings()
    return {
        "yellow_threshold_sec": settings.yellow_threshold_sec,
        "red_threshold_sec": settings.red_threshold_sec,
        "fade_duration_ms": settings.fade_duration_ms,
        "message_duration_sec": settings.message_duration_sec,
        "transition_style": settings.transition_style,
        "messages": [{"time_sec": m.time_sec, "text": m.text} for m in settings.messages],
    }


@app.get("/health")
def health() -> JSONResponse:
    settings = load_settings()
    sensor_service: SensorSessionService = app.state.sensor_service
    return JSONResponse(
        {
            "status": "ok",
            "db_path": settings.db_path,
            "sensor_entity_id": settings.sensor_entity_id,
            "sensor_inverted": settings.sensor_inverted,
            "sensor_service_running": sensor_service.state.running,
            "sensor_last_state": sensor_service.state.last_sensor_state,
            "open_session_id": sensor_service.state.open_session_id,
            "sensor_last_error": sensor_service.state.last_error,
        }
    )


@app.get("/")
@app.get("//")
@app.get(SIDEBAR_ROUTE_PREFIX)
@app.get(f"{SIDEBAR_ROUTE_PREFIX}/")
def index() -> Response:
    return HTMLResponse(render_guest_page())


@app.get("/guest", response_class=HTMLResponse)
@app.get(f"{SIDEBAR_ROUTE_PREFIX}/guest", response_class=HTMLResponse)
@app.get(f"{SIDEBAR_ROUTE_PREFIX}/guest/", response_class=HTMLResponse)
def guest_view() -> HTMLResponse:
    return HTMLResponse(render_guest_page())


@app.get("/api/guest/session")
@app.get(f"{SIDEBAR_ROUTE_PREFIX}/api/guest/session")
def api_guest_session() -> JSONResponse:
    return JSONResponse(_guest_session_payload())


@app.get("/api/guest/config")
@app.get(f"{SIDEBAR_ROUTE_PREFIX}/api/guest/config")
def api_guest_config() -> JSONResponse:
    return JSONResponse(_guest_config_payload())


@app.get(f"{SIDEBAR_ROUTE_PREFIX}/{{path:path}}", response_class=HTMLResponse)
def sidebar_panel_fallback(path: str) -> HTMLResponse:
    # HA can open custom panel URLs with variant subpaths; serve guest shell for non-API paths.
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")
    return HTMLResponse(render_guest_page())


