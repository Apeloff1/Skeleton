"""Named doses."""

from __future__ import annotations

from typing import Any


class DosePackError(ValueError):
    pass


DOSE = tuple(f"ds_{i:02d}" for i in range(16))


def give(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in DOSE:
        raise DosePackError(name)
    nxt = dict(state)
    nxt["dose"] = name
    nxt["sleep"] = min(16, int(nxt.get("sleep", 0)) + 1)
    nxt["stored_prose"] = 0
    return nxt
