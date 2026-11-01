"""Mount ultimate 0222.
"""
from __future__ import annotations

ID = "mount_ultimate_0222"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 222}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
