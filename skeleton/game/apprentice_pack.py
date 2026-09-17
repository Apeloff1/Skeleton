"""Named apprentices."""

from __future__ import annotations

from typing import Any


class ApprenticePackError(ValueError):
    pass


APP = tuple(f"ap_{i:02d}" for i in range(16))


def bind(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in APP:
        raise ApprenticePackError(name)
    nxt = dict(state)
    have = list(nxt.get("apprentice") or [])
    have.append(name)
    nxt["apprentice"] = have
    nxt["stored_prose"] = 0
    return nxt
