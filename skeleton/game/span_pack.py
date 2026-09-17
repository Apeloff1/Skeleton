"""Named spans."""

from __future__ import annotations

from typing import Any


class SpanPackError(ValueError):
    pass


SPAN = tuple(f"sp_{i:02d}" for i in range(16))


def set_span(node: dict[str, Any], name: str, length: int) -> dict[str, Any]:
    if name not in SPAN:
        raise SpanPackError(name)
    nxt = dict(node)
    nxt["span"] = name
    nxt["length"] = max(1, int(length))
    nxt["stored_prose"] = 0
    return nxt
