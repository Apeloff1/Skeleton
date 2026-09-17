"""Named wickets."""

from __future__ import annotations

from typing import Any


class WicketPackError(ValueError):
    pass


WICKET = tuple(f"wk_{i:02d}" for i in range(8))


def set_wicket(node: dict[str, Any], name: str, open_: int) -> dict[str, Any]:
    if name not in WICKET:
        raise WicketPackError(name)
    nxt = dict(node)
    nxt["wicket"] = name
    nxt["open"] = int(bool(open_))
    nxt["stored_prose"] = 0
    return nxt
