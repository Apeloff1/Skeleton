"""Mount ultimate 0118.
"""
from __future__ import annotations

ID = "mount_ultimate_0118"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 118}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
