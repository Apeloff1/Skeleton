"""Named pontils."""

from __future__ import annotations

from typing import Any


class PontilPackError(ValueError):
    pass


PONTIL = tuple(f"pt_{i:02d}" for i in range(12))


def snap(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PONTIL:
        raise PontilPackError(name)
    nxt = dict(state)
    nxt["pontil"] = name
    nxt["scrap"] = int(nxt.get("scrap", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
