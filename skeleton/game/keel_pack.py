"""Named keels."""

from __future__ import annotations

from typing import Any


class KeelPackError(ValueError):
    pass


KEEL = tuple(f"kl_{i:02d}" for i in range(12))


def set_keel(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in KEEL:
        raise KeelPackError(name)
    nxt = dict(state)
    nxt["keel"] = name
    nxt["stored_prose"] = 0
    return nxt
