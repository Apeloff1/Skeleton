"""Mount mega 0010.
"""
from __future__ import annotations

ID = "mount_mega_0010"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 10}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
