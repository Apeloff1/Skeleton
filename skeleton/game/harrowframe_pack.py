"""Named harrow frames."""

from __future__ import annotations

from typing import Any


class HarrowframePackError(ValueError):
    pass


FRAME = tuple(f"hf_{i:02d}" for i in range(8))


def set_frame(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FRAME:
        raise HarrowframePackError(name)
    nxt = dict(state)
    nxt["harrowframe"] = name
    nxt["stored_prose"] = 0
    return nxt
