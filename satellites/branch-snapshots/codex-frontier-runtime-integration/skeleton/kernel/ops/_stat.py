"""Write counter — fusion is fewer materializations."""
from __future__ import annotations

WRITES = 0


def bump(n: int = 1) -> None:
    global WRITES
    WRITES += int(n)


def reset() -> None:
    global WRITES
    WRITES = 0


def reads() -> int:
    return WRITES
