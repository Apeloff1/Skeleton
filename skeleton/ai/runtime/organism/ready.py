"""Operator ready — seed if empty, then health + next + caps."""
from __future__ import annotations

from typing import Any, Dict


def ready_card(org=None, *, neo=None, walk: bool = False, n: int = 2, fix: bool = False) -> Dict[str, Any]:
    from skeleton.organism.caps import card as caps_card
    from skeleton.organism.doctor import doctor_card
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
    if fix:
        from skeleton.organism.laws import clip_fat, persist_clip
        clip_fat(org.galaxy.mesh)
        persist_clip(org)
    health = health_card(org, neo=neo)
    nxt = hint(org, neo=neo)
    walked = None
    season = None
    if walk:
        from skeleton.organism.runloop import walk as do_walk
        walked = do_walk(org, neo=neo, n=n)
        from skeleton.kernel.season import run as season_run
        season = season_run("plan tensor ttk", n=n)
    return {
        "kind": "ready",
        "ok": health.get("ok"),
        "seed": seeded,
        "health": health,
        "next": nxt,
        "caps": caps_card(),
        "path10": path_card(org),
        "mhc": mhc_card(org),
        "doctor": doctor_card(org, neo=neo, fix=False),
        "satellites": __import__("skeleton.organism.satellites", fromlist=["satellites_card"]).satellites_card(org, cue="memory graph"),
        "nervous": __import__("skeleton.organism.nervous", fromlist=["nervous_card"]).nervous_card(org, neo=neo),
        "chronicle": __import__("skeleton.organism.chronicle", fromlist=["card"]).card(org, cue="memory graph"),
        "scope": __import__("skeleton.organism.scope", fromlist=["card"]).card(org, neo=neo),
        "kernels": __import__("skeleton.kernel.profiles", fromlist=["card"]).card(),
        "follow": __import__("skeleton.organism.follow", fromlist=["card"]).card(getattr(org, "root", None)),
        "helix_agree": __import__("skeleton.organism.helix_consensus", fromlist=["agree"]).agree(getattr(org, "root", None)),
        "walk": walked,
        "season": season,
        "cage": __import__("skeleton.galaxy.quarantine", fromlist=["card"]).card(),
        "observe": __import__("skeleton.organism.observe", fromlist=["card"]).card(getattr(org, "root", None)),
        "runtime_n": __import__("skeleton.organism.runtime", fromlist=["last"]).last(getattr(org, "root", None)).get("n") or 0,
        "stacks": __import__("skeleton.organism.stacks", fromlist=["card"]).card(getattr(org, "root", None)),
        "mix": __import__("skeleton.organism.context_step", fromlist=["mix_card"]).mix_card(getattr(org, "root", None)),
        "stored_prose": health.get("stored_prose"),
    }
