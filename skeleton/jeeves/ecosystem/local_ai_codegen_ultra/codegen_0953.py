"""Local AI Codegen ultra 0953.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "codegen_ultra_0953"

def describe() -> dict:
    return {"id": ID, "kind": "codegen", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 953 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 953 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (953 % 15) * 0.01, "notes": "refined"}
