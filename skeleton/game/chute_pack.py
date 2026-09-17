"""Named chutes."""

from __future__ import annotations

from typing import Any


class ChutePackError(ValueError):
    pass


CHUTE = tuple(f"ct_{i:02d}" for i in range(20))


def send(node: dict[str, Any], name: str, dest: str) -> dict[str, Any]:
    if name not in CHUTE:
        raise ChutePackError(name)
    nxt = dict(node)
    nxt["chute"] = name
    nxt["dest"] = dest
    nxt["stored_prose"] = 0
    return nxt
