"""Mount ultimate 0096.
"""
from __future__ import annotations

ID = "mount_ultimate_0096"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 96}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
