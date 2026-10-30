"""Content scale 0197.
"""
from __future__ import annotations

CONTENT = "content_0197"

def describe() -> dict:
    return {"id": CONTENT, "kind": ["item", "enemy", "room", "quest"][197 % 4], "rarity": ["common", "rare", "epic"][197 % 3]}

def use(target: str) -> dict:
    if not target:
        return {"ok": False, "reason": "no_target"}
    return {"ok": True, "content": CONTENT, "target": target}
