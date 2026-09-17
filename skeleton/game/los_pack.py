"""LOS rays. Block on lock/fog/dead."""

from __future__ import annotations


class LosPackError(ValueError):
    pass


def visible(cells: list[str], start: int, end: int, *, tolerate: int = 1) -> bool:
    if start < 0 or end >= len(cells) or start > end:
        raise LosPackError("range")
    blocked = 0
    for cell in cells[start:end + 1]:
        if cell in {"lock", "fog", "dead"}:
            blocked += 1
            if blocked > tolerate:
                return False
    return True
