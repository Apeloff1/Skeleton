"""Named craft steps."""

from __future__ import annotations

from typing import Any


class CraftStepError(ValueError):
    pass


STEPS: dict[str, tuple[str, int, str]] = {
    f"step_{i:02d}": (
        ("scrap", "parts", "coil", "bait", "key")[i % 5],
        1 + (i % 2),
        ("coil", "bait", "key", "ward", "patch")[i % 5],
    )
    for i in range(28)
}


def apply(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STEPS:
        raise CraftStepError(name)
    src, n, dst = STEPS[name]
    nxt = dict(state)
    if int(nxt.get(src, 0)) < n:
        raise CraftStepError("need")
    nxt[src] = int(nxt.get(src, 0)) - n
    nxt[dst] = int(nxt.get(dst, 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
