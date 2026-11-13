"""Locale pack 0027.
"""
from __future__ import annotations

PACK = "loc_0027"

def t(key: str) -> str:
    if not key:
        return ""
    return f"{PACK}:{key}"

def keys() -> list[str]:
    return ["title", "start", "options", "quit"]
