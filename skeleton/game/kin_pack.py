"""Named kin ties."""

from __future__ import annotations

from typing import Any


class KinPackError(ValueError):
    pass


KIN = tuple(f"kin_{i:02d}" for i in range(28))


def bind(state: dict[str, Any], name: str, who: str) -> dict[str, Any]:
    if name not in KIN:
        raise KinPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("kin") or {})
    cur[name] = who
    nxt["kin"] = cur
    nxt["stored_prose"] = 0
    return nxt
