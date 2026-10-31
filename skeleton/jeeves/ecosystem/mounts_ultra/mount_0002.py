"""Mount ultra 0002.
"""
from __future__ import annotations

ID = "mount_ultra_0002"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 2}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
