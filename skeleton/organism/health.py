"""Operator health — one card, fail-closed.

ok=1 when stored_prose stays 0, pressure is under 0.90, and the
error ratio is under 0.35. Lattice and KV are summaries, not dumps.
"""
from __future__ import annotations

from typing import Any, Dict


def health_card(org=None, *, neo=None) -> Dict[str, Any]:
    from skeleton.galaxy.kv import archive
    from skeleton.galaxy.lattice import card as lattice_card
    from skeleton.organism.caps import card as caps_card
    from skeleton.organism.organismer import live_organismer
    from skeleton.social.sources import SOTA_POINTERS

    org = org or live_organismer()
    caps = caps_card()
    lat = lattice_card(org.galaxy.mesh, neo=neo)
    kv = archive(org.galaxy.mesh, neo=neo)
    steps = max(1, int(org.steps or 0))
    err_ratio = float(org.errors) / steps
    pressure = float(caps.get("pressure") or 0.0)
    from skeleton.organism.laws import scan_prose
    prose = scan_prose(org.galaxy.mesh)
    ok = int(pressure < 0.90 and err_ratio < 0.35 and prose == 0)
    from skeleton.organism.journal import tail
    from skeleton.organism.next import hint
    nxt = hint(org, neo=neo)
    return {
        "kind": "health",
        "ok": ok,
        "G": round(org.G, 6),
        "toward_10x_pct": round(org.toward, 2),
        "steps": org.steps,
        "errors": org.errors,
        "error_ratio": round(err_ratio, 4),
        "pressure": pressure,
        "caps_action": caps.get("action"),
        "tier": caps.get("tier"),
        "atoms": sum(len(lib.shelf) for lib in org.galaxy.mesh.brains.values()),
        "wiki_topics": len(org.galaxy.mesh.wiki.topics),
        "lattice": lat.get("ascii"),
        "kv_bound": kv.get("bound"),
        "kv_n": kv.get("n"),
        "field_n": len(SOTA_POINTERS),
        "next": nxt.get("code"),
        "next_why": nxt.get("why"),
        "rot": nxt.get("rot"),
        "forest_n": nxt.get("forest_n"),
        "journal": tail(4, root=getattr(org, "root", None)),
        "stored_prose": prose,
        "helix": __import__("skeleton.organism.helix", fromlist=["card"]).card(getattr(org, "root", None)),
        "orch": _orch_stamp(),
        "coverage": __import__("skeleton.kernel.coverage", fromlist=["card"]).card().get("pct_obl"),
        "gov": __import__("skeleton.kernel.persist", fromlist=["load_gov"]).load_gov(),
        "witness": __import__("skeleton.kernel.witness", fromlist=["card"]).card(),
        "cage": __import__("skeleton.galaxy.quarantine", fromlist=["card"]).card(),
        "field_score": __import__("skeleton.social.coverage", fromlist=["coverage_card"]).coverage_card().get("score"),
        "rot": __import__("skeleton.organism.rotctx", fromlist=["card"]).card(),
    }


def _orch_stamp() -> Dict[str, Any]:
    try:
        from skeleton.kernel.bank import get
        o = get("orch")
        last = o.last if o is not None else {}
        return {
            "runs": last.get("runs") or 0,
            "n": last.get("n") or 0,
            "profile": (last.get("route") or {}).get("profile"),
            "decode_n": (last.get("route") or {}).get("decode_n"),
            "stored_prose": 0,
        }
    except Exception:
        return {"runs": 0, "n": 0, "stored_prose": 0}
