"""Named grommets."""

from __future__ import annotations

from typing import Any


class GrommetPackError(ValueError):
    pass


GROMMET = tuple(f"gm_{i:02d}" for i in range(16))


def set_grommet(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in GROMMET:
        raise GrommetPackError(name)
    nxt = dict(state)
    have = list(nxt.get("grommet") or [])
    have.append(name)
    nxt["grommet"] = have
    nxt["stored_prose"] = 0
    return nxt
