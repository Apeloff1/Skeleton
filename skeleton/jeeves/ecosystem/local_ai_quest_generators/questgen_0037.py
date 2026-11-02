"""Local AI Questgen 0037.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "questgen_local_0037"

def describe() -> dict:
    return {"id": ID, "kind": "questgen", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 37 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 37 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (37 % 15) * 0.01, "notes": "refined"}
