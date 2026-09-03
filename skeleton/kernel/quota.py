"""Quota kernel — per-slot atom / walk / dump budgets."""
from __future__ import annotations

from typing import Any, Dict


class Quota:
    def __init__(self, atoms: int = 48, walks: int = 2, dumps: int = 1) -> None:
        self.cap = {"atoms": int(atoms), "walks": int(walks), "dumps": int(dumps)}
        self.used = {"atoms": 0, "walks": 0, "dumps": 0}

    def take(self, name: str, n: int = 1) -> bool:
        if name not in self.cap:
            return False
        if self.used[name] + n > self.cap[name]:
            return False
        self.used[name] += n
        return True

    def reset(self, name: str = "") -> None:
        if name:
            self.used[name] = 0
        else:
            self.used = {k: 0 for k in self.cap}

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-quota",
            "cap": dict(self.cap),
            "used": dict(self.used),
            "stored_prose": 0,
        }
