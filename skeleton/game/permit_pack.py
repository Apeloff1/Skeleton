"""Named work permits."""

from __future__ import annotations

from typing import Any


class PermitPackError(ValueError):
    pass


PERMIT = tuple(f"pm_{i:02d}" for i in range(16))


def issue(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PERMIT:
        raise PermitPackError(name)
    nxt = dict(state)
    have = list(nxt.get("permit") or [])
    if name not in have:
        have.append(name)
    nxt["permit"] = have
    nxt["stored_prose"] = 0
    return nxt
