"""Shader mega 0028.
"""
from __future__ import annotations

ID = "shader_mega_0028"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 28}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
