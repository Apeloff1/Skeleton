"""Mount ultra 0042.
"""
from __future__ import annotations

ID = "mount_ultra_0042"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 42}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
