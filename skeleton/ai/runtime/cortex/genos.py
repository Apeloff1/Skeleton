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


class AdaptiveQualityRatchet:
    """Adaptive monotonic quality ratchet for cortex self-learning.

    Maintains non-regressing ceilings on perplexity and mix MAE alongside
    non-decreasing floors on bias accuracy, router entropy, and Genos G.
    Adapts the learning-rate scale based on acceptance streak and velocity,
    and automatically rolls back weight updates that breach the ratchet.
    """

    def __init__(self) -> None:
        self.ppl_ceiling: float = float("inf")
        self.mix_mae_ceiling: float = 8.0
        self.bias_acc_floor: float = 0.0
        self.gate_entropy_floor: float = 0.0
        self.g_floor: float = 1.0
        self.streak: int = 0
        self.rejections: int = 0
        self.accepted: int = 0
        self.adaptive_lr_scale: float = 1.0
        self.velocity_ewma: float = 0.0

    def observe(self, ev: Dict[str, Any], *, G: float = 1.0, tolerance: float = 0.02) -> Dict[str, Any]:
        ppl = float(ev.get("ppl") or float("inf"))
        mix_mae = float(ev.get("mix_mae") if ev.get("mix_mae") is not None else 8.0)
        bias_acc = float(ev.get("bias_acc") or 0.0)
        gate_ent = float(ev.get("gate_entropy") or 0.0)

        ppl_ok = (not math.isfinite(self.ppl_ceiling)) or (ppl <= self.ppl_ceiling * (1.0 + tolerance) + 1e-6)
        mae_ok = mix_mae <= self.mix_mae_ceiling + tolerance + 1e-6
        g_ok = G + 1e-9 >= self.g_floor

        passed = bool(ppl_ok and mae_ok and g_ok)
        if passed:
            prev_ppl = self.ppl_ceiling if math.isfinite(self.ppl_ceiling) else ppl
            rel_gain = max(0.0, (prev_ppl - ppl) / max(prev_ppl, 1e-6)) if math.isfinite(ppl) else 0.0
            self.velocity_ewma = 0.7 * self.velocity_ewma + 0.3 * rel_gain
            if math.isfinite(ppl):
                self.ppl_ceiling = min(self.ppl_ceiling, ppl)
            self.mix_mae_ceiling = min(self.mix_mae_ceiling, mix_mae)
            self.bias_acc_floor = max(self.bias_acc_floor, bias_acc)
            self.gate_entropy_floor = max(self.gate_entropy_floor, min(1.10, gate_ent))
            self.g_floor = max(self.g_floor, float(G))
            self.streak += 1
            self.accepted += 1
            self.adaptive_lr_scale = _clip(
                self.adaptive_lr_scale * (1.0 + min(0.15, 0.03 * self.streak + 0.5 * self.velocity_ewma)),
                0.25,
                2.0,
            )
        else:
            self.streak = 0
            self.rejections += 1
            self.velocity_ewma *= 0.5
            self.adaptive_lr_scale = _clip(self.adaptive_lr_scale * 0.75, 0.25, 2.0)

        return {
            "passed": passed,
            "ppl_ceiling": None if not math.isfinite(self.ppl_ceiling) else round(self.ppl_ceiling, 4),
            "mix_mae_ceiling": round(self.mix_mae_ceiling, 4),
            "bias_acc_floor": round(self.bias_acc_floor, 4),
            "gate_entropy_floor": round(self.gate_entropy_floor, 4),
            "g_floor": round(self.g_floor, 6),
            "streak": self.streak,
            "accepted": self.accepted,
            "rejections": self.rejections,
            "adaptive_lr_scale": round(self.adaptive_lr_scale, 4),
        }

    def step(
        self,
        neo,
        step_fn,
        *,
        tolerance: float = 0.02,
    ) -> Dict[str, Any]:
        """Execute ``step_fn(lr_scale)`` under ratchet protection with rollback on regression."""
        xf = getattr(neo, "transformer", None)
        rms = getattr(neo, "neo_rms", None)
        moe = getattr(neo, "moe", None)
        xf_snap = xf.snapshot() if xf is not None and hasattr(xf, "snapshot") else None
        rms_snap = rms.snapshot() if rms is not None and hasattr(rms, "snapshot") else None
        moe_snap = moe.snapshot() if moe is not None and hasattr(moe, "snapshot") else None

        ev_before = evaluate(neo) if neo is not None else {}
        G_before = float(getattr(getattr(neo, "genos_engine", None), "G", 1.0) or 1.0)
        if not math.isfinite(self.ppl_ceiling):
            ppl0 = float(ev_before.get("ppl") or float("inf"))
            if math.isfinite(ppl0):
                self.ppl_ceiling = ppl0
        self.mix_mae_ceiling = min(
            self.mix_mae_ceiling,
            float(ev_before.get("mix_mae") if ev_before.get("mix_mae") is not None else 8.0),
        )

        step_info = step_fn(self.adaptive_lr_scale)
        ev_after = evaluate(neo) if neo is not None else {}
        G_after = float(getattr(getattr(neo, "genos_engine", None), "G", G_before) or G_before)
        verdict = self.observe(ev_after, G=G_after, tolerance=tolerance)

        rolled_back = False
        if not verdict["passed"]:
            rolled_back = True
            from skeleton.cortex.transformer import TinyTransformer
            if xf_snap is not None and xf is not None and type(xf) is TinyTransformer:
                neo.transformer = TinyTransformer.from_snapshot(xf_snap)
                if getattr(neo, "bpe", None) is not None:
                    neo.transformer.bpe = neo.bpe
            if rms_snap is not None and rms is not None and type(rms) is TinyTransformer:
                neo.neo_rms = TinyTransformer.from_snapshot(rms_snap)
                if getattr(neo, "bpe", None) is not None:
                    neo.neo_rms.bpe = neo.bpe
            if moe_snap is not None and moe is not None:
                from skeleton.cortex.moe import ExpertBank
                neo.moe = ExpertBank.from_snapshot(moe_snap)

        return {
            **verdict,
            "rolled_back": rolled_back,
            "ppl_before": ev_before.get("ppl"),
            "ppl_after": ev_after.get("ppl") if not rolled_back else ev_before.get("ppl"),
            "step_info": step_info,
        }

    def snapshot(self) -> Dict[str, Any]:
        return {
            "ppl_ceiling": None if not math.isfinite(self.ppl_ceiling) else self.ppl_ceiling,
            "mix_mae_ceiling": self.mix_mae_ceiling,
            "bias_acc_floor": self.bias_acc_floor,
            "gate_entropy_floor": self.gate_entropy_floor,
            "g_floor": self.g_floor,
            "streak": self.streak,
            "accepted": self.accepted,
            "rejections": self.rejections,
            "adaptive_lr_scale": self.adaptive_lr_scale,
            "velocity_ewma": self.velocity_ewma,
        }

    def restore(self, data: Optional[Dict[str, Any]]) -> None:
        if not data:
            return
        raw_ppl = data.get("ppl_ceiling")
        self.ppl_ceiling = float(raw_ppl) if raw_ppl is not None else float("inf")
        self.mix_mae_ceiling = float(data.get("mix_mae_ceiling") if data.get("mix_mae_ceiling") is not None else 8.0)
        self.bias_acc_floor = float(data.get("bias_acc_floor") or 0.0)
        self.gate_entropy_floor = float(data.get("gate_entropy_floor") or 0.0)
        self.g_floor = float(data.get("g_floor") or 1.0)
        self.streak = int(data.get("streak") or 0)
        self.accepted = int(data.get("accepted") or 0)
        self.rejections = int(data.get("rejections") or 0)
        self.adaptive_lr_scale = float(data.get("adaptive_lr_scale") or 1.0)
        self.velocity_ewma = float(data.get("velocity_ewma") or 0.0)


class Genos:
    def __init__(self) -> None:
        self.G = 1.0
        self.pulses = 0
        self.errors = 0
        self.history: List[Dict[str, Any]] = []
        self.peak = 1.0
        self.ratchet = AdaptiveQualityRatchet()

    @property
    def epsilon(self) -> float:
        return self.errors / max(1, self.pulses)

    def pulse(self, neo, *, stimulus: str = "plan tensor ttk lattice soulslike") -> Dict[str, Any]:
        self.pulses += 1
        eta = cosine_lr(min(self.pulses, 64), 64, base=0.35, floor=0.08) * self.ratchet.adaptive_lr_scale
        eta = _clip(eta, 0.04, 0.70)
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
            ratchet_state = self.ratchet.observe(ev, G=self.G)
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
                "ratchet": ratchet_state,
            })
        except Exception as exc:
            self.errors += 1
            card.update({"ok": 0, "error": type(exc).__name__, "G": round(self.G, 6), "epsilon": round(self.epsilon, 4)})
        self.history.append(card)
        return card

    def snapshot(self) -> Dict[str, Any]:
        return {"G": self.G, "pulses": self.pulses, "errors": self.errors, "peak": self.peak,
                "ratchet": self.ratchet.snapshot(),
                "history": list(self.history[-32:])}

    def restore(self, data: Optional[Dict[str, Any]]) -> None:
        if not data:
            return
        self.G = float(data.get("G") or 1.0)
        self.pulses = int(data.get("pulses") or 0)
        self.errors = int(data.get("errors") or 0)
        self.peak = float(data.get("peak") or self.G)
        if data.get("ratchet"):
            self.ratchet.restore(data.get("ratchet"))
        self.history = list(data.get("history") or [])
