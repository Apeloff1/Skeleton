"""Mount mega 0020.
"""
from __future__ import annotations

ID = "mount_mega_0020"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 20}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
