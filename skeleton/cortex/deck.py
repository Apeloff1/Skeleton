"""Command deck — the organism you can speak through.

Unifies think → refer → improve → ascend → plan → dodeca → genos
into one instrument. Laws gate every write. Pointers only.

Now includes repair orchestrator integration for multi-pass repairs,
telemetry, learned policy, and session diagnostics.
Also includes adaptive policy for self-tuning thresholds.
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

    def speak(self, stimulus: str) -> Dict[str, Any]:
        stim = stimulus or ""
        hit = self.refer(stim)
        trace = None
        if hasattr(self.neo, "think"):
            trace = self.neo.think(stim)
        amalgam = ""
        if hit.get("hit"):
            ref = hit.get("ref") or {}
            amalgam = f"HOUSE {ref.get('era')} · {ref.get('dialect') or ''}"
        elif trace is not None and hasattr(trace, "amalgam"):
            amalgam = getattr(trace.amalgam, "text", "") or ""
        card = {"stimulus": stim[:240], "amalgam": amalgam[:400], "mouth": self.neo.speaking_name() if hasattr(self.neo, "speaking_name") else "neo", "G": round(_g(self.neo), 6), "law": "ok", "used_own": bool(getattr(trace, "used_own", False)), "hit": int(bool(hit.get("hit"))), "citation": (hit.get("ref") or {}).get("citation") if hit.get("hit") else None, "stored_prose": 0, "think": _trace_dict(trace), "at": int(time.time() * 1000)}
        check({"kind": "speak", "dialect": card["amalgam"][:160], "title": (self.last_ref or {}).get("title") or ""})
        self.traces = [card, *self.traces][:24]
        return card

    def product(self) -> Dict[str, Any]:
        from skeleton.organism.product import product_card
        card = product_card()
        card["mouth_G"] = round(_g(self.neo), 6)
        return card

    def failures(self, *, surface: str = "") -> Dict[str, Any]:
        from skeleton.organism.failure_card import failure_card
        return failure_card(root=self.root, surface=surface)

    def repairs(self, *, surface: str = "") -> Dict[str, Any]:
        from skeleton.organism.repair_card import repair_card
        return repair_card(root=self.root, surface=surface)

    def activity(self, *, surface: str = "", kind: str = "", limit: int = 8) -> Dict[str, Any]:
        from skeleton.organism.activity_card import activity_card
        return activity_card(root=self.root, surface=surface, kind=kind, limit=limit)

    def recurring(self, *, surface: str = "") -> Dict[str, Any]:
        from skeleton.organism.recurring_card import recurring_card
        return recurring_card(root=self.root, surface=surface)

    def policy(self) -> Dict[str, Any]:
        from skeleton.organism.policy_control_card import policy_control_card
        return policy_control_card(root=self.root)

    def threshold(self, *, surface: str = "") -> Dict[str, Any]:
        from skeleton.organism.policy_card import threshold_card
        return threshold_card(root=self.root, surface=surface)

    def set_threshold(self, surface: str, value: float) -> Dict[str, Any]:
        from skeleton.organism.policy_card import set_threshold_card
        return set_threshold_card(surface, value, root=self.root)

    def set_repair_enabled(self, surface: str, enabled: bool) -> Dict[str, Any]:
        from skeleton.organism.policy_card import set_repair_enabled_card
        return set_repair_enabled_card(surface, enabled, root=self.root)

    def set_repair_class(self, name: str, enabled: bool) -> Dict[str, Any]:
        from skeleton.organism.policy_card import set_repair_class_card
        return set_repair_class_card(name, enabled, root=self.root)

    # Repair orchestrator integration
    def repair_sessions(self, *, surface: str = "", limit: int = 8) -> Dict[str, Any]:
        from skeleton.intelligence.repair_autonomy import repair_session_card
        return repair_session_card(surface=surface, root=self.root, limit=limit)

    def repair_effectiveness(self, *, surface: str = "") -> Dict[str, Any]:
        from skeleton.intelligence.repair_autonomy import repair_effectiveness
        return repair_effectiveness(surface=surface, root=self.root)

    def repair_telemetry(self, *, surface: str = "", limit: int = 16) -> Dict[str, Any]:
        from skeleton.intelligence.repair_telemetry import telemetry_card
        return telemetry_card(surface=surface, root=self.root, limit=limit)

    def repair_errors(self, *, surface: str = "") -> Dict[str, Any]:
        from skeleton.intelligence.repair_telemetry import error_summary
        return error_summary(surface=surface, root=self.root)

    def learned_policy(self) -> Dict[str, Any]:
        from skeleton.intelligence.learned_repair import learned_policy_card
        return learned_policy_card(root=self.root)

    def repair_orchestrator(self) -> Dict[str, Any]:
        from skeleton.intelligence.repair_orchestrator import repair_orchestrator_card
        return repair_orchestrator_card(root=self.root)

    # Adaptive policy integration
    def adaptive_policy(self) -> Dict[str, Any]:
        from skeleton.intelligence.adaptive_policy import adaptive_policy_card
        return adaptive_policy_card(root=self.root)

    def adapt_surface(self, surface: str, *, dry_run: bool = False) -> Dict[str, Any]:
        from skeleton.intelligence.adaptive_policy import adapt_surface
        return adapt_surface(surface, root=self.root, dry_run=dry_run)

    def adapt_all(self, *, dry_run: bool = False) -> Dict[str, Any]:
        from skeleton.intelligence.adaptive_policy import adapt_all_surfaces
        return adapt_all_surfaces(root=self.root, dry_run=dry_run)

    def set_adaptive_config(self, **kwargs) -> Dict[str, Any]:
        from skeleton.intelligence.adaptive_policy import set_adaptive_config
        return set_adaptive_config(root=self.root, **kwargs)

    def set_surface_adaptive(self, surface: str, **kwargs) -> Dict[str, Any]:
        from skeleton.intelligence.adaptive_policy import set_surface_adaptive_config
        return set_surface_adaptive_config(surface, root=self.root, **kwargs)

    def snapshot(self) -> Dict[str, Any]:
        return {"status": self.status(), "last_ref": self.last_ref, "last_improve": self.last_improve, "last_plan": self.last_plan, "traces": list(self.traces[:8]), "position": self.position, "face": FACES[self.position]}


def live_deck():
    from skeleton.cortex.live import live_cortex
    return CommandDeck(live_cortex())
