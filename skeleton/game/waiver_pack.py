"""Named waivers."""

from __future__ import annotations

from typing import Any


class WaiverPackError(ValueError):
    pass


WAIVER = tuple(f"wv_{i:02d}" for i in range(16))


def sign(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in WAIVER:
        raise WaiverPackError(name)
    nxt = dict(state)
    have = list(nxt.get("waiver") or [])
    if name not in have:
        have.append(name)
    nxt["waiver"] = have
    nxt["stored_prose"] = 0
    return nxt
