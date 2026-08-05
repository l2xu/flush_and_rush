from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.responses import Response

from app.admin_frontend import render_admin_page
from app.db import (
    delete_session,
    get_latest_session,
    init_db,
    list_days,
    list_sessions_for_day,
)
from app.guest_frontend import render_guest_page
from app.services.sensor_service import SensorSessionService
from app.settings import load_settings
from app.ws_manager import GuestConnectionManager


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    init_db()
    settings = load_settings()

    ws_manager = GuestConnectionManager()
    app_instance.state.ws_manager = ws_manager

    sensor_service = SensorSessionService(
        sensor_entity_id=settings.sensor_entity_id,
        sensor_inverted=settings.sensor_inverted,
        broadcaster=ws_manager.broadcast,
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
        "fade_duration_ms": settings.fade_duration_ms,
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


@app.get("/admin", response_class=HTMLResponse)
@app.get(f"{SIDEBAR_ROUTE_PREFIX}/admin", response_class=HTMLResponse)
@app.get(f"{SIDEBAR_ROUTE_PREFIX}/admin/", response_class=HTMLResponse)
def admin_view() -> HTMLResponse:
    return HTMLResponse(render_admin_page())


@app.get("/api/guest/session")
@app.get(f"{SIDEBAR_ROUTE_PREFIX}/api/guest/session")
def api_guest_session() -> JSONResponse:
    return JSONResponse(_guest_session_payload())


@app.get("/api/guest/config")
@app.get(f"{SIDEBAR_ROUTE_PREFIX}/api/guest/config")
def api_guest_config() -> JSONResponse:
    return JSONResponse(_guest_config_payload())


@app.get("/api/admin/days")
@app.get(f"{SIDEBAR_ROUTE_PREFIX}/api/admin/days")
def api_admin_days() -> JSONResponse:
    return JSONResponse({"days": list_days()})


@app.get("/api/admin/days/{session_date}/sessions")
@app.get(f"{SIDEBAR_ROUTE_PREFIX}/api/admin/days/{{session_date}}/sessions")
def api_admin_day_sessions(session_date: str) -> JSONResponse:
    return JSONResponse({"sessions": list_sessions_for_day(session_date)})


@app.delete("/api/admin/sessions/{session_id}")
@app.delete(f"{SIDEBAR_ROUTE_PREFIX}/api/admin/sessions/{{session_id}}")
def api_admin_delete_session(session_id: int) -> JSONResponse:
    deleted = delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session nicht gefunden")
    return JSONResponse({"deleted": True})


async def _guest_websocket(websocket: WebSocket) -> None:
    ws_manager: GuestConnectionManager = websocket.app.state.ws_manager
    sensor_service: SensorSessionService = websocket.app.state.sensor_service

    await ws_manager.connect(websocket)
    try:
        await websocket.send_json(sensor_service.snapshot_payload())
        while True:
            # Guest-Client sendet keine Daten, Verbindung wird nur zum Broadcast genutzt.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await ws_manager.disconnect(websocket)


@app.websocket("/ws/guest")
async def ws_guest(websocket: WebSocket) -> None:
    await _guest_websocket(websocket)


@app.websocket(f"{SIDEBAR_ROUTE_PREFIX}/ws/guest")
async def ws_guest_sidebar(websocket: WebSocket) -> None:
    await _guest_websocket(websocket)


@app.get(f"{SIDEBAR_ROUTE_PREFIX}/{{path:path}}", response_class=HTMLResponse)
def sidebar_panel_fallback(path: str) -> HTMLResponse:
    # HA can open custom panel URLs with variant subpaths; serve guest shell for non-API/ws paths.
    if path.startswith("api/") or path.startswith("ws/"):
        raise HTTPException(status_code=404, detail="Not Found")
    if path.startswith("admin"):
        return HTMLResponse(render_admin_page())
    return HTMLResponse(render_guest_page())



