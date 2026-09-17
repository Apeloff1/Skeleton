"""Named nodi."""

from __future__ import annotations

from typing import Any


class NodusPackError(ValueError):
    pass


NODUS = tuple(f"nd_{i:02d}" for i in range(8))


def set_nodus(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in NODUS:
        raise NodusPackError(name)
    nxt = dict(node)
    nxt["nodus"] = name
    nxt["stored_prose"] = 0
    return nxt
