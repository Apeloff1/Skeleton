"""Shader scale2 0041.
"""
from __future__ import annotations

ID = "shader_scale2_0041"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 41}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
