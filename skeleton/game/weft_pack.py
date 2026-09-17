"""Named wefts."""

from __future__ import annotations

from typing import Any


class WeftPackError(ValueError):
    pass


WEFT = tuple(f"wf_{i:02d}" for i in range(16))


def pass_weft(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in WEFT:
        raise WeftPackError(name)
    nxt = dict(state)
    have = list(nxt.get("weft") or [])
    have.append(name)
    nxt["weft"] = have
    nxt["stored_prose"] = 0
    return nxt
