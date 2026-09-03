"""Organism runtime DAG.

Kernel orch is admit→quota→place→prefill→decode→check→stock→reclaim
over tensors. This is the same graph over the house:

  admit   laws
  quota   caps / pressure
  place   scope compose
  prefill five-brain context step
  decode  polish
  check   cage + prose
  stock   follow
  reclaim dump if due

One walk. Tight profile skips place/reclaim. Conductor is consulted,
never executed as a nested week.
"""
from __future__ import annotations

from typing import Any, Dict, List


EDGES = {
    "admit": ["quota"],
    "quota": ["place"],
    "place": ["prefill"],
    "prefill": ["decode"],
    "decode": ["check"],
    "check": ["stock"],
    "stock": ["reclaim"],
    "reclaim": [],
}


def dispatch(org=None, stimulus: str = "", *, neo=None) -> Dict[str, Any]:
    from skeleton.organism.organismer import live_organismer

    org = org or live_organismer()
    stim = stimulus or "plan tensor ttk"
    profile = "mobile"
    try:
        from skeleton.kernel.profiles import card as profiles_card
        profile = str(profiles_card().get("profile") or "mobile")
    except Exception:
        profile = "mobile"
    skip = {"place", "reclaim"} if profile == "tight" else set()
    pressure = 0.0
    try:
        from skeleton.organism.caps import card as caps_card
        pressure = float(caps_card().get("pressure") or 0)
    except Exception:
        pressure = 0.0
    if pressure >= 0.82:
        skip.update({"prefill", "decode", "place"})
    trace: List[Dict[str, Any]] = []
    ctx: Dict[str, Any] = {}
    for stage in EDGES:
        if stage in skip:
            trace.append({"stage": stage, "skipped": 1})
            continue
        card = _stage(stage, org, stim, neo=neo, ctx=ctx)
        if stage == "prefill":
            ctx = card
        trace.append({"stage": stage, "kind": card.get("kind"), "ok": card.get("ok", 1)})
    out = {
        "kind": "runtime",
        "profile": profile,
        "n": len([t for t in trace if not t.get("skipped")]),
        "skip": sorted(skip),
        "trace": trace,
        "ctx_n": ctx.get("n") or 0,
        "stored_prose": 0,
    }
    try:
        persist(out, root=getattr(org, "root", None))
    except Exception:
        pass
    return out


def persist(card: Dict[str, Any], *, root=None):
    import json
    from pathlib import Path
    base = Path(root) if root else Path(".")
    p = base / "chronicle" / "runtime.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    slim = {
        "kind": "runtime",
        "profile": card.get("profile"),
        "n": card.get("n"),
        "skip": card.get("skip"),
        "ctx_n": card.get("ctx_n"),
        "stored_prose": 0,
    }
    p.write_text(json.dumps(slim, indent=2), encoding="utf-8")
    return p


def last(root=None) -> Dict[str, Any]:
    import json
    from pathlib import Path
    base = Path(root) if root else Path(".")
    p = base / "chronicle" / "runtime.json"
    if not p.is_file():
        return {"kind": "runtime", "n": 0, "stored_prose": 0}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"kind": "runtime", "n": 0, "stored_prose": 0}


def _stage(name: str, org, stim: str, *, neo=None, ctx: Dict[str, Any]) -> Dict[str, Any]:
    if name == "admit":
        from skeleton.organism.laws import laws_card
        card = laws_card(org.galaxy.mesh)
        return {"kind": "admit", "ok": card.get("ok"), "prose": card.get("stored_prose")}
    if name == "quota":
        from skeleton.organism.caps import card as caps_card
        cap = caps_card()
        return {"kind": "quota", "ok": 1, "pressure": cap.get("pressure"), "tier": cap.get("tier")}
    if name == "place":
        from skeleton.organism.scope import compose
        q = compose(org, neo=neo)
        return {"kind": "place", "ok": 1, "queue": q.get("queue"), "rot": (q.get("rot") or {}).get("verdict")}
    if name == "prefill":
        from skeleton.organism.context_step import run as ctx_run
        return ctx_run(org, stim, neo=neo)
    if name == "decode":
        from skeleton.organism.context_step import polish
        return polish(org, stim)
    if name == "check":
        from skeleton.galaxy.quarantine import card as cage_card
        from skeleton.organism.laws import scan_prose
        cage = cage_card()
        prose = 0
        try:
            prose = int(scan_prose(org.galaxy.mesh) or 0)
        except Exception:
            prose = 0
        ok = int(prose == 0)
        return {"kind": "check", "ok": ok, "prose": prose, "cage": cage.get("denied")}
    if name == "stock":
        try:
            from skeleton.organism.follow import grow
            return grow(stim, root=getattr(org, "root", None))
        except Exception:
            return {"kind": "stock", "ok": 1}
    if name == "reclaim":
        try:
            from skeleton.organism.chronicle.dump import due, dump
            if due(getattr(org, "root", None)):
                return dump(getattr(org, "root", None))
        except Exception:
            pass
        return {"kind": "reclaim", "ok": 1, "due": 0}
    return {"kind": name, "ok": 1}
