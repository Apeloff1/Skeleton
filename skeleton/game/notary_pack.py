"""Named notaries."""

from __future__ import annotations

from typing import Any


class NotaryPackError(ValueError):
    pass


NOTARY = tuple(f"nt_{i:02d}" for i in range(8))


def attest(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in NOTARY:
        raise NotaryPackError(name)
    nxt = dict(state)
    nxt["notary"] = name
    nxt["ok"] = 1
    nxt["stored_prose"] = 0
    return nxt
