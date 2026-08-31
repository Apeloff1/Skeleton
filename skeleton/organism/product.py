"""Product card — one operator-facing snapshot of the living system."""
from __future__ import annotations

from typing import Any, Dict

from skeleton.organism.ledger import count, head
from skeleton.organism.organismer import live_organismer
from skeleton.galaxy.vault import vault_path
from skeleton.organism.caps import card as caps_card
from skeleton.organism.health import health_card
from skeleton.organism.path10 import path_card
from skeleton.social.coverage import coverage_card
from skeleton.organism.paths import ledger_path, state_path
from skeleton.social.sota import sota_card
from skeleton.social.sources import SOTA_POINTERS


ENDPOINTS = (
    "GET /cortex/product",
    "GET|POST /cortex/organismer",
    "GET|POST /cortex/social",
    "GET|POST /cortex/galaxy",
    "CLI: python -m skeleton product",
    "CLI: python -m skeleton organismer <stimulus>",
    "GET /cortex/wiki?q=",
    "GET /cortex/banks",
    "GET /cortex/caps",
    "GET /cortex/lattice",
    "GET /cortex/health",
    "GET /cortex/next",
    "POST /cortex/seed",
)


def product_card() -> Dict[str, Any]:
    org = live_organismer()
    snap = org.snapshot()
    return {
        "kind": "product",
        "name": "Jeeves Cortex Organism",
        "G": snap["G"],
        "target": snap["target"],
        "toward_10x_pct": snap["toward_10x_pct"],
        "steps": snap["steps"],
        "errors": snap["errors"],
        "galaxy_pulses": snap["galaxy_pulses"],
        "galaxy_atoms": sum(len(lib.shelf) for lib in org.galaxy.mesh.brains.values()),
        "wiki_topics": len(org.galaxy.mesh.wiki.topics),
        "ledger": {"head": head(org.root), "n": count(org.root), "path": str(ledger_path(org.root))},
        "state_path": str(state_path(org.root)),
        "vault": vault_path(org.root).as_posix(),
        "caps": caps_card(),
        "health": health_card(org),
        "path10": path_card(org),
        "coverage": coverage_card(""),
        "fresh": org.galaxy.editor.freshness(),
        "endpoints": list(ENDPOINTS),
        "field": [dict(p) for p in SOTA_POINTERS],
        "sota": sota_card("", G=org.G),
        "laws": ("cite-do-not-copy", "stored_prose=0", "clipped-G", "write-route skip|update|new"),
        "stored_prose": 0,
    }
