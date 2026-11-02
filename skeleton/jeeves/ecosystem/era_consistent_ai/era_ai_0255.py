"""Local AI Era_Ai 0255.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "era_ai_local_0255"

def describe() -> dict:
    return {"id": ID, "kind": "era_ai", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 255 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 255 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (255 % 15) * 0.01, "notes": "refined"}
