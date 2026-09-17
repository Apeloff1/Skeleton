"""Named setters."""

from __future__ import annotations

from typing import Any


class SetterPackError(ValueError):
    pass


SETTER = tuple(f"st_{i:02d}" for i in range(12))


def set_setter(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SETTER:
        raise SetterPackError(name)
    nxt = dict(state)
    nxt["setter"] = name
    nxt["stored_prose"] = 0
    return nxt
