"""Paged KV cache. Frames of (k,v) rows. PersistentKV handle."""
from __future__ import annotations

from typing import List, Optional, Tuple

from skeleton.kernel.ops._stat import bump

Row = List[float]


class KVCache:
    def __init__(self, frames: int = 16, width: int = 8) -> None:
        self.width = max(2, int(width))
        self.free = list(range(max(2, int(frames))))
        self.pages: dict[int, List[Tuple[Row, Row]]] = {}
        self.seq: List[int] = []
        self.faults = 0

    def put(self, k: Row, v: Row) -> Optional[int]:
        if self.seq and self.seq[-1] in self.pages:
            fid = self.seq[-1]
            if len(self.pages[fid]) < self.width:
                self.pages[fid].append((list(k), list(v)))
                bump(len(k) + len(v))
                return fid
        if not self.free:
            self.faults += 1
            return None
        fid = self.free.pop(0)
        self.pages[fid] = [(list(k), list(v))]
        self.seq.append(fid)
        bump(len(k) + len(v))
        return fid

    def rows(self) -> List[Tuple[Row, Row]]:
        out: List[Tuple[Row, Row]] = []
        for fid in self.seq:
            out.extend(self.pages.get(fid) or [])
        return out

    def card(self):
        return {
            "kind": "kernel-kvcache",
            "pages": len(self.pages),
            "tokens": sum(len(v) for v in self.pages.values()),
            "faults": self.faults,
            "stored_prose": 0,
        }
