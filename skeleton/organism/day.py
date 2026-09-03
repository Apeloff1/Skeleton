"""Day — one growth unit: seed, compose, enact under caps.

Season is kernel-only. Day is the organism verb: field pointers,
scope queue, enact heads, follow growth, rot persist.
Stops on rot, pressure ≥ 0.90, or a failed enact.
"""
from __future__ import annotations

from typing import Any, Dict, List


def run(org=None, *, n: int = 0, neo=None) -> Dict[str, Any]:
    from skeleton.organism.caps import live as live_caps
    from skeleton.organism.organismer import live_organismer
    from skeleton.organism.scope import compose, enact
    from skeleton.social.seed import seed_field

    org = org or live_organismer()
    seed = seed_field(org.galaxy)
    field: Dict[str, Any] = {}
    try:
        from skeleton.organism.fieldwalk import walk as field_walk
        field = field_walk(org, root=getattr(org, "root", None))
    except Exception:
        field = {}
    composed = compose(org, neo=neo)
    ambition = int(n or composed.get("ambition") or 2)
    ambition = max(1, min(4, ambition))
    heads: List[str] = []
    stopped = ""
    for _ in range(ambition):
        pressure = float(getattr(live_caps(), "pressure", 0) or 0)
        if pressure >= 0.90:
            stopped = "pressure"
            break
        rot = composed.get("rot") or {}
        if str(rot.get("verdict") or "") == "rot" and heads:
            stopped = "rot"
            break
        card = enact(org, neo=neo)
        heads.append(str(card.get("head") or "pulse"))
        try:
            from skeleton.organism.follow import grow
            grow(" ".join(heads), root=getattr(org, "root", None))
        except Exception:
            pass
        composed = compose(org, neo=neo)
    out = {
        "kind": "day",
        "seed": {"minted": seed.get("minted"), "wiki_topics": seed.get("wiki_topics")},
        "heads": heads,
        "n": len(heads),
        "asked": ambition,
        "stopped": stopped,
        "coverage": composed.get("coverage"),
        "rot": (composed.get("rot") or {}).get("verdict"),
        "field": {"ok": field.get("ok"), "topics": field.get("topics"), "pct": (field.get("inventory") or {}).get("field_pct")},
        "stored_prose": 0,
    }
    try:
        _persist(out, root=getattr(org, "root", None))
    except Exception:
        pass
    return out


def _persist(card: Dict[str, Any], *, root=None) -> None:
    import json
    from pathlib import Path
    base = Path(root) if root else Path(".")
    p = base / "chronicle" / "day.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    slim = {k: card.get(k) for k in ("kind", "heads", "n", "asked", "stopped", "coverage", "rot", "field", "stored_prose")}
    p.write_text(json.dumps(slim, indent=2), encoding="utf-8")
