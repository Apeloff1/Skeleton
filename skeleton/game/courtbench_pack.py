"""Named benches."""

from __future__ import annotations

from typing import Any


class CourtbenchPackError(ValueError):
    pass


BENCH = tuple(f"cb_{i:02d}" for i in range(8))


def set_bench(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BENCH:
        raise CourtbenchPackError(name)
    nxt = dict(node)
    nxt["courtbench"] = name
    nxt["stored_prose"] = 0
    return nxt
