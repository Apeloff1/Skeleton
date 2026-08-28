"""Jeeves neocortex — hivemind that organizes the tracts and is itself an LM.

The four slots (PFC / midbrain / left / right) are agents. Jeeves:
  1. lets midbrain route
  2. fires the hemispheres the route named
  3. lets PFC plan / inhibit
  4. aggregates confidence through HiveMind
  5. amalgamates a teacher thought
  6. composes an own-system thought from Jaccard-nearest acquired tracts
  7. shadows own vs teacher; auto-surpass when own wins
  8. acquire(slot) copies a model's abilities AND stamps the MoE expert
  9. surpass(slot) answers from own-system — the neo transformer SPEAKS
     (CPU default, CUDA if harnessed). Compose keeps the numbers. Veto still wins.
 10. specialist heads train on teacher numbers every think (online distill)
 11. corpus callosum fuses left/right streams; Hebb when both fire
 12. sleep consolidates the buffer; REINFORCE eats walk slack

Backends are interchangeable: bind(slot, port) hot-swaps the model in
that tract. The neo TinyTransformer is Jeeves' own language model.
GPU is a harness on that same net, not a second architecture.
Heads + MoE + callosum are how neo acquires the MODELS, not the prompts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set

from skeleton.cortex.callosum import CorpusCallosum
from skeleton.cortex.curriculum import train as run_curriculum
from skeleton.cortex.distill import Ability, AbilityLedger, ability_from
from skeleton.cortex.hemispheres import LeftHemisphere, RightHemisphere
from skeleton.cortex.midbrain import Midbrain
from skeleton.cortex.moe import ExpertBank
from skeleton.cortex.own import OwnSystem, Tract, shadow_eval
from skeleton.cortex.pfc import PrefrontalCortex
from skeleton.cortex.port import SLOTS, EchoBackend, ModelPort, Thought, fingerprint
from skeleton.cortex.rl import ReinforceState, reinforce_mix
from skeleton.cortex.sleep import SleepCycle
from skeleton.kernel.errors import CortexError
from skeleton.kernel.events import EventBus
from skeleton.swarm.hive import Estimate, HiveMind

AUTO_TRIALS = 3
AUTO_RATE = 0.60


@dataclass
class CortexTrace:
    stimulus: str
    fingerprint: str
    route: Thought
    pfc: Thought
    left: Optional[Thought]
    right: Optional[Thought]
    amalgam: Thought
    hive_value: float
    used_own: bool
    acquired: Dict[str, int]
    backends: Dict[str, str]
    recalled_jaccard: float = 0.0
    shadow_win: Optional[bool] = None
    own_size: int = 0
    moe_gates: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stimulus": self.stimulus[:160],
            "fingerprint": self.fingerprint,
            "route": self.route.to_dict(),
            "pfc": self.pfc.to_dict(),
            "left": None if self.left is None else self.left.to_dict(),
            "right": None if self.right is None else self.right.to_dict(),
            "amalgam": self.amalgam.to_dict(),
            "hive_value": round(self.hive_value, 4),
            "used_own": self.used_own,
            "acquired": dict(self.acquired),
            "backends": dict(self.backends),
            "recalled_jaccard": round(self.recalled_jaccard, 4),
            "shadow_win": self.shadow_win,
            "own_size": self.own_size,
            "moe_gates": None if self.moe_gates is None else [round(g, 4) for g in self.moe_gates],
        }


def local_slots() -> Dict[str, ModelPort]:
    return {
        "pfc": PrefrontalCortex(),
        "midbrain": Midbrain(),
        "left": LeftHemisphere(),
        "right": RightHemisphere(),
    }


class JeevesCortex:
    """Neocortex. Organizer, trainer, and the model that can surpass its parts."""

    name = "jeeves-neo"
    scale = "neo"
    slot = "neo"

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self._bus = bus or EventBus()
        self.slots: Dict[str, ModelPort] = local_slots()
        self.ledger = AbilityLedger()
        self.own = OwnSystem()
        self.acquired: Dict[str, int] = {s: 0 for s in SLOTS}
        self._surpass: Set[str] = set()
        self.shadow: Dict[str, Dict[str, int]] = {s: {"wins": 0, "trials": 0} for s in SLOTS}
        self.shadow["own"] = {"wins": 0, "trials": 0}
        self.hive = HiveMind(bus=self._bus)
        self.auto_surpass = True
        from skeleton.cortex.device import attach_lm, probe
        from skeleton.cortex.lm import gameforge_vocab
        self.transformer = attach_lm(
            vocab=gameforge_vocab(), dim=8, ctx=8, seed=19,
            n_heads=2, n_layers=2, d_ff=32, device="auto",
        )
        from skeleton.cortex.transformer import TinyTransformer
        self.neo_rms = TinyTransformer(
            vocab=gameforge_vocab(), dim=8, ctx=8, seed=23,
            n_heads=2, n_layers=2, d_ff=32, norm="rms", ffn_kind="swiglu",
        )
        self._device_info = probe()
        dim = int(getattr(self.transformer, "dim", 8) or 8)
        self.callosum = CorpusCallosum(dim=dim, seed=17)
        self.moe = ExpertBank(dim=dim, seed=19)
        self.sleep = SleepCycle(seed=23)
        self.rl = ReinforceState()
        from skeleton.cortex.bpe import gameforge_bpe
        self.bpe = gameforge_bpe(merges=64)

    def backends(self) -> Dict[str, str]:
        return {s: getattr(p, "name", type(p).__name__) for s, p in self.slots.items()}

    def bind(self, slot: str, backend: ModelPort) -> Dict[str, str]:
        slot = (slot or "").lower()
        if slot not in SLOTS:
            raise CortexError("unknown slot", context={"slot": slot, "known": list(SLOTS)})
        if getattr(backend, "slot", slot) not in {slot, "neo"}:
            try:
                backend.slot = slot  # type: ignore[attr-defined]
            except Exception:
                pass
        self.slots[slot] = backend
        self._bus.emit("cortex.slot.bound", {"slot": slot, "backend": getattr(backend, "name", type(backend).__name__)})
        return self.backends()

    def bind_echo(self, slot: str) -> Dict[str, str]:
        return self.bind(slot, EchoBackend(slot=slot))

    def bind_local(self, slot: str) -> Dict[str, str]:
        return self.bind(slot, local_slots()[slot])

    def _hidden(self, stim: str) -> List[float]:
        seq = self._hidden_seq(stim)
        return list(seq[-1]) if seq else [0.0] * int(getattr(self.transformer, "dim", 8) or 8)

    def _hidden_seq(self, stim: str) -> List[List[float]]:
        xf = self.transformer
        if xf is not None and hasattr(xf, "hidden_seq"):
            H = xf.hidden_seq(stim or "")
            if H:
                return H
        if xf is not None and hasattr(xf, "hidden"):
            h = list(xf.hidden(stim or ""))
            if h:
                return [h]
        return [[0.0] * int(getattr(xf, "dim", 8) or 8)]

    def _tract_hidden(self, slot: str, stim: str):
        port = (getattr(self, "slots", {}) or {}).get(slot)
        xf = getattr(port, "transformer", None) if port is not None else None
        if xf is None or not hasattr(xf, "hidden"):
            return None
        try:
            h = list(xf.hidden(stim or ""))
        except Exception:
            return None
        return h if h else None

    def think(self, stimulus: str, context: Optional[Dict[str, Any]] = None) -> CortexTrace:
        stim = stimulus or ""
        ctx = dict(context or {})
        fp = fingerprint(stim)

        # Compose against own-system as of BEFORE this turn (no teacher leak).
        composed = self.own.compose(stim)
        recalled_j = composed[1] if composed else 0.0

        route = self.slots["midbrain"].think(stim, ctx)
        self.ledger.record(route, stim)

        left = right = None
        lw = route.numbers[1] if len(route.numbers) > 1 else 0.55
        rw = route.numbers[2] if len(route.numbers) > 2 else 0.55
        if lw >= 0.25:
            left = self.slots["left"].think(stim, {**ctx, "route": route.to_dict()})
            self.ledger.record(left, stim)
        if rw >= 0.25:
            right = self.slots["right"].think(stim, {**ctx, "route": route.to_dict()})
            self.ledger.record(right, stim)

        pfc_ctx = {**ctx}
        if left:
            pfc_ctx["left"] = left.to_dict()
        if right:
            pfc_ctx["right"] = right.to_dict()
        pfc = self.slots["pfc"].think(stim, pfc_ctx)
        self.ledger.record(pfc, stim)

        estimates: List[Estimate] = [
            Estimate("midbrain", route.confidence),
            Estimate("pfc", pfc.confidence),
        ]
        if left:
            estimates.append(Estimate("left", left.confidence))
        if right:
            estimates.append(Estimate("right", right.confidence))
        hive = self.hive.aggregate(estimates, method="trimmed_weighted")

        teacher = self._amalgam(pfc, left, right, route, hive.value)

        used_own = False
        shadow_win: Optional[bool] = None
        amalgam = teacher
        veto = bool(pfc.tags and "veto" in pfc.tags) or (
            bool(pfc.numbers) and pfc.numbers[-1] >= 1.0
        )
        own_thought = None
        if composed is not None:
            own_thought, recalled_j, _hits = composed
            shadow_win = shadow_eval(own_thought, teacher)
            self.shadow["own"]["trials"] += 1
            if shadow_win:
                self.shadow["own"]["wins"] += 1
            if self.auto_surpass:
                self._maybe_auto_surpass()
        armed = bool(self._surpass)
        if armed and not veto:
            if own_thought is None:
                own_thought = Thought(slot="neo", kind="own", text="", confidence=0.5, tags=("own", "surpass"))
            amalgam = self._lm_amalgam(stim, own_thought, recalled_j)
            used_own = True
            for s in self._surpass:
                self.shadow[s]["trials"] += 1
                if shadow_win:
                    self.shadow[s]["wins"] += 1

        # Ingest AFTER the decision so this turn cannot recall itself.
        self.own.ingest(ability_from(teacher, stim), stim)
        for thought in (route, pfc, left, right):
            if thought is not None:
                self.own.ingest(ability_from(thought, stim), stim)

        gates = self._distill_step(stim, left=left, right=right, pfc=pfc, route=route)

        self._bus.emit("cortex.thought", {
            "fp": fp, "used_own": used_own, "hive": hive.value,
            "backends": self.backends(), "jaccard": recalled_j,
            "shadow_win": shadow_win,
        })
        return CortexTrace(
            stimulus=stim, fingerprint=fp, route=route, pfc=pfc,
            left=left, right=right, amalgam=amalgam,
            hive_value=hive.value, used_own=used_own,
            acquired=dict(self.acquired), backends=self.backends(),
            recalled_jaccard=recalled_j, shadow_win=shadow_win,
            own_size=self.own.size, moe_gates=gates,
        )

    def _distill_step(
        self,
        stim: str,
        *,
        left: Optional[Thought],
        right: Optional[Thought],
        pfc: Optional[Thought],
        route: Optional[Thought],
    ) -> List[float]:
        """Online distill: heads eat teacher numbers, callosum fuses, sleep records."""
        H = self._hidden_seq(stim)
        h = H[-1] if H else [0.0] * int(getattr(self.transformer, "dim", 8) or 8)
        left_on = left is not None
        right_on = right is not None
        h_left = self._tract_hidden("left", stim)
        h_right = self._tract_hidden("right", stim)
        if h_left is not None and h_right is not None:
            fused, _fl, _fr = self.callosum.fuse_tracts(h_left, h_right, left_on=left_on, right_on=right_on)
            if left_on and right_on:
                self.callosum.hebb_tracts(h_left, h_right)
        elif len(H) >= 2:
            fused, _fl, _fr = self.callosum.fuse_seq(H, left_on=left_on, right_on=right_on)
            if left_on and right_on:
                self.callosum.hebb(H[-1] if H else h)
        else:
            fused, _fl, _fr = self.callosum.fuse(h, left_on=left_on, right_on=right_on)
            if left_on and right_on:
                self.callosum.hebb(H[-1] if H else h)
        mixed, gates = self.moe.forward(fused)
        if left is not None:
            nums = tuple(left.numbers or ())
            if len(nums) >= 3 and 0 <= nums[-3] <= 8:
                self.moe.experts["left"].head.step(fused, nums[-3:])
            self.moe.credit("left")
        if right is not None:
            text = (right.text or "").lower()
            from skeleton.cortex.own import BIASES
            for b in BIASES:
                if b in (right.tags or ()) or f"bias={b}" in text:
                    self.moe.experts["right"].head.step(fused, b)
                    break
            self.moe.credit("right")
        if route is not None and len(route.numbers) >= 3:
            self.moe.experts["midbrain"].head.step(fused, route.numbers[:3])
            self.moe.credit("midbrain")
        if pfc is not None:
            veto_t = float(pfc.numbers[-1]) if pfc.numbers else 0.0
            self.moe.experts["pfc"].head.step(fused, veto_t)
            self.moe.credit("pfc")
        self.sleep.record(stim, fused, left=left, right=right, pfc=pfc, route=route)
        return list(gates)

    def acquire(self, slot: str) -> Dict[str, Any]:
        slot = (slot or "").lower()
        if slot not in SLOTS:
            raise CortexError("unknown slot", context={"slot": slot})
        copied = 0
        for ab in self.ledger.of_slot(slot):
            self.own.ingest(Ability(
                slot="neo", stimulus_fp=ab.stimulus_fp, signature=ab.signature,
                kind=ab.kind, text=ab.text, tags=ab.tags + ("acquired", slot),
                numbers=ab.numbers, confidence=min(1.0, ab.confidence + 0.05),
                seen=ab.seen, tokens=ab.tokens,
            ))
            copied += 1
        self.acquired[slot] = self.acquired.get(slot, 0) + copied
        stamped = self.moe.acquire(slot)
        port = self.slots.get(slot)
        model = 0
        absorb: Dict[str, Any] = {"absorbed": 0}
        if port is not None and hasattr(port, "snapshot"):
            model = self.own.ingest_model(slot, port.snapshot())
        src = getattr(port, "transformer", None) if port is not None else None
        if src is not None:
            from skeleton.cortex.gossip import absorb_mouth
            absorb = absorb_mouth(self.transformer, src, alpha=0.2)
            if getattr(self, "neo_rms", None) is not None:
                absorb["neo_rms"] = absorb_mouth(self.neo_rms, src, alpha=0.1)
        self._bus.emit("cortex.acquired", {"slot": slot, "copied": copied, "expert": stamped, "model": model})
        return {
            "slot": slot, "copied": copied, "acquired": dict(self.acquired),
            "own": self.own.size, "expert": stamped,
            "model": model, "absorb": absorb, "models": sorted(self.own.models),
        }

    def surpass(self, slot: str) -> Dict[str, Any]:
        slot = (slot or "").lower()
        if slot not in SLOTS:
            raise CortexError("unknown slot", context={"slot": slot})
        self._surpass.add(slot)
        self._bus.emit("cortex.surpass", {"slot": slot, "own": self.own.size})
        return {"slot": slot, "armed": sorted(self._surpass), "own": self.own.size, "shadow": dict(self.shadow)}

    def recall(self, stimulus: str) -> Dict[str, Any]:
        hits = self.own.recall(stimulus)
        composed = self.own.compose(stimulus)
        return {
            "hits": [h.to_dict() for h in hits],
            "composed": None if composed is None else {
                "thought": composed[0].to_dict(),
                "jaccard": round(composed[1], 4),
                "used": [h.to_dict() for h in composed[2]],
            },
        }

    def predict_mix(self, stimulus: str):
        return self.moe.predict_mix(self._stream(stimulus))

    def predict_bias(self, stimulus: str):
        return self.moe.predict_bias(self._stream(stimulus))

    def predict_route(self, stimulus: str):
        return self.moe.predict_route(self._stream(stimulus))

    def predict_veto(self, stimulus: str):
        return self.moe.predict_veto(self._stream(stimulus))

    def predict_policy(self, stimulus: str):
        return self.moe.predict_policy(self._stream(stimulus))

    def _stream(self, stim: str) -> List[float]:
        H = self._hidden_seq(stim)
        if len(H) >= 2:
            fused, _fl, _fr = self.callosum.fuse_seq(H, left_on=True, right_on=True)
            return fused
        h = H[0] if H else self._hidden(stim)
        fused, _fl, _fr = self.callosum.fuse(h, left_on=True, right_on=True)
        return fused

    def sleep_cycle(self, *, n: int = 8) -> Dict[str, Any]:
        out = self.sleep.consolidate(self, n=n)
        self.sleep.prune()
        self._bus.emit("cortex.sleep", out)
        return out

    def reinforce(self, stimulus: str, action: Sequence[float], reward: float) -> Dict[str, Any]:
        h = self._stream(stimulus)
        head = self.moe.experts["left"].head
        info = reinforce_mix(head, h, action, reward, self.rl)
        if float(reward) >= self.rl.baseline:
            self.moe.credit("left", lr=0.03)
        self._bus.emit("cortex.reinforce", info)
        return info

    def export_tract(self, slot: str) -> Dict[str, Any]:
        slot = (slot or "").lower()
        backend = self.backends().get(slot, "own")
        scale = getattr(self.slots.get(slot), "scale", "neo")
        tract = self.own.export_tract(slot, backend=backend, scale=str(scale))
        payload = tract.to_dict()
        port = self.slots.get(slot)
        if port is not None and hasattr(port, "snapshot"):
            payload["weights"] = port.snapshot()
        ex = self.moe.experts.get(slot)
        if ex is not None:
            payload["expert"] = ex.snapshot()
        payload["callosum"] = self.callosum.snapshot()
        payload["moe_fp"] = self.moe.fingerprint()
        return payload

    def import_tract(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        tract = Tract.from_dict(payload)
        n = self.own.import_tract(tract)
        weights = (payload or {}).get("weights")
        bound = None
        if weights:
            port = self.slots.get(tract.slot)
            w = getattr(port, "weights", None)
            if tract.slot == "pfc":
                from skeleton.cortex.lm import LanguageModelBackend
                ngram = {k: v for k, v in weights.items() if k not in {"neural", "transformer"}}
                self.bind(tract.slot, LanguageModelBackend.from_snapshot(ngram, slot=tract.slot))
                bound = tract.slot
            elif w is not None:
                w.restore(weights)
                bound = tract.slot
        expert = (payload or {}).get("expert")
        if expert and tract.slot in self.moe.experts:
            from skeleton.cortex.moe import Expert
            self.moe.experts[tract.slot] = Expert.from_snapshot(expert)
        if (payload or {}).get("callosum"):
            self.callosum = CorpusCallosum.from_snapshot(payload["callosum"])
        self._bus.emit("cortex.imported", {"slot": tract.slot, "copied": n})
        return {"slot": tract.slot, "copied": n, "own": self.own.size,
                "capabilities": list(tract.capabilities)[:16],
                "bound": bound, "moe_fp": self.moe.fingerprint()}

    def train(self, *, epochs: int = 1, auto_surpass: bool = True) -> Dict[str, Any]:
        return run_curriculum(self, epochs=epochs, auto_surpass=auto_surpass)

    def save(self, path) -> Dict[str, Any]:
        from pathlib import Path
        import json
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        lms = {}
        for slot, port in self.slots.items():
            if hasattr(port, "snapshot"):
                lms[slot] = port.snapshot()
        blob = {
            "own": self.own.snapshot(),
            "acquired": dict(self.acquired),
            "surpass": sorted(self._surpass),
            "shadow": dict(self.shadow),
            "lms": lms,
            "transformer": self.transformer.snapshot(),
            "neo_rms": self.neo_rms.snapshot() if getattr(self, "neo_rms", None) is not None else None,
            "callosum": self.callosum.snapshot(),
            "moe": self.moe.snapshot(),
            "sleep": self.sleep.snapshot(),
            "rl": self.rl.snapshot(),
            "bpe": self.bpe.snapshot(),
        }
        p.write_text(json.dumps(blob), encoding="utf-8")
        return {"path": str(p), "own": self.own.size, "acquired": dict(self.acquired)}

    def load(self, path) -> Dict[str, Any]:
        from pathlib import Path
        import json
        p = Path(path)
        if not p.exists():
            return {"loaded": 0, "own": self.own.size}
        blob = json.loads(p.read_text(encoding="utf-8"))
        n = self.own.restore(blob.get("own") or {})
        for k, v in (blob.get("acquired") or {}).items():
            self.acquired[str(k)] = int(v)
        self._surpass.update(blob.get("surpass") or [])
        for k, v in (blob.get("shadow") or {}).items():
            if isinstance(v, dict):
                self.shadow[str(k)] = {
                    "wins": int(v.get("wins") or 0),
                    "trials": int(v.get("trials") or 0),
                }
        for slot, snap in (blob.get("lms") or {}).items():
            port = self.slots.get(str(slot))
            w = getattr(port, "weights", None) if port is not None else None
            if w is not None and isinstance(snap, dict):
                w.restore(snap)
        if blob.get("transformer"):
            snap = blob["transformer"]
            if (snap or {}).get("kind") == "torch-stack":
                try:
                    from skeleton.cortex.torch_lm import TorchTransformer
                    self.transformer = TorchTransformer.from_snapshot(snap)
                except Exception:
                    from skeleton.cortex.transformer import TinyTransformer
                    self.transformer = TinyTransformer.from_snapshot(snap)
            else:
                from skeleton.cortex.transformer import TinyTransformer
                self.transformer = TinyTransformer.from_snapshot(snap)
        if blob.get("neo_rms"):
            from skeleton.cortex.transformer import TinyTransformer
            self.neo_rms = TinyTransformer.from_snapshot(blob["neo_rms"])
        if blob.get("callosum"):
            self.callosum = CorpusCallosum.from_snapshot(blob["callosum"])
        if blob.get("moe"):
            self.moe = ExpertBank.from_snapshot(blob["moe"])
        if blob.get("sleep"):
            self.sleep.restore(blob["sleep"])
        if blob.get("rl"):
            self.rl = ReinforceState.from_snapshot(blob["rl"])
        if blob.get("bpe"):
            from skeleton.cortex.bpe import BytePairEncoder
            self.bpe = BytePairEncoder.from_snapshot(blob["bpe"])
        return {"loaded": n, "own": self.own.size, "surpass": sorted(self._surpass)}

    def status(self) -> Dict[str, Any]:
        xf = self.transformer
        info = self._device_info or {}
        return {
            "backends": self.backends(),
            "ledger": self.ledger.to_dict(),
            "own": self.own.to_dict(),
            "acquired": dict(self.acquired),
            "surpass": sorted(self._surpass),
            "shadow": dict(self.shadow),
            "lm": {
                "fitted": int(getattr(xf, "fitted", 0) or 0),
                "steps": int(getattr(xf, "steps", 0) or 0),
                "dim": int(getattr(xf, "dim", 0) or 0),
                "ctx": int(getattr(xf, "ctx", 0) or 0),
                "n_heads": int(getattr(xf, "n_heads", 1) or 1),
                "n_layers": int(getattr(xf, "n_layers", 1) or 1),
                "d_ff": int(getattr(xf, "d_ff", 0) or 0),
                "norm": str(getattr(xf, "norm", "ln") or "ln"),
                "ffn_kind": str(getattr(xf, "ffn_kind", "gelu") or "gelu"),
                "neo_rms": {
                    "norm": str(getattr(self.neo_rms, "norm", "rms")),
                    "ffn_kind": str(getattr(self.neo_rms, "ffn_kind", "swiglu")),
                    "steps": int(getattr(self.neo_rms, "steps", 0) or 0),
                },
                "device": str(getattr(xf, "device", "cpu") or "cpu"),
                "requested": str(getattr(xf, "requested", getattr(xf, "device", "cpu")) or "cpu"),
                "backend": type(xf).__name__,
                "cuda": bool(info.get("cuda")),
                "resident": bool(getattr(xf, "resident", False)),
                "capability": str(info.get("capability") or "python"),
            },
            "callosum": self.callosum.to_dict(),
            "moe": self.moe.to_dict(),
            "sleep": self.sleep.to_dict(),
            "rl": self.rl.to_dict(),
            "bpe": self.bpe.to_dict(),
            "hive": {
                "moe_fp": self.moe.fingerprint(),
            },
            "lora": (self.transformer.lora.to_dict()
                     if getattr(self.transformer, "lora", None) is not None else None),
        }

    def mouth(self, name: str = "gelu"):
        key = str(name or "gelu").lower()
        if key in {"rms", "swiglu", "neo_rms", "right"}:
            return getattr(self, "neo_rms", None) or self.transformer
        return self.transformer

    def speak(self, stimulus: str, *, n: int = 12, seed: int = 0, mouth: str = "gelu") -> str:
        xf = self.mouth(mouth)
        if xf is None:
            return ""
        if hasattr(xf, "decode"):
            return str(xf.decode(stimulus or "", n=n, seed=seed))
        return " ".join(xf.generate(stimulus or "", n=n, seed=seed))

    def beam(self, stimulus: str, *, n: int = 8, width: int = 4, mouth: str = "gelu") -> Dict[str, Any]:
        xf = self.mouth(mouth)
        if xf is None:
            return {"winner": "", "beams": []}
        if hasattr(xf, "beam"):
            out = xf.beam(stimulus or "", n=n, width=width)
        else:
            from skeleton.cortex.beam import beam_search
            out = beam_search(xf, stimulus or "", n=n, width=width)
        out["mouth"] = "rms" if xf is getattr(self, "neo_rms", None) else "gelu"
        return out

    def attach_lora(self, *, rank: int = 2, alpha: float = 4.0) -> Dict[str, Any]:
        xf = self.transformer
        out: Dict[str, Any] = {"attached": []}
        if xf is not None and hasattr(xf, "attach_lora"):
            out = dict(xf.attach_lora(rank=rank, alpha=alpha))
        rms = getattr(self, "neo_rms", None)
        rms_out = {"attached": []}
        if rms is not None and hasattr(rms, "attach_lora"):
            rms_out = rms.attach_lora(rank=rank, alpha=alpha)
        out["neo_rms"] = rms_out
        return out

    def merge_lora(self) -> Dict[str, Any]:
        xf = self.transformer
        out: Dict[str, Any] = {"merged": []}
        if xf is not None and hasattr(xf, "merge_lora"):
            out = dict(xf.merge_lora())
        rms = getattr(self, "neo_rms", None)
        if rms is not None and hasattr(rms, "merge_lora"):
            out["neo_rms"] = rms.merge_lora()
        return out

    def accumulate(self, texts=None, *, k: int = 4, lr: float = 0.04) -> Dict[str, Any]:
        from skeleton.cortex.lm import gameforge_corpus
        xf = self.transformer
        if xf is None:
            return {"tokens": 0}
        corp = texts or gameforge_corpus()[:8]
        if hasattr(xf, "accumulate"):
            return xf.accumulate(corp, k=k, lr=lr)
        from skeleton.cortex.accum import accumulate_fit
        return accumulate_fit(xf, corp, k=k, lr=lr)

    def gossip_with(self, other, *, alpha: float = 0.5) -> Dict[str, Any]:
        from skeleton.cortex.gossip import gossip_cortices
        return gossip_cortices(self, other, alpha=alpha)

    def gossip_mouths(self, *, alpha: float = 0.25, direction: str = "rms-into-gelu") -> Dict[str, Any]:
        from skeleton.cortex.gossip import gossip_mouths
        return gossip_mouths(self, alpha=alpha, direction=direction)

    def tokens_of(self, text: str) -> List[int]:
        """BPE mouth first. Word ids if the encoder is missing."""
        xf = self.transformer
        if xf is not None and hasattr(xf, "from_bpe"):
            return list(xf.from_bpe(text or "", getattr(self, "bpe", None)))
        from skeleton.cortex.port import tokens as _tok
        return list(_tok(text or ""))

    def to(self, device: str = "auto") -> Dict[str, Any]:
        """Harness GPU if present. Degrades to CPU without throwing."""
        from skeleton.cortex.device import attach_lm, probe, resolve
        from skeleton.cortex.lm import gameforge_vocab
        info = resolve(device)
        self._device_info = probe()
        xf = self.transformer
        if hasattr(xf, "to"):
            want = info["actual"]
            if want == "cpu" and info.get("torch") and info.get("requested") in {"cuda", "gpu", "torch", "auto"}:
                want = "torch"
            xf.to(want if info.get("cuda") or want != "cuda" else "cpu")
        else:
            snap = xf.snapshot() if hasattr(xf, "snapshot") else {}
            self.transformer = attach_lm(
                vocab=gameforge_vocab(), dim=8, ctx=8, seed=19,
                n_heads=2, n_layers=2, d_ff=32, device=info["actual"],
            )
            if snap and hasattr(self.transformer, "from_snapshot"):
                pass
        rms = getattr(self, "neo_rms", None)
        if rms is not None and hasattr(rms, "to"):
            try:
                want_rms = info["actual"]
                if want_rms == "cpu" and info.get("torch") and info.get("requested") in {"cuda", "gpu", "torch", "auto"}:
                    want_rms = "torch"
                rms.to(want_rms if info.get("cuda") or want_rms != "cuda" else "cpu")
            except Exception:
                pass
        return {
            "requested": info["requested"],
            "actual": getattr(self.transformer, "device", info["actual"]),
            "neo_rms_device": str(getattr(getattr(self, "neo_rms", None), "device", "cpu") or "cpu"),
            "neo_rms_resident": bool(getattr(getattr(self, "neo_rms", None), "resident", False)),
            "degraded": bool(info.get("degraded")),
            "cuda": bool(info.get("cuda")),
            "backend": type(self.transformer).__name__,
            "resident": bool(getattr(self.transformer, "resident", False)),
            "capability": str(info.get("capability") or "python"),
        }

    def _lm_amalgam(self, stim: str, composed: Thought, jaccard: float) -> Thought:
        """Neo transformer speaks. Compose keeps numbers and acquired text.

        Unfitted net falls back to compose (tape). Fitted net is the LM.
        Decode on the bound device (CPU default, CUDA if harnessed).
        MoE mix stitches in when the left expert is fitted and compose
        has no mix numbers of its own.
        """
        xf = self.transformer
        mouth_name = "gelu"
        winner = getattr(self, "_winner_mouth", None)
        if winner == "neo_rms" and getattr(self, "neo_rms", None) is not None:
            xf = self.neo_rms
            mouth_name = "rms"
        seed = int(fingerprint(stim)[:8], 16) if stim else 0
        gen = ""
        if xf is not None and hasattr(xf, "decode"):
            gen = str(xf.decode(stim or "", n=14, seed=seed) or "")
        tags = tuple(dict.fromkeys(list(composed.tags) + ["lm", "neo", "own", "surpass", mouth_name]))
        numbers = composed.numbers
        moe_mix = self.moe.predict_mix(self._hidden(stim))
        if moe_mix is not None and (not numbers or len(numbers) < 3):
            numbers = tuple(float(x) for x in moe_mix)
            tags = tuple(dict.fromkeys(list(tags) + ["moe", "mix"]))
        body = gen.strip() or (composed.text or "")
        return Thought(
            slot="neo",
            kind="own-lm",
            text=body,
            confidence=min(1.0, 0.58 + 0.35 * float(jaccard or 0.0)),
            tags=tags,
            numbers=numbers,
        )

    def _maybe_auto_surpass(self) -> None:
        own = self.shadow.get("own") or {}
        trials = int(own.get("trials") or 0)
        wins = int(own.get("wins") or 0)
        if trials >= AUTO_TRIALS and (wins / trials) >= AUTO_RATE:
            for s in SLOTS:
                if s not in self._surpass:
                    self._surpass.add(s)
                    self._bus.emit("cortex.auto_surpass", {"slot": s, "rate": wins / trials})

    def _amalgam(self, pfc: Thought, left: Optional[Thought],
                 right: Optional[Thought], route: Thought, hive: float) -> Thought:
        if pfc.numbers and pfc.numbers[-1] >= 1.0:
            return Thought(
                slot="neo", kind="amalgam", text=pfc.text,
                confidence=pfc.confidence, tags=("veto", "neo") + pfc.tags,
            )
        parts = [f"[PFC] {pfc.text}"]
        tags = ["neo", "amalgam"]
        if left:
            parts.append(f"[L] {left.text}")
            tags.append("left")
        if right:
            parts.append(f"[R] {right.text}")
            tags.append("right")
        parts.append(f"[HIVE {hive:.2f}] {route.text}")
        conf = min(1.0, 0.45 * pfc.confidence + 0.55 * hive)
        return Thought(
            slot="neo", kind="amalgam", text=" || ".join(parts),
            confidence=conf, tags=tuple(tags),
            numbers=(hive, pfc.confidence),
        )
