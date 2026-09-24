"""GB-57 walk. Stage names must follow the kernel order. No sentence."""

from __future__ import annotations

_ORDER = (
    "admit",
    "quota",
    "place",
    "prefill",
    "decode",
    "check",
    "stock",
    "reclaim",
)
_ALLOWED = set(_ORDER)


def walk(steps: object) -> dict:
    taken: list[str] = []
    dropped = 0
    if not isinstance(steps, list):
        dropped = 1
    else:
        for item in steps:
            if not isinstance(item, str) or item not in _ALLOWED:
                dropped += 1
                continue
            taken.append(item)
    ordered = bool(taken) and tuple(taken) == _ORDER[: len(taken)]
    ok = 1 if ordered and dropped == 0 else 0
    return {
        "kind": "walk",
        "ok": ok,
        "n": len(taken) if ok else 0,
        "steps": list(taken) if ok else [],
        "dropped": dropped,
        "stored_prose": 0,
    }
