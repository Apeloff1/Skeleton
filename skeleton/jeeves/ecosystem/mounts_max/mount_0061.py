"""Mount max 0061.
"""
from __future__ import annotations

ID = "mount_max_0061"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 61}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
