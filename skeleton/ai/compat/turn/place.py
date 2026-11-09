"""GB-52 place. One token, one slot. Cap 8. No sentence."""

from __future__ import annotations

CAP = 8


def place(slot: object, token: object) -> dict:
    ok_slot = isinstance(slot, int) and not isinstance(slot, bool) and 0 <= slot < CAP
    ok_token = isinstance(token, str) and bool(token) and " " not in token and len(token) <= 32
    ok = 1 if ok_slot and ok_token else 0
    return {
        "kind": "place",
        "ok": ok,
        "slot": slot if ok else -1,
        "token": token if ok else "",
        "cap": CAP,
        "stored_prose": 0,
    }
