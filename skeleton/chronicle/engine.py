"""Three appends of observe/forge/gossip then verify."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from skeleton.chronicle.cards import helix_card
from skeleton.chronicle.helix import Helix


class ChronicleEngine:
    def snapshot(self, path: Path) -> dict[str, Any]:
        h = Helix(path)
        h.append("observe", "r1")
        h.append("forge", "r2")
        h.append("gossip", "r3")
        ok = h.verify() and len(h.records()) == 3
        return helix_card(
            kind="helix",
            hit=1 if ok else 0,
            law="helix jsonl",
            extra={"n": len(h.records()), "tip": h.tip() or "", "ok": int(ok)},
        )
