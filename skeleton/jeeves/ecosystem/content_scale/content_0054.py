"""Content scale 0054.
"""
from __future__ import annotations

CONTENT = "content_0054"

def describe() -> dict:
    return {"id": CONTENT, "kind": ["item", "enemy", "room", "quest"][54 % 4], "rarity": ["common", "rare", "epic"][54 % 3]}

def use(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "content": CONTENT, "target": target}
