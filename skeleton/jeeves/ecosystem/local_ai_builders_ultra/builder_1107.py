"""Local AI Builder ultra 1107.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "builder_ultra_1107"

def describe() -> dict:
    return {"id": ID, "kind": "builder", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 1107 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 1107 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (1107 % 15) * 0.01, "notes": "refined"}
