"""Named churns."""

from __future__ import annotations

from typing import Any


class ChurnPackError(ValueError):
    pass


CHURN = tuple(f"cn_{i:02d}" for i in range(12))


def beat(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CHURN:
        raise ChurnPackError(name)
    nxt = dict(state)
    nxt["churn"] = name
    nxt["butter"] = int(nxt.get("butter", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
