import json
import os
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class SupervisorClientError(Exception):
    pass


class SupervisorClient:
    def __init__(self, token: Optional[str] = None, base_url: str = "http://supervisor"):
        self._token = token or os.getenv("SUPERVISOR_TOKEN", "")
        self._base_url = base_url.rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def get_entity_state(self, entity_id: str) -> str:
        if not self._token:
            raise SupervisorClientError("SUPERVISOR_TOKEN fehlt")

        encoded_entity_id = quote(entity_id, safe="._")
        url = f"{self._base_url}/core/api/states/{encoded_entity_id}"
        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise SupervisorClientError(f"HTTP Fehler von Supervisor API: {exc.code}") from exc
        except URLError as exc:
            raise SupervisorClientError(f"Supervisor API nicht erreichbar: {exc.reason}") from exc
        except TimeoutError as exc:
            raise SupervisorClientError("Timeout bei Supervisor API") from exc

        state = payload.get("state")
        if not isinstance(state, str):
            raise SupervisorClientError("Ungueltige Antwort von Supervisor API (state fehlt)")
        return state
