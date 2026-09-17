"""Named harrow tines."""

from __future__ import annotations

from typing import Any


class HarrowtinePackError(ValueError):
    pass


TINE = tuple(f"ht_{i:02d}" for i in range(16))


def set_tine(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TINE:
        raise HarrowtinePackError(name)
    nxt = dict(state)
    have = list(nxt.get("harrowtine") or [])
    have.append(name)
    nxt["harrowtine"] = have
    nxt["stored_prose"] = 0
    return nxt
