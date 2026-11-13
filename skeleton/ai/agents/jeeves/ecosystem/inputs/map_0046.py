"""Input map 0046.
"""
from __future__ import annotations

MAP = "input_0046"

def bind(action: str, key: str) -> dict:
    if not action or not key:
        return {"ok": False, "reason": "incomplete"}
    return {"ok": True, "map": MAP, "action": action, "key": key}

def defaults() -> dict:
    return {"move": "wasd", "jump": "space", "interact": "e"}
