"""Shader ultimate 0196.
"""
from __future__ import annotations

ID = "shader_ultimate_0196"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 196}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
