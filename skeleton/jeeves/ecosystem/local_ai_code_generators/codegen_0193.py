"""Local AI Codegen 0193.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "codegen_local_0193"

def describe() -> dict:
    return {"id": ID, "kind": "codegen", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 193 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 193 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (193 % 15) * 0.01, "notes": "refined"}
