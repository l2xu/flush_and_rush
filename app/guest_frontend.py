from functools import lru_cache
from pathlib import Path

_GUEST_HTML_PATH = Path(__file__).parent / "static" / "guest.html"


@lru_cache(maxsize=1)
def render_guest_page() -> str:
    return _GUEST_HTML_PATH.read_text(encoding="utf-8")
