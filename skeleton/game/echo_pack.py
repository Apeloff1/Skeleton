"""Named echos."""

from __future__ import annotations

from typing import Any


class EchoPackError(ValueError):
    pass


ECHO = tuple(f"ec_{i:02d}" for i in range(20))


def ring(node: dict[str, Any], name: str, t: int) -> dict[str, Any]:
    if name not in ECHO:
        raise EchoPackError(name)
    nxt = dict(node)
    nxt["echo"] = name
    nxt["loud"] = min(16, int(nxt.get("loud", 0)) + 1 + (ECHO.index(name) % 3) + (t % 2))
    nxt["stored_prose"] = 0
    return nxt
