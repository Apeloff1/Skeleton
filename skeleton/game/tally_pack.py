"""Named tallies."""

from __future__ import annotations

from typing import Any


class TallyPackError(ValueError):
    pass


TALLY = tuple(f"ty_{i:02d}" for i in range(24))


def inc(state: dict[str, Any], name: str, n: int = 1) -> dict[str, Any]:
    if name not in TALLY:
        raise TallyPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("tally") or {})
    cur[name] = int(cur.get(name, 0)) + int(n)
    nxt["tally"] = cur
    nxt["stored_prose"] = 0
    return nxt
