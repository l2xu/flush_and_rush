import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from app.db import (
    close_session,
    create_session,
    get_latest_open_session_id,
    log_event,
)
from app.supervisor_client import SupervisorClient, SupervisorClientError


_LOGGER = logging.getLogger(__name__)


@dataclass
class SensorRuntimeState:
    running: bool = False
    last_sensor_state: Optional[str] = None
    open_session_id: Optional[int] = None
    last_error: Optional[str] = None


class SensorSessionService:
    def __init__(
        self,
        sensor_entity_id: str,
        sensor_inverted: bool = False,
        poll_interval_sec: float = 1.0,
        min_transition_sec: float = 1.5,
        supervisor_client: Optional[SupervisorClient] = None,
    ):
        self._sensor_entity_id = sensor_entity_id
        self._sensor_inverted = sensor_inverted
        self._poll_interval_sec = poll_interval_sec
        self._min_transition_sec = min_transition_sec
        self._supervisor_client = supervisor_client or SupervisorClient()

        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._state_since: Optional[float] = None
        self._state = SensorRuntimeState()

    @property
    def state(self) -> SensorRuntimeState:
        return self._state

    async def start(self) -> None:
        if self._task and not self._task.done():
            return

        self._state.open_session_id = get_latest_open_session_id()
        self._stop_event.clear()

        if not self._supervisor_client.configured:
            self._state.last_error = "SUPERVISOR_TOKEN fehlt"
            _LOGGER.warning("Sensor-Service nicht gestartet: SUPERVISOR_TOKEN fehlt")
            return

        self._state.running = True
        self._task = asyncio.create_task(self._run(), name="sensor-session-service")
        _LOGGER.info("Sensor-Service gestartet fuer %s", self._sensor_entity_id)

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._state.running = False
        _LOGGER.info("Sensor-Service gestoppt")

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                sensor_state = self._supervisor_client.get_entity_state(self._sensor_entity_id)
                self._state.last_error = None
                self._handle_state(sensor_state)
            except SupervisorClientError as exc:
                self._state.last_error = str(exc)
                _LOGGER.warning("Sensor-Abfrage fehlgeschlagen: %s", exc)
            except Exception as exc:  # pragma: no cover
                self._state.last_error = str(exc)
                _LOGGER.exception("Unerwarteter Fehler im Sensor-Service: %s", exc)

            await asyncio.sleep(self._poll_interval_sec)

    def _handle_state(self, new_state: str) -> None:
        if new_state not in {"on", "off"}:
            return

        if self._sensor_inverted:
            new_state = "off" if new_state == "on" else "on"

        loop = asyncio.get_running_loop()
        now = loop.time()

        if self._state.last_sensor_state is None:
            self._state.last_sensor_state = new_state
            self._state_since = now
            log_event("sensor_initial_state", new_state)
            return

        if new_state == self._state.last_sensor_state:
            return

        if self._state_since is not None and (now - self._state_since) < self._min_transition_sec:
            log_event("sensor_bounce_ignored", new_state)
            return

        previous_state = self._state.last_sensor_state
        self._state.last_sensor_state = new_state
        self._state_since = now

        log_event("sensor_transition", f"{previous_state}->{new_state}")

        if previous_state == "off" and new_state == "on":
            self._start_session()
        elif previous_state == "on" and new_state == "off":
            self._stop_session()

    def _start_session(self) -> None:
        if self._state.open_session_id is not None:
            return

        session_id = create_session()
        self._state.open_session_id = session_id
        log_event("session_started", str(session_id))
        _LOGGER.info("Session gestartet: id=%s", session_id)

    def _stop_session(self) -> None:
        if self._state.open_session_id is None:
            return

        session_id = self._state.open_session_id
        closed = close_session(session_id)
        if closed:
            log_event("session_closed", str(session_id))
            _LOGGER.info("Session beendet: id=%s", session_id)
        else:
            _LOGGER.warning("Session konnte nicht beendet werden: id=%s", session_id)
        self._state.open_session_id = None
