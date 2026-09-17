"""Named scuttles."""

from __future__ import annotations

from typing import Any


class ScuttlePackError(ValueError):
    pass


SCUTTLE = tuple(f"sc_{i:02d}" for i in range(12))


def set_scuttle(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SCUTTLE:
        raise ScuttlePackError(name)
    nxt = dict(node)
    nxt["scuttle"] = name
    nxt["stored_prose"] = 0
    return nxt
