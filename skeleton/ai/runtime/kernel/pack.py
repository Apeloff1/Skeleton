"""Pack kernel — pack small atoms into one frame."""
from __future__ import annotations

from typing import Any, Dict, List


class Pack:
    def __init__(self, width: int = 8) -> None:
        self.width = max(2, int(width))
        self.cur: List[str] = []
        self.frames = 0

    def add(self, key: str) -> bool:
        self.cur.append(str(key))
        if len(self.cur) >= self.width:
            self.frames += 1
            self.cur = []
            return True
        return False

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-pack",
            "width": self.width,
            "open": len(self.cur),
            "frames": self.frames,
            "stored_prose": 0,
        }
