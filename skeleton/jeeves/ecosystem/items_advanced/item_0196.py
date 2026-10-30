"""Item advanced 0196.
"""
from __future__ import annotations

ID = "item_adv_0196"

def describe() -> dict:
    return {"id": ID, "kind": "item", "index": 196}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
