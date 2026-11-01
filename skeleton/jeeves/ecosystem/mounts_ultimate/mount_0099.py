"""Mount ultimate 0099.
"""
from __future__ import annotations

ID = "mount_ultimate_0099"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 99}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
