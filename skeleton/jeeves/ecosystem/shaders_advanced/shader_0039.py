"""Shader scale2 0039.
"""
from __future__ import annotations

ID = "shader_scale2_0039"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 39}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
