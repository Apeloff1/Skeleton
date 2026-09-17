"""Named keels."""

from __future__ import annotations

from typing import Any


class KeelPackError(ValueError):
    pass


KEEL = tuple(f"kl_{i:02d}" for i in range(8))


def set_keel(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in KEEL:
        raise KeelPackError(name)
    nxt = dict(node)
    nxt["keel"] = name
    nxt["stored_prose"] = 0
    return nxt
