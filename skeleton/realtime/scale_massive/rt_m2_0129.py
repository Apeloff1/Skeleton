"""Massive scattered Rt_M2 0129.
"""
from __future__ import annotations

ID = "rt_m2_massive2_0129"

def describe() -> dict:
    return {"id": ID, "kind": "rt_m2", "scattered": True, "massive": True}

def process(data: dict | None = None) -> dict:
    d = data or {}
    return {"ok": True, "id": ID, "processed": len(d), "score": 0.72 + (129 % 20) * 0.01}

def validate() -> dict:
    return {"ok": True, "id": ID, "valid": True}
