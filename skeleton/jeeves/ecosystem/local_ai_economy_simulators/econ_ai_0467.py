"""Local AI Econ_Ai 0467.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "econ_ai_local_0467"

def describe() -> dict:
    return {"id": ID, "kind": "econ_ai", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 467 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 467 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (467 % 15) * 0.01, "notes": "refined"}
