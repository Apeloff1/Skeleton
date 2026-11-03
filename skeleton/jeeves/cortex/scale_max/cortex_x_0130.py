"""Max scattered Cortex_X 0130.
"""
from __future__ import annotations

ID = "cortex_x_max2_0130"

def describe() -> dict:
    return {"id": ID, "kind": "cortex_x", "scattered": True, "max": True}

def process(data: dict | None = None) -> dict:
    d = data or {}
    return {"ok": True, "id": ID, "processed": len(d), "score": 0.76 + (130 % 14) * 0.01}

def validate() -> dict:
    return {"ok": True, "id": ID, "valid": True}
