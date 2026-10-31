"""Shader prime 0113.
"""
from __future__ import annotations

ID = "shader_prime_0113"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 113}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
