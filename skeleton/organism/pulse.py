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
        try:
            import hashlib
            from skeleton.organism.runtime import last as rt_last
            h = hashlib.sha256(stim.encode("utf-8")).hexdigest()[:16]
            if rt_last(getattr(org, "root", None)).get("hash") == h:
                from skeleton.organism.fieldwalk import unbound, claim
                nxt = (unbound(getattr(org, "root", None)) or [None])[0]
                if nxt:
                    claimed = claim(org, nxt, root=getattr(org, "root", None))
                    stim = f"{nxt['topic']} {nxt['url']}"
                    acted["rotated"] = 1
                    acted["bound"] = claimed.get("topic")
                    acted["cursor"] = claimed
                else:
                    stim = rotate_stimulus(int(org.steps or 0) + 1, "")
                    acted["rotated"] = 1
        except Exception:
            pass
        acted["stimulus"] = stim.split()[0] if stim else ""
        try:
            from skeleton.kernel.ops.thinkmix import thinkmix
            tm = thinkmix(stim, profile=str(gov.get("profile") or "mobile"))
            acted["think"] = tm.get("open")
            acted["loop_family"] = tm.get("family") or ""
            if tm.get("open"):
                from skeleton.organism.loop_log import record
                record(
                    {"open": 1, "fire": 1, "family": tm.get("run") or tm.get("family"), "r": tm.get("r") or 2},
                    root=getattr(org, "root", None),
                )
        except Exception:
            acted["think"] = 0
        rt_early: Dict[str, Any] = {}
        try:
            from skeleton.organism.runtime import dispatch as live_dispatch
            walked = live_dispatch(org, stim, neo=neo)
            rt_early = {
                "n": walked.get("n"),
                "ctx_n": walked.get("ctx_n"),
                "profile": walked.get("profile"),
                "skip": walked.get("skip"),
                "kernel_n": walked.get("kernel_n"),
            }
        except Exception:
            rt_early = {}
        hit = 0
        try:
            from skeleton.organism.context_step import last as ctx_last
            hit = int(ctx_last(getattr(org, "root", None)).get("reused") or 0)
        except Exception:
            hit = 0
        if hit:
            acted["step"] = {"skipped": "ctx-hit"}
        else:
            acted["step"] = org.step(stim, neo=neo)
            try:
                from skeleton.organism.follow import grow
                acted["follow"] = grow(stim, root=getattr(org, "root", None))
            except Exception:
                pass
        rt = rt_early
    if code in {"tighten", "hold", "bind-source", "dream"}:
        rt = {}
    if not rt:
        try:
            from skeleton.organism.runtime import dispatch as live_dispatch
            walked = live_dispatch(org, stimulus or acted.get("stimulus") or "", neo=neo)
            rt = {
                "n": walked.get("n"),
                "ctx_n": walked.get("ctx_n"),
                "profile": walked.get("profile"),
                "skip": walked.get("skip"),
                "kernel_n": walked.get("kernel_n"),
            }
        except Exception:
            rt = {}
    return {
        "kind": "pulse",
        "next": nxt,
        "acted": acted,
        "gov": gov,
        "runtime": rt,
        "G": round(org.G, 6),
        "stored_prose": 0,
    }
