"""Title peak 0120.
"""
from __future__ import annotations

ID = "title_peak_0120"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 120}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
