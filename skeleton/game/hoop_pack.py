"""Named hoops."""

from __future__ import annotations

from typing import Any


class HoopPackError(ValueError):
    pass


HOOP = tuple(f"hp_{i:02d}" for i in range(16))


def set_hoop(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HOOP:
        raise HoopPackError(name)
    nxt = dict(state)
    have = list(nxt.get("hoop") or [])
    have.append(name)
    nxt["hoop"] = have
    nxt["stored_prose"] = 0
    return nxt
