"""Shader ultra 0060.
"""
from __future__ import annotations

ID = "shader_ultra_0060"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 60}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
