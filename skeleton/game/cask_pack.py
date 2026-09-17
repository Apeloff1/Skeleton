"""Named casks."""

from __future__ import annotations

from typing import Any


class CaskPackError(ValueError):
    pass


CASK = tuple(f"ck_{i:02d}" for i in range(16))


def fill(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CASK:
        raise CaskPackError(name)
    if int(state.get("must", 0)) < 1:
        raise CaskPackError("must")
    nxt = dict(state)
    nxt["must"] = int(nxt.get("must", 0)) - 1
    have = list(nxt.get("cask") or [])
    have.append(name)
    nxt["cask"] = have
    nxt["stored_prose"] = 0
    return nxt
