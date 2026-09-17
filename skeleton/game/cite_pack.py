"""Named citations."""

from __future__ import annotations

from typing import Any


class CitePackError(ValueError):
    pass


CITE = tuple(f"ci_{i:02d}" for i in range(20))


def write(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CITE:
        raise CitePackError(name)
    nxt = dict(state)
    have = list(nxt.get("cite") or [])
    have.append(name)
    nxt["cite"] = have
    nxt["alert"] = int(nxt.get("alert", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
