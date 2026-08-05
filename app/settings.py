from dataclasses import dataclass
import json
import os
from typing import Any, Dict

OPTIONS_PATH = "/data/options.json"
LOCAL_TIMEZONE = "Europe/Berlin"


@dataclass(frozen=True)
class Settings:
    sensor_entity_id: str
    db_path: str
    sensor_inverted: bool
    fade_duration_ms: int


def _load_options() -> Dict[str, Any]:
    try:
        with open(OPTIONS_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return default


def load_settings() -> Settings:
    # Home Assistant Supervisor schreibt die YAML-Optionen als JSON nach /data/options.json.
    options = _load_options()

    return Settings(
        sensor_entity_id=str(options.get("sensor_entity_id", os.getenv("SENSOR_ENTITY_ID", "binary_sensor.klodeckel"))),
        db_path=os.getenv("KLO_TRACKER_DB_PATH", "/data/klo_tracker.db"),
        sensor_inverted=_as_bool(options.get("sensor_inverted", os.getenv("SENSOR_INVERTED", "false")), False),
        fade_duration_ms=int(options.get("fade_duration_ms", 600)),
    )
