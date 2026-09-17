"""Named market stalls."""

from __future__ import annotations

from typing import Any


class MarketstallPackError(ValueError):
    pass


STALL = tuple(f"ms_{i:02d}" for i in range(16))


def set_stall(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STALL:
        raise MarketstallPackError(name)
    nxt = dict(node)
    nxt["marketstall"] = name
    nxt["stored_prose"] = 0
    return nxt
