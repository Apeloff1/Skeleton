"""Named hoof picks."""

from __future__ import annotations

from typing import Any


class HoofpickPackError(ValueError):
    pass


PICK = tuple(f"hp_{i:02d}" for i in range(12))


def clean(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PICK:
        raise HoofpickPackError(name)
    nxt = dict(state)
    nxt["hoofpick"] = name
    nxt["clean"] = 1
    nxt["stored_prose"] = 0
    return nxt
