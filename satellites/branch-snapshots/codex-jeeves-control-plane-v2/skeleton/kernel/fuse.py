"""Fuse kernel — budget for fused decode/MoE steps.

Pointer: MobileMoE fused expert kernel. House mapping is a
counter + cap. No generated mobile GEMM. No HF weights.
"""
from __future__ import annotations

from typing import Any, Dict


class Fuse:
    def __init__(self, cap: int = 8) -> None:
        self.cap = max(1, int(cap))
        self.used = 0
        self.skipped = 0

    def step(self, width: int = 1) -> bool:
        if self.used + width > self.cap:
            self.skipped += 1
            return False
        self.used += width
        return True

    def reset(self) -> None:
        self.used = 0

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-fuse",
            "cap": self.cap,
            "used": self.used,
            "skipped": self.skipped,
            "stored_prose": 0,
        }
