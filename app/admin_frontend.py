from functools import lru_cache
from pathlib import Path

_ADMIN_HTML_PATH = Path(__file__).parent / "static" / "admin.html"


@lru_cache(maxsize=1)
def render_admin_page() -> str:
    return _ADMIN_HTML_PATH.read_text(encoding="utf-8")
