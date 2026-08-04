from dataclasses import dataclass
from typing import Optional


@dataclass
class SessionRecord:
    id: int
    started_at: str
    ended_at: Optional[str]
    duration_sec: Optional[int]
    status: str
