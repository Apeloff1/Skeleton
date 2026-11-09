"""GB-56 reclaim. Free a held slot. Unheld or bad asks drop. No sentence."""

from __future__ import annotations

CAP = 8


def _scan(rows: object) -> tuple[set[int], int, int]:
    seen: set[int] = set()
    dropped = 0
    collision = 0
    if not isinstance(rows, list):
        return seen, 1, 0
    for item in rows:
        if isinstance(item, bool) or not isinstance(item, int) or item < 0 or item >= CAP:
            dropped += 1
            continue
        if item in seen:
            collision += 1
            continue
        seen.add(item)
    return seen, dropped, collision


def reclaim(held: object, ask: object) -> dict:
    have, drop_held, hit_held = _scan(held)
    want, drop_ask, hit_ask = _scan(ask)
    freed = sorted(slot for slot in want if slot in have)
    remain = sorted(have - set(freed))
    missed = len(want - have)
    return {
        "kind": "reclaim",
        "ok": 1 if freed else 0,
        "n": len(freed),
        "slots": freed,
        "remain": remain,
        "missed": missed,
        "collision": hit_held + hit_ask,
        "dropped": drop_held + drop_ask,
        "stored_prose": 0,
    }
