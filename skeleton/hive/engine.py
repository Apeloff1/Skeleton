"""Compose mint, link, gossip x2, walk, tick."""

from __future__ import annotations

from typing import Any

from skeleton.hive.cards import hive_card
from skeleton.hive.kernel import Hive
from skeleton.hive.law import WALK_CAP


class HiveEngine:
    def snapshot(self) -> dict[str, Any]:
        h = Hive()
        a = h.mint("alpha")
        b = h.link(a["root"], "beta")
        g1 = h.gossip()
        g2 = h.gossip(b["root"])
        w = h.walk(a["root"])
        t = h.tick()
        hist_ok = g2["n_history"] >= 2
        walk_ok = len(w["path"]) <= WALK_CAP
        ok = hist_ok and walk_ok and a["stored_prose"] == 0
        return hive_card(
            kind="hive",
            hit=1 if ok else 0,
            law="hive 1.0",
            extra={
                "root": t.get("root"),
                "n_history": g2["n_history"],
                "path_n": w["n"],
                "ticks": t["ticks"],
                "consensus": g1.get("consensus"),
            },
        )
