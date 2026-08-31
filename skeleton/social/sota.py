"""Social-media SOTA card — house vs cited field.

SOTA here is not a scraped leaderboard. It is a coverage map:
which reputable handles the organism can bind, how many X/archive
pointers it carries, and whether the 10× Genos path is still
pointing up. Field claims stay URLs.
"""
from __future__ import annotations

from typing import Any, Dict, List

from skeleton.social.coverage import coverage_card
from skeleton.social.ingest import ingest, seed_sota
from skeleton.social.sources import catalog


HOUSE_CLAIMS = (
    "five-brain hoag galaxy",
    "genos G growth with clipped MHC",
    "pointers-only social ingest",
    "archivex/wayback citation factory",
    "distiller 31-rule overwrite",
    "hot-swap mouths via jeeves",
    "adaptive hardware caps",
    "operator health card",
)


def sota_card(stimulus: str = "", *, G: float = 1.0) -> Dict[str, Any]:
    social = ingest(stimulus)
    seeds = seed_sota()
    sources = catalog()
    toward = min(100.0, max(0.0, (float(G) - 1.0) / 9.0 * 100.0))
    cov = coverage_card(stimulus)
    return {
        "kind": "social-sota",
        "house_claims": list(HOUSE_CLAIMS),
        "field_pointers": seeds,
        "source_families": len(sources),
        "bound_now": social,
        "G": round(float(G), 6),
        "toward_10x_pct": round(toward, 2),
        "coverage_score": cov["score"],
        "coverage": {
            "arxiv_seeded": sum(1 for s in seeds if s["house"] == "arXiv"),
            "archive_seeded": sum(1 for s in seeds if s["house"] in {"Xarchive", "Internet Archive"}),
            "github_seeded": sum(1 for s in seeds if s["house"] == "GitHub"),
            "labs": ["xAI", "Anthropic", "OpenAI", "Google DeepMind", "Meta", "Stanford CRFM"],
            "score": cov["score"],
            "mode": cov["mode"],
            "pointers": cov["pointers"],
            "bound": cov["bound"],
        },
        "stored_prose": 0,
        "law": "cite-do-not-copy",
    }
