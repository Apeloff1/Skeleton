"""Priority kernel — aging heap for next codes."""
from __future__ import annotations

import heapq
from typing import Any, Dict, List, Tuple


class Priority:
    def __init__(self) -> None:
        self._h: List[Tuple[int, int, str]] = []
        self._seq = 0
        self.popped = 0

    def push(self, code: str, prio: int) -> None:
        heapq.heappush(self._h, (int(prio), self._seq, str(code)))
        self._seq += 1

    def pop(self) -> str:
        if not self._h:
            return "hold"
        _, _, code = heapq.heappop(self._h)
        self.popped += 1
        return code

    def age(self, delta: int = 1) -> None:
        aged = []
        while self._h:
            p, s, c = heapq.heappop(self._h)
            aged.append((max(0, p - delta), s, c))
        for row in aged:
            heapq.heappush(self._h, row)

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-priority",
            "queued": len(self._h),
            "popped": self.popped,
            "stored_prose": 0,
        }
