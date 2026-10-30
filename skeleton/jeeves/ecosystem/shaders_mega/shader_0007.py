"""Shader mega 0007.
"""
from __future__ import annotations

ID = "shader_mega_0007"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 7}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
