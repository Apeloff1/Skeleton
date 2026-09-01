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

    def __init__(self, neo: Any) -> None:
        self.neo = neo
        self.traces: List[Dict[str, Any]] = []
        self.last_ref: Optional[Dict[str, Any]] = None
        self.last_improve: Optional[Dict[str, Any]] = None
        self.last_plan: Optional[Dict[str, Any]] = None
        self.position = 0

    def status(self) -> Dict[str, Any]:
        neo = self.neo
        st = neo.status() if hasattr(neo, "status") else {}
        if not isinstance(st, dict):
            st = {}
        g = _g(neo)
        toward = min(100.0, max(0.0, (g - 1.0) / 9.0 * 100.0))
        return {
            "G": round(g, 6),
            "target": 10.0,
            "toward_pct": round(toward, 1),
            "pulses": int(getattr(getattr(neo, "genos_engine", None), "pulses", 0) or 0),
            "epsilon": float(getattr(getattr(neo, "genos_engine", None), "epsilon", 0) or 0),
            "mouth": neo.speaking_name() if hasattr(neo, "speaking_name") else "neo",
            "dodeca": face_card(neo),
            "laws": list(LAWS),
            "refs": len(refs_index()),
            "traces": len(self.traces),
            "last_title": (self.last_ref or {}).get("title"),
            "cortex": st,
        }

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
        card = {
            "stimulus": stim[:240],
            "amalgam": amalgam[:400],
            "mouth": self.neo.speaking_name() if hasattr(self.neo, "speaking_name") else "neo",
            "G": round(_g(self.neo), 6),
            "law": "ok",
            "used_own": bool(getattr(trace, "used_own", False)),
            "hit": int(bool(hit.get("hit"))),
            "citation": (hit.get("ref") or {}).get("citation") if hit.get("hit") else None,
            "stored_prose": 0,
            "improve": improve,
            "think": _trace_dict(trace),
            "at": int(time.time() * 1000),
        }
        check({"kind": "speak", "dialect": card["amalgam"][:160], "title": (self.last_ref or {}).get("title") or ""})
        self.traces = [card, *self.traces][:24]
        return card

    def galaxy(self, stimulus: str = "", *, sleep: bool = False) -> Dict[str, Any]:
        from skeleton.galaxy.system import live_galaxy
        gxy = live_galaxy()
        if stimulus:
            card = gxy.pulse(stimulus, sleep=sleep)
        else:
            card = gxy.snapshot()
        card["G"] = round(_g(self.neo), 6)
        card["stored_prose"] = 0
        return card

    def organismer(self, stimulus: str = "", *, sleep: bool = False, live_cdx: bool = False) -> Dict[str, Any]:
        from skeleton.organism.organismer import live_organismer
        org = live_organismer()
        if stimulus:
            return org.step(stimulus, neo=self.neo, sleep=sleep, live_cdx=live_cdx)
        snap = org.snapshot()
        snap["G"] = round(_g(self.neo), 6) if _g(self.neo) > snap["G"] else snap["G"]
        return snap

    def social(self, stimulus: str = "") -> Dict[str, Any]:
        from skeleton.social.sota import sota_card
        return sota_card(stimulus, G=_g(self.neo))

    def product(self) -> Dict[str, Any]:
        from skeleton.organism.product import product_card
        card = product_card()
        card["mouth_G"] = round(_g(self.neo), 6)
        return card

    def health(self) -> Dict[str, Any]:
        from skeleton.organism.health import health_card
        return health_card(neo=self.neo)

    def doctor(self, fix: bool = False) -> Dict[str, Any]:
        from skeleton.organism.doctor import doctor_card
        return doctor_card(neo=self.neo, fix=fix)

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

    def sleep(self, force: bool = False, cue: str = "") -> Dict[str, Any]:
        from skeleton.organism.sleep import cycle
        return cycle(neo=self.neo, force=force, cue=cue)

    def forget(self, cue: str = "") -> Dict[str, Any]:
        from skeleton.galaxy.system import live_galaxy
        from skeleton.organism.forget import sweep
        return sweep(live_galaxy().mesh, cue=cue)

    def pulse(self, stimulus: str = "") -> Dict[str, Any]:
        from skeleton.organism.pulse import pulse
        return pulse(neo=self.neo, stimulus=stimulus)

    def walk(self, stimulus: str = "", n: int = 4) -> Dict[str, Any]:
        from skeleton.organism.runloop import walk
        return walk(neo=self.neo, stimulus=stimulus, n=n)

    def wiki(self, q: str = "") -> Dict[str, Any]:
        from skeleton.galaxy.query import run
        from skeleton.galaxy.system import live_galaxy
        return run(live_galaxy().mesh, q)

    def graph(self, cue: str = "") -> Dict[str, Any]:
        from skeleton.galaxy.graph import card as graph_card
        from skeleton.galaxy.system import live_galaxy
        return graph_card(live_galaxy().mesh, cue)

    def context(self, cue: str = "") -> Dict[str, Any]:
        from skeleton.organism.context_loop import assess
        from skeleton.organism.organismer import live_organismer
        return assess(live_organismer(), cue=cue, neo=self.neo)

    def banks(self) -> Dict[str, Any]:
        from skeleton.galaxy.banks import card
        from skeleton.galaxy.system import live_galaxy
        return card(live_galaxy().mesh, neo=self.neo)

    def caps(self) -> Dict[str, Any]:
        from skeleton.organism.caps import card
        return card()

    def lattice(self) -> Dict[str, Any]:
        from skeleton.galaxy.kv import archive
        from skeleton.galaxy.lattice import card as lattice_card
        from skeleton.galaxy.system import live_galaxy
        gxy = live_galaxy()
        out = lattice_card(gxy.mesh, neo=self.neo)
        out["kv"] = archive(gxy.mesh, neo=self.neo)
        return out

    def contact(self, stimulus: str = "") -> Dict[str, Any]:
        from skeleton.organism.teachers import glean_rule, sync
        from skeleton.galaxy.system import live_galaxy
        card = sync(self.neo, stimulus)
        card["rule"] = glean_rule(live_galaxy(), stimulus=stimulus, contact=card)
        card["G"] = round(_g(self.neo), 6)
        return card

    def plan(self, vision: str) -> Dict[str, Any]:
        from skeleton.cortex.era_bind import resolve
        card = resolve(vision)
        if card.get("hit"):
            self.last_ref = {
                "title": card.get("title"),
                "era": card.get("era"),
                "citation": card.get("citation"),
                "url": card.get("url"),
            }
        if hasattr(self.neo, "plan_build"):
            out = self.neo.plan_build(vision=vision)
            if isinstance(out, dict):
                out.setdefault("era", card.get("era"))
                out.setdefault("citation", card.get("citation"))
                out.setdefault("stored_prose", 0)
                self.last_plan = out
                return out
        pack = card.get("pack") or {}
        out = {
            "era": card.get("era"),
            "title": card.get("title"),
            "citation": card.get("citation"),
            "url": card.get("url"),
            "room_bias": pack.get("room_bias") or (pack.get("meta") or {}).get("philosophy") or card.get("era"),
            "primary_dps": card.get("primary_dps") or pack.get("primary_dps"),
            "stored_prose": 0,
            "law": "ok",
        }
        self.last_plan = out
        return out

    def cut(self, stimulus: str, *, rounds: int = 3, live: bool = False) -> Dict[str, Any]:
        from skeleton.cortex.perpendicular import cut as perp_cut
        card = perp_cut(self.neo, stimulus, rounds=rounds, live=live)
        if card.get("title"):
            self.last_ref = {
                "title": card.get("title"),
                "era": card.get("era"),
                "citation": card.get("citation"),
                "url": card.get("url"),
            }
        if card.get("improved"):
            self.last_improve = card.get("improve")
        self.traces = [card, *self.traces][:24]
        return card

    def genos(self, stimulus: str = "plan tensor ttk lattice soulslike") -> Dict[str, Any]:
        if hasattr(self.neo, "genos"):
            return self.neo.genos(stimulus)
        engine = getattr(self.neo, "genos_engine", None)
        if engine is not None and hasattr(engine, "pulse"):
            return engine.pulse(self.neo, stimulus=stimulus)
        return {"ok": 0, "reason": "no-genos"}

    def walk(self, steps: int = 1) -> Dict[str, Any]:
        steps = max(1, min(12, int(steps)))
        walked = []
        for i in range(steps):
            self.position = (self.position + 1 + (8847291 % 5)) % 12
            walked.append({"face_index": self.position, "face_name": FACES[self.position], "step": i})
        return {
            "seed": 8847291,
            "position": self.position,
            "face": FACES[self.position],
            "walk": walked,
            "card": face_card(self.neo),
        }

    def pick(self, index: int) -> Dict[str, Any]:
        self.position = int(index) % 12
        return {
            "seed": 8847291,
            "position": self.position,
            "face": FACES[self.position],
            "card": face_card(self.neo),
        }

    def snapshot(self) -> Dict[str, Any]:
        return {
            "status": self.status(),
            "last_ref": self.last_ref,
            "last_improve": self.last_improve,
            "last_plan": self.last_plan,
            "traces": list(self.traces[:8]),
            "position": self.position,
            "face": FACES[self.position],
        }


def live_deck():
    from skeleton.cortex.live import live_cortex
    return CommandDeck(live_cortex())
