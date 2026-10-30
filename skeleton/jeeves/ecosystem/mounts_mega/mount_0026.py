"""Mount mega 0026.
"""
from __future__ import annotations

ID = "mount_mega_0026"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 26}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
