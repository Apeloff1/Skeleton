"""Shader scale2 0005.
"""
from __future__ import annotations

ID = "shader_scale2_0005"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 5}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
