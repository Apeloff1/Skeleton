"""Named skim coats."""

from __future__ import annotations

from typing import Any


class SkimPackError(ValueError):
    pass


SKIM = tuple(f"sm_{i:02d}" for i in range(12))


def finish(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SKIM:
        raise SkimPackError(name)
    nxt = dict(node)
    nxt["skim"] = name
    nxt["coat"] = int(nxt.get("coat", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
