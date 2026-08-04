from dataclasses import dataclass, field
import json
import os
from typing import Any, Dict, List

OPTIONS_PATH = "/data/options.json"
TRANSITION_STYLES = {"fade", "slide", "zoom"}


@dataclass(frozen=True)
class MessageRule:
    time_sec: int
    text: str


@dataclass(frozen=True)
class Settings:
    sensor_entity_id: str
    db_path: str
    sensor_inverted: bool
    yellow_threshold_sec: int
    red_threshold_sec: int
    fade_duration_ms: int
    message_duration_sec: int
    transition_style: str
    messages: List[MessageRule] = field(default_factory=list)


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


def _parse_messages(raw: Any) -> List[MessageRule]:
    if not isinstance(raw, list):
        return []
    return [
        MessageRule(time_sec=int(item["time_sec"]), text=str(item.get("text", "")))
        for item in raw
        if isinstance(item, dict) and "time_sec" in item
    ]


def _parse_transition_style(raw: Any) -> str:
    value = str(raw or "fade").lower()
    return value if value in TRANSITION_STYLES else "fade"


def load_settings() -> Settings:
    # Home Assistant Supervisor schreibt die YAML-Optionen als JSON nach /data/options.json.
    options = _load_options()

    return Settings(
        sensor_entity_id=str(options.get("sensor_entity_id", os.getenv("SENSOR_ENTITY_ID", "binary_sensor.klodeckel"))),
        db_path=os.getenv("KLO_TRACKER_DB_PATH", "/data/klo_tracker.db"),
        sensor_inverted=_as_bool(options.get("sensor_inverted", os.getenv("SENSOR_INVERTED", "false")), False),
        yellow_threshold_sec=int(options.get("yellow_threshold_sec", 120)),
        red_threshold_sec=int(options.get("red_threshold_sec", 300)),
        fade_duration_ms=int(options.get("fade_duration_ms", 600)),
        message_duration_sec=int(options.get("message_duration_sec", 8)),
        transition_style=_parse_transition_style(options.get("transition_style", "fade")),
        messages=_parse_messages(options.get("messages", [])),
    )
