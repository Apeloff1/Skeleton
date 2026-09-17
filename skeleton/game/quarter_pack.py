"""Named quarters."""

from __future__ import annotations

from typing import Any


class QuarterPackError(ValueError):
    pass


QR = tuple(f"qr_{i:02d}" for i in range(8))


def weigh(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in QR:
        raise QuarterPackError(name)
    nxt = dict(state)
    nxt["quarter"] = name
    nxt["qr"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
