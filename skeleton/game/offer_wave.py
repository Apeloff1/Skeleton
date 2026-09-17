"""Wave-4 barter offers."""

from __future__ import annotations

from typing import Any


class OfferWaveError(ValueError):
    pass


OFF = {
    f"off_{i:02d}": (
        ("scrap", "parts", "coil", "xp", "sleep")[i % 5],
        1 + (i % 2),
        ("parts", "coil", "key", "hp", "tokens")[i % 5],
    )
    for i in range(20)
}


def apply(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in OFF:
        raise OfferWaveError(name)
    src, need, dst = OFF[name]
    nxt = dict(state)
    if int(nxt.get(src, 0)) < need:
        raise OfferWaveError("need")
    nxt[src] = int(nxt.get(src, 0)) - need
    nxt[dst] = int(nxt.get(dst, 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
