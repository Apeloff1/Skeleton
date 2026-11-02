"""Mount eco_supreme 0333.
"""
from __future__ import annotations

ID = "mount_eco_supreme_0333"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 333}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
