"""Mount ultimate 0242.
"""
from __future__ import annotations

ID = "mount_ultimate_0242"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 242}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
