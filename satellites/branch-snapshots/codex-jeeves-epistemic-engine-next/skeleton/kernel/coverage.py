"""Coverage — catalog vs live bank vs hot stages."""
from __future__ import annotations

from typing import Any, Dict, List

from skeleton.kernel.ops.catalog import EXTRA, OBLIGATORY, OBSCURE, SOCIAL
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
    obscure = list(OBSCURE)
    if "obscure" in live or "block" in live:
        covered.update(set(obscure))
    missing_obl = [k for k in obl if k not in covered]
    missing_extra = [k for k in extra if k not in covered]
    missing_obscure = [k for k in obscure if k not in covered]
    social = list(SOCIAL)
    if "socialk" in live or "block" in live:
        covered.update(set(social))
    missing_social = [k for k in social if k not in covered]
    return {
        "kind": "kernel-coverage",
        "live_n": len(live),
        "hot_n": len(hot),
        "obligatory": obl,
        "missing_obl": missing_obl,
        "missing_extra": missing_extra,
        "missing_obscure": missing_obscure,
        "pct_obscure": round(100 * (1 - len(missing_obscure) / max(1, len(obscure))), 1),
        "missing_social": missing_social,
        "pct_social": round(100 * (1 - len(missing_social) / max(1, len(social))), 1),
        "live": sorted(live),
        "hot": sorted(hot),
        "pct_obl": round(100 * (1 - len(missing_obl) / max(1, len(obl))), 1),
        "mix": __import__("skeleton.organism.context_step", fromlist=["mix_card"]).mix_card(),
        "stored_prose": 0,
    }
