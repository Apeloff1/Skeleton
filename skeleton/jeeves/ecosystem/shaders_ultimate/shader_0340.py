"""Shader ultimate 0340.
"""
from __future__ import annotations

ID = "shader_ultimate_0340"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 340}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
