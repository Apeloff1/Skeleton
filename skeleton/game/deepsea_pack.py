"""Named deep-sea leads."""

from __future__ import annotations

from typing import Any


class DeepseaPackError(ValueError):
    pass


DEEP = tuple(f"ds_{i:02d}" for i in range(8))


def drop(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in DEEP:
        raise DeepseaPackError(name)
    nxt = dict(state)
    nxt["deepsea"] = name
    nxt["cast"] = int(nxt.get("cast", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
