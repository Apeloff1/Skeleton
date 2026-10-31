"""Mount ultra 0048.
"""
from __future__ import annotations

ID = "mount_ultra_0048"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 48}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
