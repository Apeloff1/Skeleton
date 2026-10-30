"""Shader advanced 0060.
"""
from __future__ import annotations

ID = "shader_adv_0060"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 60}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
