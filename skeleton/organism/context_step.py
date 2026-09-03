"""Context post-process — five brains, cage, decoder, editor decide.

memory → compiler → dream → distiller → editor.
Multi-turn codec when the stimulus has line breaks.
URL pointers ingest as citations, bodies stay off-shelf.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def run(org, stimulus: str = "", *, sleep: bool = False, neo=None) -> Dict[str, Any]:
    stim = (stimulus or "plan tensor ttk").strip()
    gxy: Dict[str, Any] = {}
    try:
        gxy = org.galaxy.pulse(stim, sleep=sleep)
    except Exception as exc:
        gxy = {"kind": "galaxy-pulse", "error": type(exc).__name__, "stored_prose": 0}
    ids: List[str] = list(gxy.get("atom_ids") or [])
    if not gxy.get("principle"):
        try:
            atom = org.galaxy.distiller.glean(stim)
            if atom is not None:
                gxy["principle"] = atom.to_dict()
                ids.append(atom.id)
        except Exception:
            pass
    longform: Dict[str, Any] = {}
    turns = [ln.strip() for ln in stim.splitlines() if ln.strip()]
    if len(turns) >= 2:
        try:
            longform = org.galaxy.ingest_turns(turns)
        except Exception:
            longform = {}
    social: Dict[str, Any] = {}
    if "http" in stim.lower():
        try:
            from skeleton.social.ingest import ingest
            social = ingest(stim)
            extra = ingest(" ".join(str(c.get("url") or "") for c in (social.get("cards") or []) if c.get("url")))
            social["bound"] = extra.get("n") or len(social.get("cards") or [])
        except Exception:
            social = {}
    cond: Dict[str, Any] = {}
    try:
        from skeleton.organism.conductor import decide
        cond = decide(org, neo=neo)
    except Exception:
        cond = {}
    cage: Dict[str, Any] = {}
    try:
        from skeleton.galaxy.quarantine import card as cage_card
        cage = cage_card()
    except Exception:
        cage = {}
    helix: Dict[str, Any] = {}
    try:
        from skeleton.organism.helix import stamp
        helix = stamp(org, {"phase": "ctx", "n": len(ids), "stored_prose": 0}, root=getattr(org, "root", None))
    except Exception:
        helix = {}
    out = {
        "kind": "context-step",
        "route": gxy.get("route"),
        "atom_ids": ids,
        "n": len(ids),
        "pulses": gxy.get("pulses") or 0,
        "decoded": bool(gxy.get("decoded")),
        "longform": longform.get("atoms") or 0,
        "structure": longform.get("structure") or {},
        "social_n": social.get("bound") or len(social.get("cards") or []),
        "conductor": {"code": cond.get("code"), "why": cond.get("why"), "horizon": cond.get("horizon")},
        "cage": {"denied": cage.get("denied"), "held": cage.get("held")},
        "helix": {"ok": 1 if helix else 0, "sense": (helix.get("sense") or {}).get("height")},
        "stored_prose": 0,
    }
    try:
        persist(out, root=getattr(org, "root", None))
    except Exception:
        pass
    return out


def path(root: Optional[Path] = None) -> Path:
    base = Path(root) if root else Path(".")
    return base / "chronicle" / "ctx.json"


def persist(card: Dict[str, Any], *, root: Optional[Path] = None) -> Path:
    p = path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    slim = {
        "kind": "context-step",
        "route": card.get("route"),
        "atom_ids": card.get("atom_ids") or [],
        "n": card.get("n") or 0,
        "conductor": card.get("conductor"),
        "stored_prose": 0,
    }
    p.write_text(json.dumps(slim, indent=2), encoding="utf-8")
    return p


def last(root: Optional[Path] = None) -> Dict[str, Any]:
    p = path(root)
    if not p.is_file():
        return {"kind": "context-step", "n": 0, "stored_prose": 0}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"kind": "context-step", "n": 0, "stored_prose": 0}
