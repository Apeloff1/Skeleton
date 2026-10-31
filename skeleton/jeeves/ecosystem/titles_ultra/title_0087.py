"""Title ultra 0087.
"""
from __future__ import annotations

ID = "title_ultra_0087"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 87}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
