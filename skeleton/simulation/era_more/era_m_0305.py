"""More scattered Era_M 0305.
"""
from __future__ import annotations

ID = "era_m_more2_0305"

def describe() -> dict:
    return {"id": ID, "kind": "era_m", "scattered": True, "more": True}

def process(data: dict | None = None) -> dict:
    d = data or {}
    return {"ok": True, "id": ID, "processed": len(d), "score": 0.75 + (305 % 16) * 0.01}

def validate() -> dict:
    return {"ok": True, "id": ID, "valid": True}
