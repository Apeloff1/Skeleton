"""Named loans."""

from __future__ import annotations

from typing import Any


class LoanPackError(ValueError):
    pass


LOAN = tuple(f"ln_{i:02d}" for i in range(24))


def out(state: dict[str, Any], name: str, who: str) -> dict[str, Any]:
    if name not in LOAN:
        raise LoanPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("loan") or {})
    cur[name] = who
    nxt["loan"] = cur
    nxt["stored_prose"] = 0
    return nxt
