"""Shader prime 0187.
"""
from __future__ import annotations

ID = "shader_prime_0187"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 187}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
