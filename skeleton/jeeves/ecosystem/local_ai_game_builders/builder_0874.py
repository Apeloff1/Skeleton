"""Local AI Builder 0874.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "builder_local_0874"

def describe() -> dict:
    return {"id": ID, "kind": "builder", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 874 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 874 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (874 % 15) * 0.01, "notes": "refined"}
