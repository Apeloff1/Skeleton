"""Far scattered Rt_F2 0270.
"""
from __future__ import annotations

ID = "rt_f2_far2_0270"

def describe() -> dict:
    return {"id": ID, "kind": "rt_f2", "scattered": True, "far": True}

def process(data: dict | None = None) -> dict:
    d = data or {}
    return {"ok": True, "id": ID, "processed": len(d), "score": 0.74 + (270 % 18) * 0.01}

def validate() -> dict:
    return {"ok": True, "id": ID, "valid": True}
