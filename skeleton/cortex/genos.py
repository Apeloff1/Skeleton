"""Genos — the improvement gene as a system.

Trajectory is not a slogan. It is a pulse:

    G_{t+1} = G_t * (1 + η * M * H * C * (1 - ε))

    G  genos score (starts 1)
    η  cosine step, floor 0.08
    M  contact magnitude (birth_ppl / contact_ppl), clipped [0.25, 16]
    H  hive gate entropy (alive experts)
    C  BPE compression gain (1 - ratio)
    ε  error rate (failed pulses / total), target 0

A pulse runs: elect mouth, contact every teacher slot, sleep both neos,
evaluate four mouths, write the card into own-system and the repo.
Zero error margin: a pulse that throws is recorded as ε and does not
corrupt G. Performance peak is ppl inverse times coupling.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from skeleton.cortex.attn import cosine_lr
from skeleton.cortex.metrics import evaluate


def _clip(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


class Genos:
    def __init__(self) -> None:
        self.G = 1.0
        self.pulses = 0
        self.errors = 0
        self.history: List[Dict[str, Any]] = []
        self.peak = 1.0

    @property
    def epsilon(self) -> float:
        return self.errors / max(1, self.pulses)

    def pulse(self, neo, *, stimulus: str = "plan tensor ttk lattice soulslike") -> Dict[str, Any]:
        self.pulses += 1
        eta = cosine_lr(min(self.pulses, 64), 64, base=0.35, floor=0.08)
        card: Dict[str, Any] = {"pulse": self.pulses, "eta": round(eta, 4)}
        try:
            if hasattr(neo, "elect_mouth"):
                seal = neo.elect_mouth()
                card["mouth"] = seal.get("winner")
            mags = []
            slots = getattr(neo, "slots", {}) or {}
            from skeleton.cortex.contact import is_teacher
            for slot, port in slots.items():
                if is_teacher(port) and hasattr(neo, "contact"):
                    info = neo.contact(slot, stimulus)
                    mags.append(float(info.get("magnitude") or 1.0))
            if hasattr(neo, "sleep_cycle"):
                card["sleep"] = neo.sleep_cycle(n=4)
            ev = evaluate(neo) if neo is not None else {}
            card["eval"] = ev
            M = _clip(max(mags) if mags else 1.0, 0.25, 16.0)
            beats = ev.get("beats") or {}
            H = 1.0 if beats.get("gates_alive") else 0.55
            comp = float(ev.get("bpe_compression") or 1.0)
            C = max(0.05, 1.0 - comp)
            ppl = float(ev.get("ppl") or 1e3)
            coupling = float(ev.get("coupling") or 0.0)
            perf = (1.0 / max(ppl, 1e-6)) * (1.0 + coupling) * (1.0 + C)
            eps = self.epsilon
            growth = 1.0 + eta * M * H * C * (1.0 - eps)
            self.G = float(self.G * growth)
            if self.G > self.peak:
                self.peak = self.G
            card.update({
                "ok": 1,
                "M": round(M, 4),
                "H": H,
                "C": round(C, 4),
                "epsilon": round(eps, 4),
                "G": round(self.G, 6),
                "peak": round(self.peak, 6),
                "perf": round(perf, 8),
                "growth": round(growth, 6),
            })
        except Exception as exc:
            self.errors += 1
            card.update({"ok": 0, "error": type(exc).__name__, "G": round(self.G, 6), "epsilon": round(self.epsilon, 4)})
        self.history.append(card)
        return card

    def snapshot(self) -> Dict[str, Any]:
        return {"G": self.G, "pulses": self.pulses, "errors": self.errors, "peak": self.peak,
                "history": list(self.history[-32:])}

    def restore(self, data: Optional[Dict[str, Any]]) -> None:
        if not data:
            return
        self.G = float(data.get("G") or 1.0)
        self.pulses = int(data.get("pulses") or 0)
        self.errors = int(data.get("errors") or 0)
        self.peak = float(data.get("peak") or self.G)
        self.history = list(data.get("history") or [])
