"""Named wards."""

from __future__ import annotations

from typing import Any


class WardPackError(ValueError):
    pass


WARD = tuple(f"wd_{i:02d}" for i in range(12))


def set_ward(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in WARD:
        raise WardPackError(name)
    nxt = dict(state)
    have = list(nxt.get("ward") or [])
    have.append(name)
    nxt["ward"] = have
    nxt["stored_prose"] = 0
    return nxt
