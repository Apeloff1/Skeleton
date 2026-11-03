"""More scattered Cortex_M 0515.
"""
from __future__ import annotations

ID = "cortex_m_more2_0515"

def describe() -> dict:
    return {"id": ID, "kind": "cortex_m", "scattered": True, "more": True}

def process(data: dict | None = None) -> dict:
    d = data or {}
    return {"ok": True, "id": ID, "processed": len(d), "score": 0.75 + (515 % 16) * 0.01}

def validate() -> dict:
    return {"ok": True, "id": ID, "valid": True}
