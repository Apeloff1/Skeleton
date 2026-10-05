"""Batch kernel — continuous batch size cap.

Pointer: Orca / vLLM continuous batching. House mapping is how
many pulses may share a tick.
"""
from __future__ import annotations

from typing import Any, Dict, List


class Batch:
    def __init__(self, cap: int = 2) -> None:
        self.cap = max(1, int(cap))
        self.cur: List[str] = []
        self.ticks = 0

    def add(self, code: str) -> bool:
        if len(self.cur) >= self.cap:
            return False
        self.cur.append(str(code))
        return True

    def flush(self) -> List[str]:
        out = list(self.cur)
        self.cur = []
        self.ticks += 1
        return out

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-batch",
            "cap": self.cap,
            "open": len(self.cur),
            "ticks": self.ticks,
            "stored_prose": 0,
        }
