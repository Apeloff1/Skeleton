"""Locale pack 0068.
"""
from __future__ import annotations

PACK = "loc_0068"

def t(key: str) -> str:
    if not key:
        return ""
    return f"{PACK}:{key}"

def keys() -> list[str]:
    return ["title", "start", "options", "quit"]
