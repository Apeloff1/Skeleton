"""Named cringles."""

from __future__ import annotations

from typing import Any


class CringlePackError(ValueError):
    pass


CRINGLE = tuple(f"cg_{i:02d}" for i in range(16))


def set_cringle(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CRINGLE:
        raise CringlePackError(name)
    nxt = dict(state)
    have = list(nxt.get("cringle") or [])
    have.append(name)
    nxt["cringle"] = have
    nxt["stored_prose"] = 0
    return nxt
