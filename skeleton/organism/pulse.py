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
    gov: Dict[str, Any] = {}
    try:
        from skeleton.kernel.governor import tick as gov_tick
        gov = gov_tick()
    except Exception:
        gov = {}
    bank: Dict[str, Any] = {}
    try:
        from skeleton.kernel.orchestrator import Orchestrator
        from skeleton.kernel.bank import get, snapshot
        orch = get("orch") or Orchestrator()
        bank = orch.dispatch(stimulus or "plan tensor ttk")
        arena = get("ram")
        if arena is not None:
            from skeleton.kernel.meshmem import place
            bank["meshmem"] = place(org.galaxy.mesh, arena)
        bank["snapshot"] = snapshot()
    except Exception:
        bank = {}
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
        from skeleton.organism.sleep import cycle as sleep_cycle
        acted["sleep"] = sleep_cycle(org, neo=neo, force=True, cue=stimulus)
    else:
        from skeleton.organism.runloop import rotate_stimulus
        stim = rotate_stimulus(int(org.steps or 0), stimulus)
        acted["step"] = org.step(stim, neo=neo)
        acted["stimulus"] = stim.split()[0]
        try:
            from skeleton.organism.follow import grow
            acted["follow"] = grow(stim, root=getattr(org, "root", None))
        except Exception:
            pass
    rt: Dict[str, Any] = {}
    try:
        from skeleton.organism.runtime import dispatch as live_dispatch
        walked = live_dispatch(org, stimulus or acted.get("stimulus") or "", neo=neo)
        rt = {
            "n": walked.get("n"),
            "ctx_n": walked.get("ctx_n"),
            "profile": walked.get("profile"),
            "skip": walked.get("skip"),
        }
    except Exception:
        rt = {}
    return {
        "kind": "pulse",
        "next": nxt,
        "acted": acted,
        "gov": gov,
        "bank": bank,
        "runtime": rt,
        "G": round(org.G, 6),
        "stored_prose": 0,
    }
