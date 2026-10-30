"""Shader scale2 0020.
"""
from __future__ import annotations

ID = "shader_scale2_0020"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 20}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
