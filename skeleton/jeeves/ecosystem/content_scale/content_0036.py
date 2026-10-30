"""Content scale 0036.
"""
from __future__ import annotations

CONTENT = "content_0036"

def describe() -> dict:
    return {"id": CONTENT, "kind": ["item", "enemy", "room", "quest"][36 % 4], "rarity": ["common", "rare", "epic"][36 % 3]}

def use(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "content": CONTENT, "target": target}
