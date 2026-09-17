"""Named pleachers."""

from __future__ import annotations

from typing import Any


class PleachPackError(ValueError):
    pass


PLEACH = tuple(f"pl_{i:02d}" for i in range(16))


def lay(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PLEACH:
        raise PleachPackError(name)
    nxt = dict(state)
    have = list(nxt.get("pleach") or [])
    have.append(name)
    nxt["pleach"] = have
    nxt["stored_prose"] = 0
    return nxt
