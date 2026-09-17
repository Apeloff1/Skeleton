"""Named inn signs."""

from __future__ import annotations

from typing import Any


class InnsignPackError(ValueError):
    pass


SIGN = tuple(f"is_{i:02d}" for i in range(12))


def hang(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SIGN:
        raise InnsignPackError(name)
    nxt = dict(node)
    nxt["innsign"] = name
    nxt["stored_prose"] = 0
    return nxt
