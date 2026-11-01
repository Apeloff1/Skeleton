"""Title ultimate 0293.
"""
from __future__ import annotations

ID = "title_ultimate_0293"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 293}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
