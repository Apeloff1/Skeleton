"""Memory 0025.
"""
from __future__ import annotations

MEM = "mem_0025"

def store(key: str, value: str) -> dict:
    if not key:
        return {"ok": False, "reason": "no_key"}
    return {"ok": True, "mem": MEM, "key": key, "value": value[:120]}

def recall(key: str) -> dict:
    return {"ok": True, "mem": MEM, "key": key, "found": bool(key)}
