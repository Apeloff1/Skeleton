"""Shader scale2 0063.
"""
from __future__ import annotations

ID = "shader_scale2_0063"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 63}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
