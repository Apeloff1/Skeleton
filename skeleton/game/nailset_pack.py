"""Named nail sets."""

from __future__ import annotations

from typing import Any


class NailsetPackError(ValueError):
    pass


NAIL = tuple(f"ns_{i:02d}" for i in range(16))


def drive(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in NAIL:
        raise NailsetPackError(name)
    nxt = dict(state)
    have = list(nxt.get("nailset") or [])
    have.append(name)
    nxt["nailset"] = have
    nxt["stored_prose"] = 0
    return nxt
