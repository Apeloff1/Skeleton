"""Stub for dragon treasury fixtures."""
from typing import Any

obs = {"ok": True}
A = "a"
B = "b"
C = "c"
NOW = "2026-11-26T00:00:00Z"
DAY = "2026-11-26"
BASE = "https://example.com"

def treasury_fixture(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "treasury": True}
