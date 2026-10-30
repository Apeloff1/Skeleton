"""Shader mega 0013.
"""
from __future__ import annotations

ID = "shader_mega_0013"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 13}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
