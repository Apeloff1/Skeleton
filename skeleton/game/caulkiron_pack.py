"""Named caulking irons."""

from __future__ import annotations

from typing import Any


class CaulkironPackError(ValueError):
    pass


IRON = tuple(f"ci_{i:02d}" for i in range(12))


def drive(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in IRON:
        raise CaulkironPackError(name)
    nxt = dict(state)
    nxt["caulkiron"] = name
    nxt["driven"] = int(nxt.get("driven", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
