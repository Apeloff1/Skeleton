"""Mount eco_supreme 0380.
"""
from __future__ import annotations

ID = "mount_eco_supreme_0380"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 380}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
