"""Mount eco_supreme 0404.
"""
from __future__ import annotations

ID = "mount_eco_supreme_0404"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 404}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
