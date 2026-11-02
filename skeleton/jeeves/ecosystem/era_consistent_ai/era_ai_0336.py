"""Local AI Era_Ai 0336.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "era_ai_local_0336"

def describe() -> dict:
    return {"id": ID, "kind": "era_ai", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 336 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 336 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (336 % 15) * 0.01, "notes": "refined"}
