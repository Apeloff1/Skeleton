"""Local AI Bossdesign 0163.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "bossdesign_local_0163"

def describe() -> dict:
    return {"id": ID, "kind": "bossdesign", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 163 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 163 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (163 % 15) * 0.01, "notes": "refined"}
