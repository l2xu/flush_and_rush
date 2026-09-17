from functools import lru_cache
from pathlib import Path

_STATIC_DIR = Path(__file__).parent / "static"
_PAGES = frozenset({"guest", "admin"})


@lru_cache(maxsize=len(_PAGES))
def render_page(name: str) -> str:
    """Laedt guest.html bzw. admin.html einmalig und haelt sie im Cache."""
    if name not in _PAGES:
        raise ValueError(f"Unbekannte Seite: {name}")
    return (_STATIC_DIR / f"{name}.html").read_text(encoding="utf-8")
