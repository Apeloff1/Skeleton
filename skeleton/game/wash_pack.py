"""Named washes."""

from __future__ import annotations

from typing import Any


class WashPackError(ValueError):
    pass


WASH = tuple(f"wa_{i:02d}" for i in range(8))


def charge(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in WASH:
        raise WashPackError(name)
    nxt = dict(state)
    nxt["wash"] = name
    nxt["wet"] = int(nxt.get("wet", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
