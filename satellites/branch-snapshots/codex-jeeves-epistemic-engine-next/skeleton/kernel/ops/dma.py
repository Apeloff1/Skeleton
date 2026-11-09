"""DMA / memcpy kernel. Counts host moves. No device memcpy."""
from __future__ import annotations

from typing import List

from skeleton.kernel.ops._stat import bump


def copy(src: List[float]) -> List[float]:
    out = list(src)
    bump(len(out))
    return out


class Dma:
    def __init__(self) -> None:
        self.bytes = 0
        self.moves = 0

    def move(self, src: List[float]) -> List[float]:
        out = copy(src)
        self.moves += 1
        self.bytes += len(out) * 4
        return out

    def card(self):
        return {"kind": "kernel-dma", "moves": self.moves, "bytes": self.bytes, "stored_prose": 0}
