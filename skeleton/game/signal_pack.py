"""Named signals."""

from __future__ import annotations

from typing import Any


class SignalPackError(ValueError):
    pass


SIGNAL = tuple(f"sg_{i:02d}" for i in range(24))


def set_aspect(node: dict[str, Any], name: str, aspect: int) -> dict[str, Any]:
    if name not in SIGNAL:
        raise SignalPackError(name)
    nxt = dict(node)
    nxt["signal"] = name
    nxt["aspect"] = max(0, min(2, int(aspect)))
    nxt["stored_prose"] = 0
    return nxt
