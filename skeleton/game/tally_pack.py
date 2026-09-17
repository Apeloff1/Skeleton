"""Named tallies."""

from __future__ import annotations

from typing import Any


class TallyPackError(ValueError):
    pass


TALLY = tuple(f"ty_{i:02d}" for i in range(12))


def notch(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TALLY:
        raise TallyPackError(name)
    nxt = dict(state)
    nxt["tally"] = name
    nxt["notch"] = int(nxt.get("notch", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
