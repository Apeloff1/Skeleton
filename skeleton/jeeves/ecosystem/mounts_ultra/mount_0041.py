"""Mount ultra 0041.
"""
from __future__ import annotations

ID = "mount_ultra_0041"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 41}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
