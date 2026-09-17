"""Named splints."""

from __future__ import annotations

from typing import Any


class SplintPackError(ValueError):
    pass


SPLINT = tuple(f"sp_{i:02d}" for i in range(16))


def set_splint(state: dict[str, Any], name: str, site: str) -> dict[str, Any]:
    if name not in SPLINT:
        raise SplintPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("splint") or {})
    cur[name] = site
    nxt["splint"] = cur
    nxt["stored_prose"] = 0
    return nxt
