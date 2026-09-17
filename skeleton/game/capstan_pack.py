"""Named capstans."""

from __future__ import annotations

from typing import Any


class CapstanPackError(ValueError):
    pass


CAPSTAN = tuple(f"cp_{i:02d}" for i in range(8))


def heave(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CAPSTAN:
        raise CapstanPackError(name)
    nxt = dict(state)
    nxt["capstan"] = name
    nxt["turns"] = int(nxt.get("turns", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
