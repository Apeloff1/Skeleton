"""Named selvedges."""

from __future__ import annotations

from typing import Any


class SelvedgePackError(ValueError):
    pass


SELV = tuple(f"sv_{i:02d}" for i in range(8))


def set_selv(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SELV:
        raise SelvedgePackError(name)
    nxt = dict(state)
    nxt["selvedge"] = name
    nxt["stored_prose"] = 0
    return nxt
