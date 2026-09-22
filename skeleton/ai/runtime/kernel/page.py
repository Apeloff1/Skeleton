"""Page kernel — fixed-size frames for atom ids.

Pointer: PagedAttention / PersistentKV. House mapping is a free-list
of frames. No GPU block table. No FlashInfer.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class Page:
    def __init__(self, frames: int = 64, size: int = 16) -> None:
        self.size = max(4, int(size))
        self.free: List[int] = list(range(max(4, int(frames))))
        self.used: Dict[int, List[str]] = {}
        self.faults = 0

    def alloc(self, key: str) -> Optional[int]:
        if not self.free:
            self.faults += 1
            return None
        fid = self.free.pop(0)
        self.used[fid] = [str(key)]
        return fid

    def append(self, fid: int, key: str) -> bool:
        row = self.used.get(fid)
        if row is None or len(row) >= self.size:
            return False
        row.append(str(key))
        return True

    def free_frame(self, fid: int) -> None:
        if fid in self.used:
            del self.used[fid]
            self.free.append(fid)

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-page",
            "free": len(self.free),
            "used": len(self.used),
            "faults": self.faults,
            "size": self.size,
            "stored_prose": 0,
        }
