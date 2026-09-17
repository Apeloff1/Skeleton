"""Named tuns."""

from __future__ import annotations

from typing import Any


class TunPackError(ValueError):
    pass


TUN = tuple(f"tn_{i:02d}" for i in range(8))


def set_tun(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TUN:
        raise TunPackError(name)
    nxt = dict(node)
    nxt["tun"] = name
    nxt["stored_prose"] = 0
    return nxt
