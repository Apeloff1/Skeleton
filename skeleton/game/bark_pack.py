"""Named bark lots."""

from __future__ import annotations

from typing import Any


class BarkPackError(ValueError):
    pass


BARK = tuple(f"bk_{i:02d}" for i in range(16))


def tan(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BARK:
        raise BarkPackError(name)
    nxt = dict(state)
    have = list(nxt.get("bark") or [])
    have.append(name)
    nxt["bark"] = have
    nxt["stored_prose"] = 0
    return nxt
