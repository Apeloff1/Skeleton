"""Shader mega 0001.
"""
from __future__ import annotations

ID = "shader_mega_0001"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 1}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
