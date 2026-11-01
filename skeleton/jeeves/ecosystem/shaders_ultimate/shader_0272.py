"""Shader ultimate 0272.
"""
from __future__ import annotations

ID = "shader_ultimate_0272"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 272}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
