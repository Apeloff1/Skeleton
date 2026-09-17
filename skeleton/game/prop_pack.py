"""Named props."""

from __future__ import annotations

from typing import Any


class PropPackError(ValueError):
    pass


PROP = tuple(f"pr_{i:02d}" for i in range(16))


def set_prop(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PROP:
        raise PropPackError(name)
    nxt = dict(state)
    have = list(nxt.get("prop") or [])
    have.append(name)
    nxt["prop"] = have
    nxt["stored_prose"] = 0
    return nxt
