"""GB-54 prefill. Empty slots take one token. Occupied stay. No sentence."""

from __future__ import annotations

CAP = 8


def _token(value: object) -> str:
    if not isinstance(value, str):
        return ""
    if not value or " " in value or len(value) > 32:
        return ""
    return value


def _occupied(rows: object) -> tuple[set[int], int]:
    seen: set[int] = set()
    dropped = 0
    if not isinstance(rows, list):
        return seen, 1
    for item in rows:
        if isinstance(item, bool) or not isinstance(item, int) or item < 0 or item >= CAP:
            dropped += 1
            continue
        seen.add(item)
    return seen, dropped


def prefill(occupied: object, token: object) -> dict:
    seen, dropped = _occupied(occupied)
    fill = _token(token)
    if not fill:
        return {
            "kind": "prefill",
            "ok": 0,
            "n": 0,
            "slots": [],
            "dropped": dropped + 1,
            "stored_prose": 0,
        }
    slots = [slot for slot in range(CAP) if slot not in seen]
    return {
        "kind": "prefill",
        "ok": 1,
        "n": len(slots),
        "slots": slots,
        "dropped": dropped,
        "stored_prose": 0,
    }
