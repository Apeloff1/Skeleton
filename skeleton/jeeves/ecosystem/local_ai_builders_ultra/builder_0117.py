"""Local AI Builder ultra 0117.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "builder_ultra_0117"

def describe() -> dict:
    return {"id": ID, "kind": "builder", "local": True, "era_safe": True, "ultra": True}

def build(spec: str = "") -> dict:
    if not spec and 117 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 117 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.82 + (117 % 15) * 0.01, "notes": "refined"}
