"""Checksum over RAM clock keys. Detect silent frame rot."""
from __future__ import annotations

import hashlib
from typing import Any, Dict


class Check:
    def __init__(self) -> None:
        self.last = ""
        self.ok = 0
        self.bad = 0

    def stamp(self, clock) -> str:
        blob = "|".join(k or "" for k in clock.keys)
        self.last = hashlib.sha256(blob.encode("utf-8")).hexdigest()
        return self.last

    def verify(self, clock) -> bool:
        now = hashlib.sha256("|".join(k or "" for k in clock.keys).encode("utf-8")).hexdigest()
        if now == self.last or not self.last:
            self.ok += 1
            self.last = now
            return True
        self.bad += 1
        return False

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-check",
            "ok": self.ok,
            "bad": self.bad,
            "head": self.last[:12],
            "stored_prose": 0,
        }
