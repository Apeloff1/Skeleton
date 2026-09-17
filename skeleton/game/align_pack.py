"""Named alignments."""

from __future__ import annotations

from typing import Any


class AlignPackError(ValueError):
    pass


ALIGN = tuple(f"al_{i:02d}" for i in range(20))


def set_align(node: dict[str, Any], name: str, off: int) -> dict[str, Any]:
    if name not in ALIGN:
        raise AlignPackError(name)
    nxt = dict(node)
    nxt["align"] = name
    nxt["off"] = int(off)
    nxt["stored_prose"] = 0
    return nxt
