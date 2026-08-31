"""Obey the next code — seed, dream, contact, or step.

tighten/hold do not write. bind-source seeds. dream runs idle.
contact + pulse run one organismer step.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def pulse(org=None, *, neo=None, stimulus: str = "", persist: Optional[bool] = None) -> Dict[str, Any]:
    from skeleton.organism.next import hint
    from skeleton.organism.organismer import live_organismer
    from skeleton.social.seed import seed_field

    org = org or live_organismer()
    if persist is not None:
        org.persist_on = bool(persist)
    nxt = hint(org, neo=neo)
    code = str(nxt.get("code") or "pulse")
    acted: Dict[str, Any] = {"code": code}
    if code == "tighten":
        from skeleton.organism.caps import adapt, trim_mesh
        from skeleton.organism.laws import clip_fat, persist_clip
        acted["adapt"] = adapt()
        acted["trim"] = trim_mesh(org.galaxy.mesh)
        acted["clip"] = clip_fat(org.galaxy.mesh)
        acted["clip"].update(persist_clip(org))
    elif code == "hold":
        acted["held"] = 1
    elif code == "bind-source":
        acted["seed"] = seed_field(org.galaxy)
    elif code == "dream":
        from skeleton.organism.caps import trim_mesh
        from skeleton.organism.idle import run as idle_run
        from skeleton.organism.laws import clip_fat, persist_clip
        acted["idle"] = idle_run(org.galaxy, neo)
        acted["trim"] = trim_mesh(org.galaxy.mesh)
        acted["clip"] = clip_fat(org.galaxy.mesh)
        acted["clip"].update(persist_clip(org))
        acted["refresh"] = org.galaxy.editor.refresh()
        org.last_dream_step = org.steps
    else:
        from skeleton.organism.runloop import rotate_stimulus
        stim = rotate_stimulus(int(org.steps or 0), stimulus)
        acted["step"] = org.step(stim, neo=neo)
        acted["stimulus"] = stim.split()[0]
    return {
        "kind": "pulse",
        "next": nxt,
        "acted": acted,
        "G": round(org.G, 6),
        "stored_prose": 0,
    }
