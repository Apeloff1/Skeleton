"""Local AI Codegen 0041.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "codegen_local_0041"

def describe() -> dict:
    return {"id": ID, "kind": "codegen", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 41 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 41 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (41 % 15) * 0.01, "notes": "refined"}
