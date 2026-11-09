"""Reclaim kernel — mobile low-memory killer for mesh atoms.

Drops oldest low-confidence captures first. Never touches
internalized or principle atoms unless force=True.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class Reclaim:
    def __init__(self, floor: int = 48) -> None:
        self.floor = max(8, int(floor))
        self.killed = 0

    def run(self, mesh, *, target: Optional[int] = None, force: bool = False) -> Dict[str, Any]:
        want = int(target if target is not None else self.floor)
        seen = []
        for lib in (*getattr(mesh, "brains", {}).values(), getattr(mesh, "wiki", None)):
            if lib is None:
                continue
            for atom in lib.all():
                if atom.superseded_by:
                    continue
                seen.append(atom)
        extra = max(0, len(seen) - want)
        victims = []
        for atom in sorted(seen, key=lambda a: (a.confidence, getattr(a, "ts", 0))):
            if extra <= 0:
                break
            tags = atom.tags or ()
            if "internalized" in tags and not force:
                continue
            if atom.kind == "principle" and not force:
                continue
            atom.superseded_by = "reclaim"
            victims.append(atom.id)
            extra -= 1
        self.killed += len(victims)
        return {
            "kind": "kernel-reclaim",
            "killed": len(victims),
            "live": len(seen) - len(victims),
            "floor": want,
            "stored_prose": 0,
        }

    def card(self) -> Dict[str, Any]:
        return {"kind": "kernel-reclaim", "killed": self.killed, "floor": self.floor, "stored_prose": 0}
