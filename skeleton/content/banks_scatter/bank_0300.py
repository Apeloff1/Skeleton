"""Scattered Bank 0300.
"""
from __future__ import annotations

ID = "bank_scatter2_0300"

def describe() -> dict:
    return {"id": ID, "kind": "bank", "scattered": True}

def process(data: dict | None = None) -> dict:
    d = data or {}
    return {"ok": True, "id": ID, "processed": len(d), "score": 0.7 + (300 % 20) * 0.01}

def validate() -> dict:
    return {"ok": True, "id": ID, "valid": True}
