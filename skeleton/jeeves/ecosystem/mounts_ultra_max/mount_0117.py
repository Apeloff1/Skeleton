"""Mount ultra_max 0117.
"""
from __future__ import annotations

ID = "mount_ultra_max_0117"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 117}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
