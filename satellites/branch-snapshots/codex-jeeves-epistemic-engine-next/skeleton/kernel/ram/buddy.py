"""Buddy allocator. Power-of-two frames over a fixed heap.

Orders 4..12 → 16 B .. 4 KiB simulated frames. Counts splits/merges.
No mmap. The heap is a free-list of integer ids.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class Buddy:
    def __init__(self, orders: int = 8, root: int = 12) -> None:
        self.root = max(6, min(16, int(root)))
        self.min_order = max(2, self.root - max(4, int(orders)))
        self.free: Dict[int, List[int]] = {o: [] for o in range(self.min_order, self.root + 1)}
        self.free[self.root].append(0)
        self.used: Dict[int, int] = {}
        self.splits = 0
        self.merges = 0
        self.fails = 0

    def _split(self, order: int) -> Optional[int]:
        if order > self.root:
            return None
        if self.free[order]:
            return self.free[order].pop()
        parent = self._split(order + 1)
        if parent is None:
            return None
        self.splits += 1
        buddy = parent + (1 << order)
        self.free[order].append(buddy)
        return parent

    def alloc(self, need: int) -> Optional[int]:
        need = max(1, int(need))
        order = self.min_order
        size = 1 << order
        while size < need and order < self.root:
            order += 1
            size <<= 1
        addr = self._split(order)
        if addr is None:
            self.fails += 1
            return None
        self.used[addr] = order
        return addr

    def free_addr(self, addr: int) -> None:
        order = self.used.pop(addr, None)
        if order is None:
            return
        while order < self.root:
            buddy = addr ^ (1 << order)
            if buddy in self.free[order]:
                self.free[order].remove(buddy)
                addr = min(addr, buddy)
                order += 1
                self.merges += 1
            else:
                break
        self.free[order].append(addr)

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-buddy",
            "used": len(self.used),
            "splits": self.splits,
            "merges": self.merges,
            "fails": self.fails,
            "stored_prose": 0,
        }
