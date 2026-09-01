"""Two-phase sleep. Consolidation is gated, not every step.

NREM: clip fat dialect, trim to cap, write-back absorb, editor refresh.
REM: DreamBrain replay + mouth sleep_cycle + reconstruction forest.

Gate cites 2605.12978 — consolidation after every interaction degrades
utility. House fires only when idle cadence is due or the operator
forces it. Cite 2606.03979 / 2604.20943 as the NREM+REM split.
No paper bodies. No Merge/Abstract/Rewrite imports.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


CITE = (
    "https://arxiv.org/abs/2606.03979",
    "https://arxiv.org/abs/2604.20943",
    "https://arxiv.org/abs/2605.12978",
)


def due(org, *, cadence: Optional[int] = None) -> bool:
    from skeleton.organism.idle import due as idle_due
    last = int(getattr(org, "last_dream_step", 0) or 0)
    return idle_due(int(org.steps or 0), last, cadence=cadence)


def nrem(org) -> Dict[str, Any]:
    from skeleton.organism.caps import adapt, trim_mesh
    from skeleton.organism.laws import clip_fat, persist_clip
    from skeleton.organism.writeback import absorb

    from skeleton.organism.forget import sweep
    clip = clip_fat(org.galaxy.mesh)
    clip.update(persist_clip(org))
    forgotten = sweep(org.galaxy.mesh)
    helix = None
    if getattr(org, "persist_on", False):
        from skeleton.organism.helix import stamp as helix_stamp
        helix = helix_stamp(org, {"kind": "nrem", "topic": "sleep", "G": getattr(org, "G", None)},
                            root=getattr(org, "root", None))
    return {
        "kind": "nrem",
        "adapt": adapt(),
        "trim": trim_mesh(org.galaxy.mesh),
        "clip": clip,
        "absorb": absorb(org.galaxy.mesh),
        "forget": forgotten,
        "helix": helix,
        "refresh": org.galaxy.editor.refresh(),
        "stored_prose": clip.get("stored_prose", 0),
    }


def rem(org, *, neo=None, cue: str = "") -> Dict[str, Any]:
    from skeleton.organism.context_loop import assess
    from skeleton.organism.idle import run as idle_run

    from skeleton.organism.forget import reconsolidate
    cue = cue or "memory graph"
    return {
        "kind": "rem",
        "idle": idle_run(org.galaxy, neo),
        "loop": assess(org, cue=cue, neo=neo),
        "reconsolidate": reconsolidate(org.galaxy.mesh, cue),
        "stored_prose": 0,
    }


def cycle(org=None, *, neo=None, force: bool = False, cue: str = "",
          persist: Optional[bool] = None) -> Dict[str, Any]:
    from skeleton.organism.organismer import live_organismer

    org = org or live_organismer()
    if persist is not None:
        org.persist_on = bool(persist)
    gated = due(org)
    if not force and not gated:
        return {
            "kind": "sleep",
            "ran": 0,
            "why": "gated",
            "due": False,
            "cite": list(CITE),
            "stored_prose": 0,
        }
    n = nrem(org)
    r = rem(org, neo=neo, cue=cue)
    org.last_dream_step = int(org.steps or 0)
    return {
        "kind": "sleep",
        "ran": 1,
        "why": "force" if force else "due",
        "due": True,
        "nrem": n,
        "rem": r,
        "cite": list(CITE),
        "stored_prose": int(n.get("stored_prose") or 0),
    }
