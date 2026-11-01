"""Title ultimate 0298.
"""
from __future__ import annotations

ID = "title_ultimate_0298"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 298}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
