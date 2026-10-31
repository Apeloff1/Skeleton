"""Shader ultra 0012.
"""
from __future__ import annotations

ID = "shader_ultra_0012"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 12}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
