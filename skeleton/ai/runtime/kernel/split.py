"""Split kernel — prefill vs decode budget.

Pointer: DistServe-style disaggregation. House mapping is two
counters. No cluster split.
"""
from __future__ import annotations

from typing import Any, Dict


class Split:
    def __init__(self, prefill: int = 4, decode: int = 8) -> None:
        self.cap = {"prefill": max(1, int(prefill)), "decode": max(1, int(decode))}
        self.used = {"prefill": 0, "decode": 0}

    def take(self, phase: str) -> bool:
        if phase not in self.cap:
            return False
        if self.used[phase] >= self.cap[phase]:
            return False
        self.used[phase] += 1
        return True

    def reset(self) -> None:
        self.used = {"prefill": 0, "decode": 0}

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-split",
            "cap": dict(self.cap),
            "used": dict(self.used),
            "stored_prose": 0,
        }
