"""Mount eco_supreme 0256.
"""
from __future__ import annotations

ID = "mount_eco_supreme_0256"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 256}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
