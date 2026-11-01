"""Shader ultra_max 0174.
"""
from __future__ import annotations

ID = "shader_ultra_max_0174"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 174}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
