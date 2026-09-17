"""Named lead lines."""

from __future__ import annotations

from typing import Any


class LeadlinePackError(ValueError):
    pass


LEAD = tuple(f"ld_{i:02d}" for i in range(12))


def cast(state: dict[str, Any], name: str, fath: int) -> dict[str, Any]:
    if name not in LEAD:
        raise LeadlinePackError(name)
    nxt = dict(state)
    nxt["leadline"] = name
    nxt["fath"] = max(0, int(fath))
    nxt["stored_prose"] = 0
    return nxt
