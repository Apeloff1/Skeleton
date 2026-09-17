"""Named save marks."""

from __future__ import annotations

from typing import Any


class SaveMarkError(ValueError):
    pass


MARKS = tuple(f"mark_{i:02d}" for i in range(24))


def write(bank: dict[str, Any], name: str, digest: str) -> dict[str, Any]:
    if name not in MARKS:
        raise SaveMarkError(name)
    if not digest:
        raise SaveMarkError("digest")
    nxt = dict(bank)
    nxt[name] = {"digest": digest, "stored_prose": 0}
    return nxt


def read(bank: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in MARKS:
        raise SaveMarkError(name)
    card = bank.get(name)
    if not card:
        raise SaveMarkError("empty")
    return dict(card)
