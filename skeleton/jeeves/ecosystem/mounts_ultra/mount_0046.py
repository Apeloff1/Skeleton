"""Mount ultra 0046.
"""
from __future__ import annotations

ID = "mount_ultra_0046"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 46}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
