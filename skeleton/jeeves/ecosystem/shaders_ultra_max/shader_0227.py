"""Shader ultra_max 0227.
"""
from __future__ import annotations

ID = "shader_ultra_max_0227"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 227}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
