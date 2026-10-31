"""Shader ultra 0093.
"""
from __future__ import annotations

ID = "shader_ultra_0093"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 93}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
