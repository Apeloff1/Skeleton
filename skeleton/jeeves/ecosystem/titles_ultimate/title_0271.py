"""Title ultimate 0271.
"""
from __future__ import annotations

ID = "title_ultimate_0271"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 271}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
