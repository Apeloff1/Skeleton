"""Named catchwords."""

from __future__ import annotations

from typing import Any


class CatchwordPackError(ValueError):
    pass


CATCH = tuple(f"cw_{i:02d}" for i in range(16))


def set_catch(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CATCH:
        raise CatchwordPackError(name)
    nxt = dict(state)
    nxt["catchword"] = name
    nxt["stored_prose"] = 0
    return nxt
