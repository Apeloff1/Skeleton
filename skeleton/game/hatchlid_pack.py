"""Named hatch lids."""

from __future__ import annotations

from typing import Any


class HatchlidPackError(ValueError):
    pass


LID = tuple(f"hl_{i:02d}" for i in range(12))


def set_lid(node: dict[str, Any], name: str, open_: int) -> dict[str, Any]:
    if name not in LID:
        raise HatchlidPackError(name)
    nxt = dict(node)
    nxt["hatchlid"] = name
    nxt["open"] = int(bool(open_))
    nxt["stored_prose"] = 0
    return nxt
