"""Max scattered Rt_X2 0460.
"""
from __future__ import annotations

ID = "rt_x2_max2_0460"

def describe() -> dict:
    return {"id": ID, "kind": "rt_x2", "scattered": True, "max": True}

def process(data: dict | None = None) -> dict:
    d = data or {}
    return {"ok": True, "id": ID, "processed": len(d), "score": 0.76 + (460 % 14) * 0.01}

def validate() -> dict:
    return {"ok": True, "id": ID, "valid": True}
