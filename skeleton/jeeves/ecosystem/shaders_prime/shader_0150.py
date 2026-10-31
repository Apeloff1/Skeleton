"""Shader prime 0150.
"""
from __future__ import annotations

ID = "shader_prime_0150"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 150}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
