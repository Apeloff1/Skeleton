"""Stub for adaptive instruction guard tests."""
from typing import Any

BASE = "https://example.com"
OTHER = "https://other.example.com"
ROBOTS = "User-agent: *\nAllow: /"
GOOD = "https://good.example.com"
BAD = "https://bad.example.com"
SITEMAP = "https://example.com/sitemap.xml"
HTML = "<html><body>ok</body></html>"

class ScriptedFetcher:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass
    def fetch(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"ok": True}

def make_run(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"ok": True}

def resign(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"ok": True}

def step(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"ok": True}

def adaptive_instruction_guard(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "guard": "adaptive"}
