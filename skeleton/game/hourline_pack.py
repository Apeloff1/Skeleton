"""Named hour lines."""

from __future__ import annotations

from typing import Any


class HourlinePackError(ValueError):
    pass


HOUR = tuple(f"hr_{i:02d}" for i in range(12))


def mark(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HOUR:
        raise HourlinePackError(name)
    nxt = dict(node)
    have = list(nxt.get("hourline") or [])
    have.append(name)
    nxt["hourline"] = have
    nxt["stored_prose"] = 0
    return nxt
