"""Shader eco_prime 0213.
"""
from __future__ import annotations

ID = "shader_eco_prime_0213"

def describe() -> dict:
    return {"id": ID, "kind": "shader", "index": 213}

def activate(context: str = "") -> dict:
    return {"ok": True, "id": ID, "context": context[:100], "active": True}
