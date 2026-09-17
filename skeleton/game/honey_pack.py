"""Named honey lots."""

from __future__ import annotations

from typing import Any


class HoneyPackError(ValueError):
    pass


HONEY = tuple(f"hn_{i:02d}" for i in range(16))


def jar(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in HONEY:
        raise HoneyPackError(name)
    nxt = dict(state)
    have = list(nxt.get("honey") or [])
    have.append(name)
    nxt["honey"] = have
    nxt["stored_prose"] = 0
    return nxt
