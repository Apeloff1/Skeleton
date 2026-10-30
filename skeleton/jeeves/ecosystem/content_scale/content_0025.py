"""Content scale 0025.
"""
from __future__ import annotations

CONTENT = "content_0025"

def describe() -> dict:
    return {"id": CONTENT, "kind": ["item", "enemy", "room", "quest"][25 % 4], "rarity": ["common", "rare", "epic"][25 % 3]}

def use(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "content": CONTENT, "target": target}
