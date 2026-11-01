"""Title ultra_max 0245.
"""
from __future__ import annotations

ID = "title_ultra_max_0245"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 245}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
