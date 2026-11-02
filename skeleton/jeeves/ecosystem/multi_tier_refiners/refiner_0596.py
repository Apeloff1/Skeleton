"""Local AI Refiner 0596.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "refiner_local_0596"

def describe() -> dict:
    return {"id": ID, "kind": "refiner", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 596 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 596 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (596 % 15) * 0.01, "notes": "refined"}
