"""Named hides."""

from __future__ import annotations

from typing import Any


class HideacrePackError(ValueError):
    pass


HIDE = tuple(f"hd_{i:02d}" for i in range(12))


def set_hide(state: dict[str, Any], name: str, n: int) -> dict[str, Any]:
    if name not in HIDE:
        raise HideacrePackError(name)
    nxt = dict(state)
    nxt["hideacre"] = name
    nxt["hide"] = max(0, int(n))
    nxt["stored_prose"] = 0
    return nxt
