"""Named tailbands."""

from __future__ import annotations

from typing import Any


class TailbandPackError(ValueError):
    pass


TAIL = tuple(f"tb_{i:02d}" for i in range(8))


def set_tail(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TAIL:
        raise TailbandPackError(name)
    nxt = dict(state)
    nxt["tailband"] = name
    nxt["stored_prose"] = 0
    return nxt
