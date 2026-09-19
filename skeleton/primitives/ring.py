"""Bounded ring. Cap 24. Oldest drops on overflow if drop=True else fail-closed."""

from __future__ import annotations

from collections import deque
from typing import Iterable, Iterator

from skeleton.primitives.cards import primitive_card
from skeleton.primitives.errors import RingCapError
from skeleton.primitives.law import RING_CAP


class Ring:
    def __init__(self, cap: int = RING_CAP) -> None:
        if cap != RING_CAP:
            raise RingCapError("cap")
        self.cap = cap
        self._q: deque[str] = deque(maxlen=cap)

    def __len__(self) -> int:
        return len(self._q)

    def __iter__(self) -> Iterator[str]:
        return iter(self._q)

    def items(self) -> list[str]:
        return list(self._q)

    def push(self, token: str, *, drop: bool = True) -> str | None:
        evicted = None
        if len(self._q) >= self.cap:
            if not drop:
                raise RingCapError("full")
            evicted = self._q[0]
        self._q.append(token)
        return evicted

    def extend(self, tokens: Iterable[str], *, drop: bool = True) -> int:
        n = 0
        for token in tokens:
            self.push(token, drop=drop)
            n += 1
        return n

    def clear(self) -> None:
        self._q.clear()

    def card(self) -> dict:
        return primitive_card(
            kind="ring",
            hit=1 if len(self._q) <= self.cap else 0,
            law="ring cap 24",
            extra={"size": len(self._q), "cap": self.cap},
        )
