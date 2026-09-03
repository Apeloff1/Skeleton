"""Coverage — catalog vs live bank vs hot stages."""
from __future__ import annotations

from typing import Any, Dict, List

from skeleton.kernel.ops.catalog import EXTRA, OBLIGATORY
from skeleton.kernel.hot import rank
from skeleton.kernel.scoreboard import card as score_card


def card() -> Dict[str, Any]:
    board = score_card()
    live = set(board.get("rows") or {})
    hot = set(rank().get("hot") or [])
    obl = list(OBLIGATORY)
    extra = list(EXTRA)
    bundled = {"matmul", "attention", "rmsnorm", "kvcache", "qlinear", "sample", "fused"}
    covered = set(live)
    if "ops" in live or "block" in live:
        covered.update(bundled)
    if "extras" in live or "block" in live:
        covered.update(set(extra))
    missing_obl = [k for k in obl if k not in covered]
    missing_extra = [k for k in extra if k not in covered]
    return {
        "kind": "kernel-coverage",
        "live_n": len(live),
        "hot_n": len(hot),
        "obligatory": obl,
        "missing_obl": missing_obl,
        "missing_extra": missing_extra,
        "live": sorted(live),
        "hot": sorted(hot),
        "pct_obl": round(100 * (1 - len(missing_obl) / max(1, len(obl))), 1),
        "stored_prose": 0,
    }
