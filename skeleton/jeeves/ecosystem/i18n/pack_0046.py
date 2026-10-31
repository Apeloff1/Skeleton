"""Locale pack 0046.
"""
from __future__ import annotations

PACK = "loc_0046"

def t(key: str) -> str:
    if not key:
        return ""
    return f"{PACK}:{key}"

def keys() -> list[str]:
    return ["title", "start", "options", "quit"]
