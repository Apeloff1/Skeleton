"""Named fillets."""

from __future__ import annotations

from typing import Any


class FilletPackError(ValueError):
    pass


FILLET = tuple(f"fi_{i:02d}" for i in range(8))


def roll(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FILLET:
        raise FilletPackError(name)
    nxt = dict(state)
    nxt["fillet"] = name
    nxt["line"] = 1
    nxt["stored_prose"] = 0
    return nxt
