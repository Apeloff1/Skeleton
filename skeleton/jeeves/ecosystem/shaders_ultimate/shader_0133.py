"""Shader ultimate 0133.
"""
from __future__ import annotations

ID = "shader_ultimate_0133"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 133}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
