"""Named sextants."""

from __future__ import annotations

from typing import Any


class SextantPackError(ValueError):
    pass


SEXT = tuple(f"sx_{i:02d}" for i in range(8))


def shoot(state: dict[str, Any], name: str, alt: int) -> dict[str, Any]:
    if name not in SEXT:
        raise SextantPackError(name)
    nxt = dict(state)
    nxt["sextant"] = name
    nxt["alt"] = max(0, min(90, int(alt)))
    nxt["stored_prose"] = 0
    return nxt
