"""Named yoke staples."""

from __future__ import annotations

from typing import Any


class YokestaplePackError(ValueError):
    pass


STAPLE = tuple(f"ys_{i:02d}" for i in range(12))


def set_staple(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STAPLE:
        raise YokestaplePackError(name)
    nxt = dict(state)
    nxt["yokestaple"] = name
    nxt["stored_prose"] = 0
    return nxt
