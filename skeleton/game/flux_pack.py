"""Named fluxes."""

from __future__ import annotations

from typing import Any


class FluxPackError(ValueError):
    pass


FLUX = tuple(f"fx_{i:02d}" for i in range(24))


def add(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FLUX:
        raise FluxPackError(name)
    nxt = dict(state)
    have = list(nxt.get("flux") or [])
    have.append(name)
    nxt["flux"] = have
    nxt["stored_prose"] = 0
    return nxt
