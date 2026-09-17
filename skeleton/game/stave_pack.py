"""Named staves."""

from __future__ import annotations

from typing import Any


class StavePackError(ValueError):
    pass


STAVE = tuple(f"sv_{i:02d}" for i in range(16))


def set_stave(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STAVE:
        raise StavePackError(name)
    nxt = dict(state)
    have = list(nxt.get("stave") or [])
    have.append(name)
    nxt["stave"] = have
    nxt["stored_prose"] = 0
    return nxt
