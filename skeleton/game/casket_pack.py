"""Named caskets."""

from __future__ import annotations

from typing import Any


class CasketPackError(ValueError):
    pass


CASKET = tuple(f"ck_{i:02d}" for i in range(8))


def set_casket(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CASKET:
        raise CasketPackError(name)
    nxt = dict(node)
    nxt["casket"] = name
    nxt["stored_prose"] = 0
    return nxt
