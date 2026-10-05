"""Pin kernel — keep hot pages resident."""
from __future__ import annotations

from typing import Any, Dict, Set


class Pin:
    def __init__(self, cap: int = 8) -> None:
        self.cap = max(1, int(cap))
        self.hot: Set[str] = set()
        self.evicted = 0

    def hold(self, key: str) -> bool:
        if key in self.hot:
            return True
        if len(self.hot) >= self.cap:
            self.hot.pop()
            self.evicted += 1
        self.hot.add(str(key))
        return True

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-pin",
            "n": len(self.hot),
            "cap": self.cap,
            "evicted": self.evicted,
            "stored_prose": 0,
        }
