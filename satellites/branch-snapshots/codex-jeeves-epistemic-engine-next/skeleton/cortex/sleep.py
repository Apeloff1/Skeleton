"""Sleep consolidation — the own-system replays without the teacher.

A ring of (stim, hidden, labels, fired-slots) traces. consolidate()
replays a sample: specialist heads take another SGD step, adapters
distill toward the stored hidden, Hebbian tags fire when both
hemispheres were on, low-confidence traces drop. EMA of the neo
transformer snapshot is the synaptic tag — a slow copy of the guts
that hive B can import as a prior. This is not a second model. It is
how one model keeps what it acquired overnight.
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple

from skeleton.cortex.own import BIASES
from skeleton.cortex.port import SLOTS, Thought

K_BUFFER = 64
K_REPLAY = 8


@dataclass
class SleepTrace:
    stim: str
    hidden: Tuple[float, ...]
    mix: Optional[Tuple[float, float, float]] = None
    bias: Optional[str] = None
    route: Optional[Tuple[float, float, float]] = None
    veto: float = 0.0
    policy: Optional[Tuple[float, float]] = None
    fired: Tuple[str, ...] = ()
    slack: float = 0.0
    conf: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stim": self.stim[:160],
            "hidden": list(self.hidden),
            "mix": None if self.mix is None else list(self.mix),
            "bias": self.bias,
            "route": None if self.route is None else list(self.route),
            "veto": self.veto,
            "policy": None if self.policy is None else list(self.policy),
            "fired": list(self.fired),
            "slack": self.slack,
            "conf": self.conf,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SleepTrace":
        mix = d.get("mix")
        route = d.get("route")
        pol = d.get("policy")
        return cls(
            stim=str(d.get("stim") or ""),
            hidden=tuple(float(x) for x in (d.get("hidden") or ())),
            mix=None if not mix else (float(mix[0]), float(mix[1]), float(mix[2])),
            bias=d.get("bias"),
            route=None if not route else (float(route[0]), float(route[1]), float(route[2])),
            veto=float(d.get("veto") or 0.0),
            policy=None if not pol else (float(pol[0]), float(pol[1])),
            fired=tuple(d.get("fired") or ()),
            slack=float(d.get("slack") or 0.0),
            conf=float(d.get("conf") or 0.0),
        )


class SleepCycle:
    """Replay buffer + Hebbian co-fire matrix + EMA prior."""

    def __init__(self, *, k: int = K_BUFFER, seed: int = 23) -> None:
        self.buffer: Deque[SleepTrace] = deque(maxlen=max(8, int(k)))
        self.hebb: Dict[str, float] = {f"{a}:{b}": 0.0 for a in SLOTS for b in SLOTS}
        self.cycles = 0
        self.replays = 0
        self.pruned = 0
        self.ema: Optional[Dict[str, Any]] = None
        self._rng = random.Random(int(seed) & 0xFFFFFFFF)

    def record(
        self,
        stim: str,
        hidden: Sequence[float],
        *,
        left: Optional[Thought] = None,
        right: Optional[Thought] = None,
        pfc: Optional[Thought] = None,
        route: Optional[Thought] = None,
        slack: float = 0.0,
    ) -> SleepTrace:
        fired: List[str] = []
        mix = None
        bias = None
        route_n = None
        veto = 0.0
        policy = None
        confs: List[float] = []
        if left is not None:
            fired.append("left")
            confs.append(left.confidence)
            nums = tuple(left.numbers or ())
            if len(nums) >= 3 and 0 <= nums[-3] <= 8:
                mix = (float(nums[-3]), float(nums[-2]), float(nums[-1]))
        if right is not None:
            fired.append("right")
            confs.append(right.confidence)
            text = (right.text or "").lower()
            for b in BIASES:
                if b in (right.tags or ()) or f"bias={b}" in text:
                    bias = b
                    break
        if route is not None:
            fired.append("midbrain")
            confs.append(route.confidence)
            nums = tuple(route.numbers or ())
            if len(nums) >= 3:
                route_n = (float(nums[0]), float(nums[1]), float(nums[2]))
        if pfc is not None:
            fired.append("pfc")
            confs.append(pfc.confidence)
            nums = tuple(pfc.numbers or ())
            if nums:
                veto = float(nums[-1])
            if len(nums) >= 2:
                policy = (float(nums[0] >= 1.0), float(nums[-1] >= 1.0))
        for a in fired:
            for b in fired:
                key = f"{a}:{b}"
                self.hebb[key] = self.hebb.get(key, 0.0) + 1.0
        tr = SleepTrace(
            stim=stim or "",
            hidden=tuple(float(x) for x in hidden),
            mix=mix, bias=bias, route=route_n, veto=veto, policy=policy,
            fired=tuple(fired), slack=float(slack),
            conf=(sum(confs) / len(confs)) if confs else 0.0,
        )
        self.buffer.append(tr)
        return tr

    def consolidate(self, neo, *, n: int = K_REPLAY, lr: float = 0.06) -> Dict[str, Any]:
        """Replay. Heads step. Adapters distill. Callosum Hebbs. EMA updates."""
        buf = list(self.buffer)
        if not buf:
            return {"replays": 0, "cycles": self.cycles}
        k = min(max(1, int(n)), len(buf))
        sample = buf if len(buf) <= k else self._rng.sample(buf, k)
        heads_steps = 0
        distills = 0
        hebbs = 0
        moe = getattr(neo, "moe", None)
        callosum = getattr(neo, "callosum", None)
        for tr in sample:
            h = list(tr.hidden)
            if moe is not None:
                if tr.mix is not None:
                    moe.experts["left"].head.step(h, tr.mix, lr=lr)
                    heads_steps += 1
                if tr.bias is not None:
                    moe.experts["right"].head.step(h, tr.bias, lr=lr)
                    heads_steps += 1
                if tr.route is not None:
                    moe.experts["midbrain"].head.step(h, tr.route, lr=lr)
                    heads_steps += 1
                moe.experts["pfc"].head.step(h, tr.veto, lr=lr)
                heads_steps += 1
                if moe.experts["pfc"].aux is not None and tr.policy is not None:
                    moe.experts["pfc"].aux.step(h, tr.policy, lr=lr)
                    heads_steps += 1
                mixed, _ = moe.forward(h)
                for slot in tr.fired:
                    ex = moe.experts.get(slot)
                    if ex is not None:
                        ex.distill(h, mixed, lr=lr * 0.5)
                        distills += 1
                        moe.credit(slot, lr=0.01)
            if callosum is not None and "left" in tr.fired and "right" in tr.fired:
                callosum.hebb(h, lr=0.02)
                hebbs += 1
            if tr.stim:
                xf = getattr(neo, "transformer", None)
                if xf is not None and hasattr(xf, "fit"):
                    xf.fit([tr.stim], lr=min(lr, 0.03), schedule="cosine")
                rms = getattr(neo, "neo_rms", None)
                if rms is not None and hasattr(rms, "fit"):
                    rms.fit([tr.stim], lr=min(lr, 0.03), schedule="cosine")
            self.replays += 1
        self._ema_update(neo)
        self.cycles += 1
        return {
            "replays": len(sample),
            "heads_steps": heads_steps,
            "distills": distills,
            "hebbs": hebbs,
            "cycles": self.cycles,
            "buffer": len(self.buffer),
        }

    def prune(self, *, min_conf: float = 0.35) -> int:
        keep = [t for t in self.buffer if t.conf >= min_conf or t.slack > 0.0]
        dropped = len(self.buffer) - len(keep)
        self.buffer = deque(keep, maxlen=self.buffer.maxlen)
        self.pruned += dropped
        return dropped

    def _ema_update(self, neo, *, decay: float = 0.9) -> None:
        xf = getattr(neo, "transformer", None)
        if xf is None or not hasattr(xf, "snapshot"):
            return
        snap = xf.snapshot()
        if self.ema is None:
            self.ema = snap
            return
        # Only average fitted/steps — full weight EMA of nested lists is
        # the slow tag, done on Wout (the speaking head) so hive B inherits
        # a prior without copying the whole stack every cycle.
        prev = self.ema.get("Wout")
        cur = snap.get("Wout")
        if prev and cur and len(prev) == len(cur):
            blended = []
            for i, row in enumerate(cur):
                prow = prev[i]
                blended.append([
                    decay * float(prow[j]) + (1.0 - decay) * float(row[j])
                    for j in range(min(len(row), len(prow)))
                ])
            snap["Wout"] = blended
        self.ema = snap

    def snapshot(self) -> Dict[str, Any]:
        return {
            "buffer": [t.to_dict() for t in self.buffer],
            "hebb": dict(self.hebb),
            "cycles": self.cycles,
            "replays": self.replays,
            "pruned": self.pruned,
            "ema": self.ema,
        }

    def restore(self, data: Dict[str, Any]) -> int:
        self.buffer.clear()
        n = 0
        for d in (data or {}).get("buffer") or []:
            self.buffer.append(SleepTrace.from_dict(d))
            n += 1
        for k, v in ((data or {}).get("hebb") or {}).items():
            self.hebb[str(k)] = float(v)
        self.cycles = int((data or {}).get("cycles") or 0)
        self.replays = int((data or {}).get("replays") or 0)
        self.pruned = int((data or {}).get("pruned") or 0)
        self.ema = (data or {}).get("ema")
        return n

    def to_dict(self) -> Dict[str, Any]:
        co = self.hebb.get("left:right", 0.0)
        return {
            "buffer": len(self.buffer),
            "cycles": self.cycles,
            "replays": self.replays,
            "pruned": self.pruned,
            "cofire_lr": co,
            "ema": self.ema is not None,
        }
