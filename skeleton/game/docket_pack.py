"""Named dockets."""

from __future__ import annotations

from typing import Any


class DocketPackError(ValueError):
    pass


DOCKET = tuple(f"dk_{i:02d}" for i in range(16))


def file(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in DOCKET:
        raise DocketPackError(name)
    nxt = dict(state)
    have = list(nxt.get("docket") or [])
    have.append(name)
    nxt["docket"] = have
    nxt["stored_prose"] = 0
    return nxt
