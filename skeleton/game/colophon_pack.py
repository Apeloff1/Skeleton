"""Named colophons."""

from __future__ import annotations

from typing import Any


class ColophonPackError(ValueError):
    pass


COLOPHON = tuple(f"co_{i:02d}" for i in range(8))


def close(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in COLOPHON:
        raise ColophonPackError(name)
    nxt = dict(state)
    nxt["colophon"] = name
    nxt["closed"] = 1
    nxt["stored_prose"] = 0
    return nxt
