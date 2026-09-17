"""Named yoke beams."""

from __future__ import annotations

from typing import Any


class YokebeamPackError(ValueError):
    pass


BEAM = tuple(f"yb_{i:02d}" for i in range(8))


def set_beam(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BEAM:
        raise YokebeamPackError(name)
    nxt = dict(state)
    nxt["yokebeam"] = name
    nxt["stored_prose"] = 0
    return nxt
