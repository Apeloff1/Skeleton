"""More scattered Rt_M2 0404.
"""
from __future__ import annotations

ID = "rt_m2_more2_0404"

def describe() -> dict:
    return {"id": ID, "kind": "rt_m2", "scattered": True, "more": True}

def process(data: dict | None = None) -> dict:
    d = data or {}
    return {"ok": True, "id": ID, "processed": len(d), "score": 0.75 + (404 % 16) * 0.01}

def validate() -> dict:
    return {"ok": True, "id": ID, "valid": True}
