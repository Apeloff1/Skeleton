"""Command deck — the organism you can speak through.

Unifies think → refer → improve → ascend → plan → dodeca → genos
into one instrument. Laws gate every write. Pointers only.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from skeleton.cortex.dodeca import FACES, face_card
from skeleton.cortex.laws import LAWS, check
from skeleton.cortex.refs import index as refs_index
from skeleton.cortex.refs import refer


def _g(neo) -> float:
    return float(getattr(getattr(neo, "genos_engine", None), "G", 1.0) or 1.0)


def _trace_dict(trace: Any) -> Dict[str, Any]:
    if trace is None:
        return {}
    if hasattr(trace, "to_dict"):
        return trace.to_dict()
    if isinstance(trace, dict):
        return dict(trace)
    return {"text": str(trace)}


class CommandDeck:
    """Live instrument over a JeevesCortex (or any neo with the same mouth)."""

    def __init__(self, neo: Any, *, root=None) -> None:
        self.neo = neo
        self.traces: List[Dict[str, Any]] = []
        self.last_ref: Optional[Dict[str, Any]] = None
        self.last_improve: Optional[Dict[str, Any]] = None
        self.last_plan: Optional[Dict[str, Any]] = None
        self.position = 0
        self.root = root

    def status(self) -> Dict[str, Any]:
        neo = self.neo
        st = neo.status() if hasattr(neo, "status") else {}
        if not isinstance(st, dict):
            st = {}
        g = _g(neo)
        toward = min(100.0, max(0.0, (g - 1.0) / 9.0 * 100.0))
        return {"G": round(g, 6), "target": 10.0, "toward_pct": round(toward, 1), "pulses": int(getattr(getattr(neo, "genos_engine", None), "pulses", 0) or 0), "epsilon": float(getattr(getattr(neo, "genos_engine", None), "epsilon", 0) or 0), "mouth": neo.speaking_name() if hasattr(neo, "speaking_name") else "neo", "dodeca": face_card(neo), "laws": list(LAWS), "refs": len(refs_index()), "traces": len(self.traces), "last_title": (self.last_ref or {}).get("title"), "cortex": st}

    def refer(self, stimulus: str, *, live: bool = False) -> Dict[str, Any]:
        out = refer(stimulus, live=live)
        if out.get("hit"):
            self.last_ref = out.get("ref")
        return out

    def improve(self, stimulus: str, *, rounds: int = 6) -> Dict[str, Any]:
        if hasattr(self.neo, "improve"):
            card = self.neo.improve(stimulus, rounds=rounds)
        else:
            from skeleton.cortex.improve import improve as improve_fn
            card = improve_fn(self.neo, stimulus, rounds=rounds)
        if isinstance(card, dict) and card.get("improved"):
            self.last_improve = card
        return card if isinstance(card, dict) else {"improved": 0}

    def ascend(self, stimulus: str, *, rounds: int = 6) -> Dict[str, Any]:
        if hasattr(self.neo, "ascend"):
            card = self.neo.ascend(stimulus, rounds=rounds)
        else:
            card = self.improve(stimulus, rounds=rounds)
            if isinstance(card, dict) and card.get("improved"):
                card = {**card, "kind": "ascend"}
        if isinstance(card, dict) and card.get("improved"):
            self.last_improve = card
        return card if isinstance(card, dict) else {"improved": 0}

    def speak(self, stimulus: str) -> Dict[str, Any]:
        stim = stimulus or ""
        hit = self.refer(stim)
        improve: Optional[Dict[str, Any]] = None
        if "like " in stim.lower() and hit.get("hit"):
            improve = self.ascend(stim, rounds=6)
        trace = None
        if hasattr(self.neo, "think"):
            trace = self.neo.think(stim)
        amalgam = ""
        if hit.get("hit"):
            ref = hit.get("ref") or {}
            amalgam = f"HOUSE {ref.get('era')} · {ref.get('dialect') or ''}"
        elif trace is not None and hasattr(trace, "amalgam"):
            amalgam = getattr(trace.amalgam, "text", "") or ""
        card = {"stimulus": stim[:240], "amalgam": amalgam[:400], "mouth": self.neo.speaking_name() if hasattr(self.neo, "speaking_name") else "neo", "G": round(_g(self.neo), 6), "law": "ok", "used_own": bool(getattr(trace, "used_own", False)), "hit": int(bool(hit.get("hit"))), "citation": (hit.get("ref") or {}).get("citation") if hit.get("hit") else None, "stored_prose": 0, "improve": improve, "think": _trace_dict(trace), "at": int(time.time() * 1000)}
        check({"kind": "speak", "dialect": card["amalgam"][:160], "title": (self.last_ref or {}).get("title") or ""})
        self.traces = [card, *self.traces][:24]
        return card

    def product(self) -> Dict[str, Any]:
        from skeleton.organism.product import product_card
        card = product_card()
        card["mouth_G"] = round(_g(self.neo), 6)
        return card

    def failures(self) -> Dict[str, Any]:
        from skeleton.organism.failure_card import failure_card
        return failure_card(root=self.root)

    def repairs(self) -> Dict[str, Any]:
        from skeleton.organism.repair_card import repair_card
        return repair_card(root=self.root)

    def activity(self) -> Dict[str, Any]:
        from skeleton.organism.activity_card import activity_card
        return activity_card(root=self.root)

    def recurring(self) -> Dict[str, Any]:
        from skeleton.organism.recurring_card import recurring_card
        return recurring_card(root=self.root)

    def health(self) -> Dict[str, Any]:
        from skeleton.organism.health import health_card
        return health_card(neo=self.neo)

    def doctor(self, fix: bool = False) -> Dict[str, Any]:
        from skeleton.organism.doctor import doctor_card
        return doctor_card(neo=self.neo, fix=fix)

    def satellites(self, cue: str = "") -> Dict[str, Any]:
        from skeleton.organism.organismer import live_organismer
        from skeleton.organism.satellites import satellites_card
        return satellites_card(live_organismer(), cue=cue)

    def nervous(self) -> Dict[str, Any]:
        from skeleton.organism.nervous import nervous_card
        from skeleton.organism.organismer import live_organismer
        return nervous_card(live_organismer(), neo=self.neo)

    def chronicle(self, cue: str = "") -> Dict[str, Any]:
        from skeleton.organism.chronicle import card
        from skeleton.organism.organismer import live_organismer
        return card(live_organismer(), cue=cue)

    def dump(self, force: bool = False) -> Dict[str, Any]:
        from skeleton.organism.chronicle.dump import dump
        from skeleton.organism.organismer import live_organismer
        return dump(live_organismer().root, force=force)

    def laws(self) -> Dict[str, Any]:
        from skeleton.organism.laws import laws_card
        from skeleton.galaxy.system import live_galaxy
        return laws_card(live_galaxy().mesh)

    def next(self) -> Dict[str, Any]:
        from skeleton.organism.next import hint
        from skeleton.organism.organismer import live_organismer
        return hint(live_organismer(), neo=self.neo)

    def seed(self) -> Dict[str, Any]:
        from skeleton.galaxy.system import live_galaxy
        from skeleton.social.seed import seed_field
        return seed_field(live_galaxy())

    def field(self) -> Dict[str, Any]:
        from skeleton.social.field import field_card
        return field_card()

    def ready(self, walk: bool = False, n: int = 2, fix: bool = False) -> Dict[str, Any]:
        from skeleton.organism.ready import ready_card
        return ready_card(neo=self.neo, walk=walk, n=n, fix=fix)

    def pulse(self, stimulus: str = "") -> Dict[str, Any]:
        from skeleton.organism.pulse import pulse
        return pulse(neo=self.neo, stimulus=stimulus)

    def walk(self, stimulus: str = "", n: int = 4) -> Dict[str, Any]:
        from skeleton.organism.runloop import walk
        return walk(neo=self.neo, stimulus=stimulus, n=n)

    def snapshot(self) -> Dict[str, Any]:
        return {"status": self.status(), "last_ref": self.last_ref, "last_improve": self.last_improve, "last_plan": self.last_plan, "traces": list(self.traces[:8]), "position": self.position, "face": FACES[self.position]}


def live_deck():
    from skeleton.cortex.live import live_cortex
    return CommandDeck(live_cortex())
