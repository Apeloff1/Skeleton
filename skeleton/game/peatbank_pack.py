"""Named peat banks."""

from __future__ import annotations

from typing import Any


class PeatbankPackError(ValueError):
    pass


BANK = tuple(f"pb_{i:02d}" for i in range(8))


def set_bank(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BANK:
        raise PeatbankPackError(name)
    nxt = dict(node)
    nxt["peatbank"] = name
    nxt["stored_prose"] = 0
    return nxt
