"""Shader scale2 0018.
"""
from __future__ import annotations

ID = "shader_scale2_0018"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 18}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
