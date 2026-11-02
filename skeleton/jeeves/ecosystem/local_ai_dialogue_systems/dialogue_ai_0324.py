"""Local AI Dialogue_Ai 0324.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "dialogue_ai_local_0324"

def describe() -> dict:
    return {"id": ID, "kind": "dialogue_ai", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 324 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 324 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (324 % 15) * 0.01, "notes": "refined"}
