"""GB-53 stock. Unique slots. Cap 8. Collision drops. No sentence."""

from __future__ import annotations

CAP = 8


def _slot(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0 or value >= CAP:
        return None
    return value


def _token(value: object) -> str:
    if not isinstance(value, str):
        return ""
    if not value or " " in value or len(value) > 32:
        return ""
    return value


def stock(rows: list) -> dict:
    seen: dict[int, str] = {}
    collision = 0
    dropped = 0
    for row in rows:
        if not isinstance(row, dict):
            dropped += 1
            continue
        slot = _slot(row.get("slot"))
        token = _token(row.get("token"))
        if slot is None or not token:
            dropped += 1
            continue
        if slot in seen:
            collision += 1
            continue
        seen[slot] = token
    return {
        "kind": "stock",
        "n": len(seen),
        "slots": sorted(seen),
        "collision": collision,
        "dropped": dropped,
        "stored_prose": 0,
    }
