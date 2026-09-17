"""Named log chips."""

from __future__ import annotations

from typing import Any


class LogchipPackError(ValueError):
    pass


LOG = tuple(f"lg_{i:02d}" for i in range(12))


def heave(state: dict[str, Any], name: str, kn: int) -> dict[str, Any]:
    if name not in LOG:
        raise LogchipPackError(name)
    nxt = dict(state)
    nxt["logchip"] = name
    nxt["kn"] = max(0, int(kn))
    nxt["stored_prose"] = 0
    return nxt
