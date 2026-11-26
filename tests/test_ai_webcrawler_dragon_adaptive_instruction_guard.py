"""Adaptive instruction guard fixtures."""
from typing import Any

BASE = "https://example.com"
OTHER = "https://other.example.com"
ROBOTS = "User-agent: *\nAllow: /"
GOOD = "https://good.example.com"
BAD = "https://bad.example.com"
SITEMAP = "https://example.com/sitemap.xml"
HTML = "<html><body>ok</body></html>"

class ScriptedFetcher:
    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {}
    def fetch(self, url: str, **kwargs: Any) -> dict[str, Any]:
        return self.responses.get(url, {"ok": True, "status": 200, "body": HTML})

def make_run(urls: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "urls": urls or [BASE], "status": "queued"}

def resign(run: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "run": run, "status": "resigned"}

def step(run: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "run": run, "status": "stepped"}

def adaptive_instruction_guard(instruction: str, **kwargs: Any) -> dict[str, Any]:
    return {"ok": True, "guard": "adaptive", "instruction": instruction}
