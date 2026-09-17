"""Named ash pans."""

from __future__ import annotations

from typing import Any


class AshpanPackError(ValueError):
    pass


PAN = tuple(f"ap_{i:02d}" for i in range(16))


def fill(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PAN:
        raise AshpanPackError(name)
    nxt = dict(node)
    nxt["ashpan"] = name
    nxt["ash"] = int(nxt.get("ash", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
