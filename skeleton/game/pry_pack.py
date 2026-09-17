"""Named pry points."""

from __future__ import annotations

from typing import Any


class PryPackError(ValueError):
    pass


PRY = tuple(f"pr_{i:02d}" for i in range(16))


def use(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PRY:
        raise PryPackError(name)
    nxt = dict(state)
    if "pick" not in list(nxt.get("tools") or []):
        raise PryPackError("tool")
    nxt["pried"] = name
    nxt["stored_prose"] = 0
    return nxt
