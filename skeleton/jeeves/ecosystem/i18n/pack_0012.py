"""Locale pack 0012.
"""
from __future__ import annotations

PACK = "loc_0012"

def t(key: str) -> str:
    if not key:
        return ""
    return f"{PACK}:{key}"

def keys() -> list[str]:
    return ["title", "start", "options", "quit"]
