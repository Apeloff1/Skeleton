"""Field coverage — how many reputable houses a pulse can name.

Score is bound-houses / catalog-houses when URLs are present,
else seeded-pointer density. No bodies. Pointers only.
"""
from __future__ import annotations

from typing import Any, Dict, Set

from skeleton.social.ingest import ingest
from skeleton.social.sources import SOTA_POINTERS, catalog


def coverage_card(stimulus: str = "") -> Dict[str, Any]:
    sources = catalog()
    houses: Set[str] = {str(s["house"]) for s in sources}
    kinds: Set[str] = {str(s["kind"]) for s in sources}
    social = ingest(stimulus)
    bound = {str(c.get("house")) for c in (social.get("cards") or []) if c.get("house")}
    if bound:
        score = len(bound & houses) / max(1, len(houses))
        mode = "live-bind"
    else:
        score = min(1.0, len(SOTA_POINTERS) / 24.0)
        mode = "seed-density"
    return {
        "kind": "field-coverage",
        "houses": sorted(houses),
        "kinds": sorted(kinds),
        "pointers": len(SOTA_POINTERS),
        "source_families": len(sources),
        "bound": sorted(bound),
        "score": round(score, 4),
        "mode": mode,
        "stored_prose": 0,
    }
