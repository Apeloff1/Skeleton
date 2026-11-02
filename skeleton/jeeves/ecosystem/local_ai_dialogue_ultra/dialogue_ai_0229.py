"""Local AI Dialogue_Ai ultra 0229.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "dialogue_ai_ultra_0229"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue_ai", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 229 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 229 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (229 % 15) * 0.01, "notes": "refined"}
