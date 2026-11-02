"""Shader eco_supreme 0200.
"""
from __future__ import annotations

ID = "shader_eco_supreme_0200"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 200}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
