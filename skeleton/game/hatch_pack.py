"""Named hatches."""

from __future__ import annotations

from typing import Any


class HatchPackError(ValueError):
    pass


HATCH = tuple(f"ht_{i:02d}" for i in range(20))


def open_hatch(node: dict[str, Any], state: dict[str, Any], name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if name not in HATCH:
        raise HatchPackError(name)
    d, s = dict(node), dict(state)
    need = HATCH.index(name) % 2
    if need and int(s.get("key", 0)) < 1:
        raise HatchPackError("key")
    if need:
        s["key"] = int(s.get("key", 0)) - 1
    d["hatch"] = name
    d["open"] = True
    d["stored_prose"] = 0
    s["stored_prose"] = 0
    return d, s
