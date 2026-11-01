"""Shader ultra_max 0230.
"""
from __future__ import annotations

ID = "shader_ultra_max_0230"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 230}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
