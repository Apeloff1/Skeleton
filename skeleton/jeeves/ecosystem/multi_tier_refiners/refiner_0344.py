"""Local AI Refiner 0344.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "refiner_local_0344"

def describe() -> dict:
    return {"id": ID, "kind": "refiner", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 344 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 344 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (344 % 15) * 0.01, "notes": "refined"}
