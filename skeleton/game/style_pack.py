"""Named styles."""

from __future__ import annotations

from typing import Any


class StylePackError(ValueError):
    pass


STYLE = tuple(f"st_{i:02d}" for i in range(8))


def set_style(node: dict[str, Any], name: str, deg: int) -> dict[str, Any]:
    if name not in STYLE:
        raise StylePackError(name)
    nxt = dict(node)
    nxt["style"] = name
    nxt["deg"] = max(0, min(90, int(deg)))
    nxt["stored_prose"] = 0
    return nxt
