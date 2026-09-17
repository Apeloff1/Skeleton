"""Named saggars."""

from __future__ import annotations

from typing import Any


class SaggarPackError(ValueError):
    pass


SAGGAR = tuple(f"sg_{i:02d}" for i in range(12))


def set_saggar(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SAGGAR:
        raise SaggarPackError(name)
    nxt = dict(state)
    nxt["saggar"] = name
    nxt["stored_prose"] = 0
    return nxt
