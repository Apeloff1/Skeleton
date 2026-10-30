"""Mount mega 0001.
"""
from __future__ import annotations

ID = "mount_mega_0001"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 1}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
