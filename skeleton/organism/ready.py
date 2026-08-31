"""Operator ready — seed if empty, then health + next + caps."""
from __future__ import annotations

from typing import Any, Dict


def ready_card(org=None, *, neo=None, walk: bool = False, n: int = 2) -> Dict[str, Any]:
    from skeleton.organism.caps import card as caps_card
    from skeleton.organism.health import health_card
    from skeleton.organism.mhc import mhc_card
    from skeleton.organism.next import hint
    from skeleton.organism.organismer import live_organismer
    from skeleton.organism.path10 import path_card
    from skeleton.social.seed import seed_field

    org = org or live_organismer()
    seeded = {"minted": 0, "skipped": 0}
    if not (org.galaxy.mesh.wiki.topics or {}):
        seeded = seed_field(org.galaxy)
    health = health_card(org, neo=neo)
    nxt = hint(org, neo=neo)
    walked = None
    if walk:
        from skeleton.organism.runloop import walk as do_walk
        walked = do_walk(org, neo=neo, n=n)
    return {
        "kind": "ready",
        "ok": health.get("ok"),
        "seed": seeded,
        "health": health,
        "next": nxt,
        "caps": caps_card(),
        "path10": path_card(org),
        "mhc": mhc_card(org),
        "walk": walked,
        "stored_prose": 0,
    }
