from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from app.db import (
    delete_session,
    get_statistics,
    init_db,
    list_days,
    list_sessions_for_day,
)
from app.pages import render_page
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


app = FastAPI(title="Flush & Rush", version="0.4.0", lifespan=lifespan, redirect_slashes=False)


def _is_ingress(request: Request) -> bool:
    """Erkennt Aufrufe ueber den Home-Assistant-Ingress-Proxy.

    Der Supervisor setzt X-Ingress-Path (Basis-Pfad des Panels); neuere Versionen
    zusaetzlich X-Hass-Source: core.ingress. Beide Signale werden akzeptiert.
    """
    return bool(request.headers.get("X-Ingress-Path")) or (
        request.headers.get("X-Hass-Source", "").lower() == "core.ingress"
    )


def _root_view(request: Request) -> str:
    """Welche Seite die Add-on-Wurzel ausliefert.

    Der Sidebar-Eintrag oeffnet die Wurzel ueber Ingress und soll die
    Admin-Auswertung zeigen; der direkte Port-Zugriff (WC-Display) bleibt auf der
    Gaeste-Ansicht. Die Option 'sidebar_view' erzwingt bei Bedarf eine Seite.
    """
    configured = load_settings().sidebar_view
    if configured in {"admin", "guest"}:
        return configured
    return "admin" if _is_ingress(request) else "guest"


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


@app.get("/", response_class=HTMLResponse)
@app.get("//", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return HTMLResponse(render_page(_root_view(request)))


@app.get("/guest", response_class=HTMLResponse)
@app.get("/guest/", response_class=HTMLResponse)
def guest_view() -> HTMLResponse:
    return HTMLResponse(render_page("guest"))


@app.get("/admin", response_class=HTMLResponse)
@app.get("/admin/", response_class=HTMLResponse)
def admin_view() -> HTMLResponse:
    return HTMLResponse(render_page("admin"))


@app.get("/api/guest/config")
def api_guest_config() -> JSONResponse:
    return JSONResponse({"fade_duration_ms": load_settings().fade_duration_ms})


@app.get("/api/admin/days")
def api_admin_days() -> JSONResponse:
    return JSONResponse({"days": list_days()})


@app.get("/api/admin/stats")
def api_admin_stats(days: int = 30) -> JSONResponse:
    return JSONResponse(get_statistics(day_limit=max(1, min(days, 365))))


@app.get("/api/admin/days/{session_date}/sessions")
def api_admin_day_sessions(session_date: str) -> JSONResponse:
    return JSONResponse({"sessions": list_sessions_for_day(session_date)})


@app.delete("/api/admin/sessions/{session_id}")
def api_admin_delete_session(session_id: int) -> JSONResponse:
    if not delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session nicht gefunden")
    return JSONResponse({"deleted": True})


@app.websocket("/ws/guest")
async def ws_guest(websocket: WebSocket) -> None:
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
