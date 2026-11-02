"""Local AI Econ_Ai ultra 0500.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "econ_ai_ultra_0500"

def describe() -> dict:
    return {"id": ID, "kind": "econ_ai", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 500 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 500 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (500 % 15) * 0.01, "notes": "refined"}
