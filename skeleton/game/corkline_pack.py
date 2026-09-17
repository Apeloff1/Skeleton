"""Named cork lines."""

from __future__ import annotations

from typing import Any


class CorklinePackError(ValueError):
    pass


CORK = tuple(f"ck_{i:02d}" for i in range(12))


def set_cork(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CORK:
        raise CorklinePackError(name)
    nxt = dict(state)
    nxt["corkline"] = name
    nxt["float"] = 1
    nxt["stored_prose"] = 0
    return nxt
