"""Named azimuths."""

from __future__ import annotations

from typing import Any


class AzimuthPackError(ValueError):
    pass


AZ = tuple(f"az_{i:02d}" for i in range(12))


def set_az(state: dict[str, Any], name: str, deg: int) -> dict[str, Any]:
    if name not in AZ:
        raise AzimuthPackError(name)
    nxt = dict(state)
    nxt["azimuth"] = name
    nxt["deg"] = int(deg) % 360
    nxt["stored_prose"] = 0
    return nxt
