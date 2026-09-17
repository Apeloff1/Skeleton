"""Named stepping stones."""

from __future__ import annotations

from typing import Any


class StepstonePackError(ValueError):
    pass


STEP = tuple(f"ss_{i:02d}" for i in range(16))


def set_step(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STEP:
        raise StepstonePackError(name)
    nxt = dict(node)
    have = list(nxt.get("stepstone") or [])
    have.append(name)
    nxt["stepstone"] = have
    nxt["stored_prose"] = 0
    return nxt
