"""Local AI Refiner ultra 0584.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "refiner_ultra_0584"

def describe() -> dict:
    return {"id": ID, "kind": "refiner", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 584 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 584 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (584 % 15) * 0.01, "notes": "refined"}
