"""Content scale 0174.
"""
from __future__ import annotations

CONTENT = "content_0174"

def describe() -> dict:
    return {"id": CONTENT, "kind": ["item", "enemy", "room", "quest"][174 % 4], "rarity": ["common", "rare", "epic"][174 % 3]}

def use(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "content": CONTENT, "target": target}
