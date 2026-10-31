"""Mount peak 0093.
"""
from __future__ import annotations

ID = "mount_peak_0093"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 93}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
