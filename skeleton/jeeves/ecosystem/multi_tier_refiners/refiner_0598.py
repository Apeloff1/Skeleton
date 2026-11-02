"""Local AI Refiner 0598.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "refiner_local_0598"

def describe() -> dict:
    return {"id": ID, "kind": "refiner", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 598 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 598 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (598 % 15) * 0.01, "notes": "refined"}
