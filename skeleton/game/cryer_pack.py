"""Named cryers."""

from __future__ import annotations

from typing import Any


class CryerPackError(ValueError):
    pass


CRYER = tuple(f"cy_{i:02d}" for i in range(8))


def cry(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CRYER:
        raise CryerPackError(name)
    nxt = dict(state)
    nxt["cryer"] = name
    nxt["heard"] = 1
    nxt["stored_prose"] = 0
    return nxt
