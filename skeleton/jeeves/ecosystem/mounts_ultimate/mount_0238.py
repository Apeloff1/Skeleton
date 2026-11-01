"""Mount ultimate 0238.
"""
from __future__ import annotations

ID = "mount_ultimate_0238"

def describe() -> dict:
    return {"id": ID, "kind": "mount", "index": 238}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
