"""Mount ultra_max 0132.
"""
from __future__ import annotations

ID = "mount_ultra_max_0132"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 132}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
