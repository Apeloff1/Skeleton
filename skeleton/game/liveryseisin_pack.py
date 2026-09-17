"""Named liveries of seisin."""

from __future__ import annotations

from typing import Any


class LiveryseisinPackError(ValueError):
    pass


LIVERY = tuple(f"lv_{i:02d}" for i in range(8))


def deliver(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in LIVERY:
        raise LiveryseisinPackError(name)
    nxt = dict(state)
    nxt["liveryseisin"] = name
    nxt["seised"] = 1
    nxt["stored_prose"] = 0
    return nxt
