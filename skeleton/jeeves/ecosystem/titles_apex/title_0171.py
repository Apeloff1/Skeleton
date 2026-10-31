"""Title apex 0171.
"""
from __future__ import annotations

ID = "title_apex_0171"

def describe() -> dict:
    return {"id": ID, "kind": "title", "index": 171}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
