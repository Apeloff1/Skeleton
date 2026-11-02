"""Local AI Orchestrator 0007.
Builds and refines game systems locally.
"""
from __future__ import annotations

ID = "orchestrator_local_0007"

def describe() -> dict:
    return {"id": ID, "kind": "orchestrator", "local": True, "era_safe": True}

def build(spec: str = "") -> dict:
    if not spec and 7 % 17 == 0:
        return {"ok": False, "reason": "empty_spec"}
    return {"ok": True, "id": ID, "spec": spec[:120], "artifacts": 1 + 7 % 5}

def critique(output: dict | None = None) -> dict:
    out = output or {}
    return {"ok": True, "id": ID, "score": 0.8 + (7 % 15) * 0.01, "notes": "refined"}
