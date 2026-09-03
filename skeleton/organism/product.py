"""Product card — one operator-facing snapshot of the living system."""
from __future__ import annotations

from typing import Any, Dict

from skeleton.organism.ledger import count, head
from skeleton.organism.organismer import live_organismer
from skeleton.galaxy.vault import vault_path
from skeleton.organism.caps import card as caps_card
from skeleton.organism.doctor import doctor_card
from skeleton.organism.laws import laws_card
from skeleton.organism.health import health_card
from skeleton.organism.next import hint as next_hint
from skeleton.organism.mhc import mhc_card
from skeleton.organism.path10 import path_card
from skeleton.social.coverage import coverage_card
from skeleton.organism.paths import ledger_path, state_path
from skeleton.social.sota import sota_card
from skeleton.social.sources import SOTA_POINTERS


VERSION = "2026.09.03-rotf3"


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
    "GET /cortex/ready",
    "POST /cortex/pulse",
    "POST /cortex/walk",
    "GET /cortex/field",
    "GET /cortex/doctor",
    "GET /cortex/laws",
    "GET /cortex/graph",
    "GET /cortex/context",
    "GET|POST /cortex/sleep",
    "POST /cortex/forget",
    "GET /cortex/helix",
    "GET /cortex/recall?q=",
    "GET /cortex/satellites",
    "GET /cortex/nervous",
    "GET /cortex/chronicle",
    "POST /cortex/dump",
    "GET /cortex/scope",
    "POST /cortex/enact",
    "GET /cortex/kernels",
    "GET /cortex/follow",
    "GET /cortex/agree",
)


def _quality_snapshot(root=None) -> Dict[str, Any]:
    from skeleton.organism.quality_state import quality_snapshot
    return quality_snapshot(root=root)


def product_card() -> Dict[str, Any]:
    org = live_organismer()
    snap = org.snapshot()
    laws = laws_card(org.galaxy.mesh)
    quality = _quality_snapshot(root=getattr(org, "root", None))
    latest_repair = quality.get("latest_repair") or {}
    repair_view = {
        "surface": latest_repair.get("surface") or "",
        "reason": latest_repair.get("reason") or "",
        "changed": (latest_repair.get("metadata") or {}).get("changed", 0),
        "before_reason": (latest_repair.get("metadata") or {}).get("before_reason") or "",
        "after_reason": (latest_repair.get("metadata") or {}).get("after_reason") or "",
        "target": latest_repair.get("weakest_path") or "",
    }
    return {
        "kind": "product",
        "name": "Jeeves Cortex Organism",
        "version": VERSION,
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
        "doctor": doctor_card(org),
        "path10": path_card(org),
        "mhc": mhc_card(org),
        "budget": next_hint(org).get("budget"),
        "kernels": {
            "scoreboard_n": __import__("skeleton.kernel.scoreboard", fromlist=["card"]).card().get("n"),
            "hot": __import__("skeleton.kernel.hot", fromlist=["rank"]).rank().get("hot"),
            "persist_n": __import__("skeleton.kernel.persist", fromlist=["load"]).load().get("n"),
            "stored_prose": 0,
        },
        "coverage": coverage_card(""),
        "fresh": org.galaxy.editor.freshness(),
        "endpoints": list(ENDPOINTS),
        "field": [dict(p) for p in SOTA_POINTERS],
        "sota": sota_card("", G=org.G),
        "laws": laws,
        "quality": quality,
        "latest_repair": latest_repair,
        "repair_view": repair_view,
        "stored_prose": laws["stored_prose"],
    }
