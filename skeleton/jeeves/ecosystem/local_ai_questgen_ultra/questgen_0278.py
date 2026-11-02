"""Local AI Questgen ultra 0278.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "questgen_ultra_0278"

def describe() -> dict:
    return {"id": ID, "kind": "questgen", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 278 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 278 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (278 % 15) * 0.01, "notes": "refined"}
