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
from skeleton.kernel.events import DomainEvent, EventBus
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
    mouth: str = "neo"
    G: float = 1.0
    law: str = "ok"
    improve: Optional[Dict[str, Any]] = None

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
            "mouth": self.mouth,
            "G": round(float(self.G), 6),
            "law": self.law,
            "improve": self.improve,
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
        from skeleton.cortex.device import probe
        from skeleton.cortex.lm import gameforge_vocab
        from skeleton.cortex.production_profile import build_initial_speaking_model
        # An explicit nonlegacy profile configures initial capacity only.
        # On restoring SKELETON_OWN, the saved production architecture remains
        # authoritative; profile selection never silently migrates weights.
        self.transformer = build_initial_speaking_model(
            vocab=gameforge_vocab(), seed=19,
        )
        from skeleton.cortex.transformer import TinyTransformer
        self.neo_rms = TinyTransformer(
            vocab=gameforge_vocab(), dim=8, ctx=8, seed=23,
            n_heads=2, n_layers=2, d_ff=32, norm="rms", ffn_kind="swiglu",
        )
        self.backup_transformer = TinyTransformer(
            vocab=gameforge_vocab(), dim=8, ctx=8, seed=29,
            n_heads=2, n_layers=2, d_ff=32, norm="ln", ffn_kind="gelu",
        )
        self._device_info = probe()
        dim = int(getattr(self.transformer, "dim", 8) or 8)
        self.callosum = CorpusCallosum(dim=dim, seed=17)
        self.moe = ExpertBank(dim=dim, seed=19)
        self.sleep = SleepCycle(seed=23)
        self.rl = ReinforceState()
        from skeleton.cortex.bpe import gameforge_bpe
        self.bpe = gameforge_bpe(merges=64)
        self.transformer.bpe = self.bpe
        self.neo_rms.bpe = self.bpe
        self.backup_transformer.bpe = self.bpe
        if hasattr(self.transformer, "tie"):
            self.transformer.tie()
        if hasattr(self.backup_transformer, "tie"):
            self.backup_transformer.tie()
        if hasattr(self.transformer, "checkpoint_redundant_standby"):
            self.transformer.checkpoint_redundant_standby()
        if hasattr(self.neo_rms, "checkpoint_redundant_standby"):
            self.neo_rms.checkpoint_redundant_standby()
        if hasattr(self.backup_transformer, "checkpoint_redundant_standby"):
            self.backup_transformer.checkpoint_redundant_standby()
        for port in self.slots.values():
            xf = getattr(port, "transformer", None)
            if xf is not None:
                xf.bpe = self.bpe
        self._winner_mouth = "neo"
        self._mouth_override = None
        self._seal: Dict[str, Any] = {}
        from skeleton.cortex.contact import ContactEngine
        from skeleton.cortex.genos import Genos
        from skeleton.cortex.own import (
            AdaptiveSequentialDecompiler,
            JeevesCognitiveToolSuite,
            RepetitionTrainingAutomation,
            ZeroShotBlueprintCompiler,
        )
        from skeleton.cortex.rl import DPOPreferenceOptimizer
        self.contact_engine = ContactEngine()
        self.genos_engine = Genos()
        self.repetition_automation = RepetitionTrainingAutomation()
        self.blueprint_compiler = ZeroShotBlueprintCompiler()
        self.decompiler = AdaptiveSequentialDecompiler()
        self.tool_suite = JeevesCognitiveToolSuite(self)
        self.massive_steps_completed: int = 0
        self.dpo_optimizer = DPOPreferenceOptimizer()

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

    def bind_hf(self, slot: str, model_id: str = "sshleifer/tiny-gpt2") -> Dict[str, Any]:
        from skeleton.cortex.interchange import HuggingFaceBackend, probe_interchange
        backends = self.bind(slot, HuggingFaceBackend(model_id, slot=slot))
        return {"backends": backends, "probe": probe_interchange(), "model_id": model_id}

    def bind_kimi(self, slot: str, model: str = "kimi-k2-0711-preview") -> Dict[str, Any]:
        from skeleton.cortex.interchange import KimiBackend, probe_interchange
        backends = self.bind(slot, KimiBackend(model, slot=slot))
        return {"backends": backends, "probe": probe_interchange(), "model": model}

    def distill(self, slot: str, stimulus: str) -> Dict[str, Any]:
        from skeleton.cortex.interchange import distill_teacher
        out = distill_teacher(self, slot, stimulus)
        out["contact"] = self.contact(slot, stimulus)
        return out

    def contact(self, slot: str, stimulus: str = "") -> Dict[str, Any]:
        return self.contact_engine.touch(self, slot, stimulus)

    def genos(self, stimulus: str = "plan tensor ttk lattice soulslike") -> Dict[str, Any]:
        return self.genos_engine.pulse(self, stimulus=stimulus)

    def gate(self, fid: str, *, slot: str = "left", model: str | None = None, modality: str = "text") -> Dict[str, Any]:
        from skeleton.cortex.gates import bind_gate
        return bind_gate(self, fid, slot=slot, model=model, modality=modality)

    def acquire_gaming(self, *, appid: int = 1245620, title: str = "Elden Ring") -> Dict[str, Any]:
        from skeleton.cortex.acquire_repo import acquire_gaming
        return acquire_gaming(self, appid=appid, title=title)

    def acquire_spree(self) -> Dict[str, Any]:
        from skeleton.cortex.acquire_repo import acquire_spree
        return acquire_spree(self)

    def refer(self, stimulus: str, *, live: bool = False) -> Dict[str, Any]:
        from skeleton.cortex.refs import refer
        return refer(stimulus, live=live)

    def improve(self, stimulus: str, *, rounds: int = 16) -> Dict[str, Any]:
        from skeleton.cortex.improve import improve
        return improve(self, stimulus, rounds=rounds)

    def ascend(self, stimulus: str, *, rounds: int = 8) -> Dict[str, Any]:
        from skeleton.cortex.laws import check
        from skeleton.cortex.metrics import evaluate
        card = self.improve(stimulus, rounds=rounds)
        if not card.get("improved"):
            return card
        if hasattr(self, "elect_mouth"):
            card["mouth"] = (self.elect_mouth() or {}).get("winner")
        if hasattr(self, "sleep_cycle"):
            card["sleep"] = self.sleep_cycle(n=4)
        card["eval"] = evaluate(self)
        card["kind"] = "ascend"
        slim = {k: v for k, v in card.items() if k not in {"eval", "sleep", "mouth"}}
        slim["kind"] = "ascend"
        slim["eval_ppl"] = (card.get("eval") or {}).get("ppl")
        out = check(slim)
        out["eval"] = card.get("eval")
        out["sleep"] = card.get("sleep")
        out["mouth"] = card.get("mouth")
        return out

    def bind_ref(self, slot: str = "right") -> Dict[str, str]:
        from skeleton.cortex.refs import GameRefPort
        return self.bind(slot, GameRefPort(slot=slot))

    def _contact_if_teacher(self, slot: str, stimulus: str) -> None:
        from skeleton.cortex.contact import is_teacher
        port = self.slots.get(slot)
        if port is not None and is_teacher(port):
            self.contact_engine.touch(self, slot, stimulus)

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

        ref = self.refer(stim)
        if ref.get("hit"):
            ctx["reference"] = ref["ref"]
            stim = f"{stim} {ref['ref'].get('dialect') or ''}".strip()
        if "like " in (stimulus or "").lower() and ref.get("hit"):
            ctx["improve"] = self.ascend(stimulus or "")

        route = self.slots["midbrain"].think(stim, ctx)
        self.ledger.record(route, stim)

        left = right = None
        lw = route.numbers[1] if len(route.numbers) > 1 else 0.55
        rw = route.numbers[2] if len(route.numbers) > 2 else 0.55
        if lw >= 0.25:
            left = self.slots["left"].think(stim, {**ctx, "route": route.to_dict()})
            self.ledger.record(left, stim)
            self._contact_if_teacher("left", stim)
        if rw >= 0.25:
            right = self.slots["right"].think(stim, {**ctx, "route": route.to_dict()})
            self.ledger.record(right, stim)
            self._contact_if_teacher("right", stim)

        pfc_ctx = {**ctx}
        if left:
            pfc_ctx["left"] = left.to_dict()
        if right:
            pfc_ctx["right"] = right.to_dict()
        pfc = self.slots["pfc"].think(stim, pfc_ctx)
        self.ledger.record(pfc, stim)
        self._contact_if_teacher("pfc", stim)
        self._contact_if_teacher("midbrain", stim)

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
            mouth=self.speaking_name(),
            G=float(getattr(self.genos_engine, "G", 1.0) or 1.0),
            law="ok",
            improve=ctx.get("improve") if isinstance(ctx.get("improve"), dict) else None,
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
        lora_info: Dict[str, Any] = {"attached": []}
        if src is not None:
            from skeleton.cortex.gossip import absorb_mouth
            if getattr(self.transformer, "lora", None) is None and hasattr(self, "attach_lora"):
                lora_info = self.attach_lora(rank=2)
            absorb = absorb_mouth(self.transformer, src, alpha=0.2)
            if getattr(self, "neo_rms", None) is not None:
                absorb["neo_rms"] = absorb_mouth(self.neo_rms, src, alpha=0.1)
        self._bus.emit("cortex.acquired", {"slot": slot, "copied": copied, "expert": stamped, "model": model})
        return {
            "slot": slot, "copied": copied, "acquired": dict(self.acquired),
            "own": self.own.size, "expert": stamped,
            "model": model, "absorb": absorb, "models": sorted(self.own.models),
            "lora": lora_info,
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

    def predict_pacing(self, stimulus: str):
        return self.moe.predict_pacing(self._stream(stimulus))

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
        out = run_curriculum(self, epochs=epochs, auto_surpass=auto_surpass)
        seal = self.elect_mouth()
        out["mouth"] = seal.get("winner")
        out["seal"] = seal
        return out

    def apply_gaming_weights(self, *, rounds: int = 2) -> Dict[str, Any]:
        """Apply beneficial gaming and game-adjacent weight priors across the cortex."""
        from skeleton.cortex.improve import apply_gaming_priors
        return apply_gaming_priors(self, rounds=rounds)

    def upgrade_capacity(
        self,
        *,
        extra_layers: int = 1,
        lora_rank: int = 4,
    ) -> Dict[str, Any]:
        """Acquire capability and progressively increase model depth and LoRA rank."""
        from skeleton.cortex.production_profile import plan_capacity_escalation

        xf = self.transformer
        rms = getattr(self, "neo_rms", None)
        depth_info = {}
        if xf is not None and hasattr(xf, "expand_depth") and extra_layers > 0:
            depth_info["neo"] = xf.expand_depth(extra_layers=extra_layers)
        if rms is not None and hasattr(rms, "expand_depth") and extra_layers > 0:
            depth_info["neo_rms"] = rms.expand_depth(extra_layers=extra_layers)

        if getattr(xf, "lora", None) is None:
            self.attach_lora(rank=max(2, int(lora_rank)), alpha=float(max(4, lora_rank * 2)))
        else:
            xf.lora.expand_rank(int(lora_rank))
            if rms is not None and getattr(rms, "lora", None) is not None:
                rms.lora.expand_rank(int(lora_rank))

        acquired_slots = {}
        for slot in SLOTS:
            acquired_slots[slot] = self.acquire(slot)["copied"]

        G = float(getattr(self.genos_engine, "G", 1.0) or 1.0)
        streak = int(getattr(getattr(self.genos_engine, "ratchet", None), "streak", 0) or 0)
        plan = plan_capacity_escalation("legacy", genos_g=G, ratchet_streak=streak)
        return {
            "depth": depth_info,
            "lora": xf.lora.to_dict() if getattr(xf, "lora", None) is not None else None,
            "acquired_slots": acquired_slots,
            "escalation_plan": plan,
        }

    def self_learn_cycle(
        self,
        stimuli: Optional[Sequence[str]] = None,
        *,
        rounds: int = 2,
        apply_gaming: bool = True,
        grow_on_streak: bool = False,
    ) -> Dict[str, Any]:
        """Enterprise self-learning cycle guarded by the adaptive quality ratchet."""
        from skeleton.cortex.curriculum import CORE_PAIRS, WALK_PAIRS
        from skeleton.cortex.gossip import adaptive_gossip

        rounds = max(1, min(16, int(rounds)))
        eval_texts = [a for a, _ in list(CORE_PAIRS)] + [a for a, _ in list(WALK_PAIRS)]
        texts = list(stimuli) if stimuli else eval_texts
        ratchet = self.genos_engine.ratchet

        def _inner_step(lr_scale: float) -> Dict[str, Any]:
            base_lr = max(0.01, min(0.08, 0.04 * float(lr_scale)))
            for text in texts[:6]:
                self.think(text)
            for slot in SLOTS:
                port = self.slots.get(slot)
                w = getattr(port, "weights", None)
                if w is not None and hasattr(w, "self_learn"):
                    w.self_learn(texts[:4], epochs=1, lr=base_lr)
                elif port is not None and hasattr(port, "fit"):
                    for text in texts[:4]:
                        port.fit(text)
            for slot in SLOTS:
                self.acquire(slot)
            sleep_info = self.sleep_cycle(n=6)
            pulse = self.genos(texts[0] if texts else "plan tensor ttk")
            xf = self.transformer
            if xf is not None and hasattr(xf, "specialized_calibrate"):
                xf.specialized_calibrate(texts, epochs=rounds, lr=base_lr, weight_decay=1e-4, holdout=eval_texts)
            rms = getattr(self, "neo_rms", None)
            if rms is not None and hasattr(rms, "specialized_calibrate"):
                rms.specialized_calibrate(texts, epochs=max(1, rounds // 2), lr=base_lr, weight_decay=1e-4, holdout=eval_texts)
            if xf is not None and rms is not None:
                adaptive_gossip(xf, rms, eval_texts, max_alpha=0.20)
            if apply_gaming:
                self.apply_gaming_weights(rounds=max(1, rounds // 2))
            self.sync_backup_transformer()
            return {"sleep": sleep_info, "pulse": pulse, "lr_used": round(base_lr, 4)}

        verdict = ratchet.step(self, _inner_step)
        capacity_upgrade = None
        if grow_on_streak and verdict.get("passed") and int(verdict.get("streak") or 0) >= 1:
            capacity_upgrade = self.upgrade_capacity(extra_layers=1, lora_rank=4)
        return {
            "ratchet": verdict,
            "capacity_upgrade": capacity_upgrade,
            "mouth": self.speaking_name(),
            "G": round(float(self.genos_engine.G), 6),
        }

    def finetune_for_game_creation(
        self,
        *,
        epochs: int = 2,
        rounds: int = 2,
        include_az_curricula: bool = True,
        grow_capacity: bool = False,
    ) -> Dict[str, Any]:
        """Comprehensive multi-stage game creation finetuning across all cortex substrates."""
        from skeleton.ai.runtime.inference.game_self_learn import (
            GAME_CREATION_STAGES,
            pareto_weighted_curriculum,
        )
        from skeleton.cortex.curriculum import CORE_PAIRS, WALK_PAIRS
        from skeleton.cortex.gossip import adaptive_gossip

        epochs = max(1, min(8, int(epochs)))
        rounds = max(1, min(8, int(rounds)))

        base_train = self.train(epochs=epochs, auto_surpass=True)
        gaming_priors = self.apply_gaming_weights(rounds=rounds)

        stage_summaries: List[Dict[str, Any]] = []
        eval_texts = [a for a, _ in list(CORE_PAIRS)] + [a for a, _ in list(WALK_PAIRS)]
        if include_az_curricula:
            for idx, stage_name in enumerate(GAME_CREATION_STAGES):
                rows = pareto_weighted_curriculum(stage=stage_name, min_pareto_score=14)
                stage_docs = [str(r["text"]) for r in rows[:8]]
                if not stage_docs:
                    continue
                stage_lr = max(0.01, 0.035 * (0.88 ** idx))
                for doc in stage_docs[:4]:
                    self.think(doc)
                for slot in SLOTS:
                    port = self.slots.get(slot)
                    w = getattr(port, "weights", None)
                    if w is not None and hasattr(w, "self_learn"):
                        w.self_learn(stage_docs[:4], epochs=1, lr=stage_lr)
                    elif port is not None and hasattr(port, "fit"):
                        for doc in stage_docs[:4]:
                            port.fit(doc)
                stage_summaries.append({
                    "stage": stage_name,
                    "lessons_ingested": len(stage_docs),
                    "lr": round(stage_lr, 4),
                })

        xf = self.transformer
        rms = getattr(self, "neo_rms", None)
        if xf is not None and hasattr(xf, "specialized_calibrate"):
            xf.specialized_calibrate(eval_texts, epochs=rounds, lr=0.035, weight_decay=1e-4, holdout=eval_texts)
        if rms is not None and hasattr(rms, "specialized_calibrate"):
            rms.specialized_calibrate(eval_texts, epochs=max(1, rounds // 2), lr=0.03, weight_decay=1e-4, holdout=eval_texts)
        if xf is not None and rms is not None:
            adaptive_gossip(xf, rms, eval_texts, max_alpha=0.20)

        for slot in SLOTS:
            self.acquire(slot)
            self.surpass(slot)

        sleep_out = self.sleep_cycle(n=8)
        self.sync_backup_transformer()
        seal = self.elect_mouth(texts=eval_texts)
        cap_out = self.upgrade_capacity(extra_layers=1, lora_rank=4) if grow_capacity else None
        from skeleton.cortex.metrics import evaluate as _eval_metrics
        metrics = _eval_metrics(self)

        return {
            "kind": "cortex-game-creation-finetune",
            "curriculum_train": base_train,
            "gaming_priors": gaming_priors,
            "stages": stage_summaries,
            "sleep": sleep_out,
            "mouth": seal.get("winner"),
            "capacity_upgrade": cap_out,
            "metrics": metrics,
            "G": round(float(self.genos_engine.G), 6),
        }

    def plan_game_spec(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich a `skeleton.game_design_spec.v1` using cortex hemispheres, PFC, and MoE."""
        if not isinstance(spec, dict):
            return spec
        brief_text = str(spec.get("brief") or spec.get("fantasy") or spec.get("title") or "playable game")
        era = str(spec.get("era") or "extraction_now")
        genre = str(spec.get("genre") or "action")

        stim = f"{era} {genre} {brief_text}".strip()
        trace = self.think(stim, {"era": era, "genre": genre})

        left_port = self.slots.get("left")
        right_port = self.slots.get("right")
        pfc_port = self.slots.get("pfc")

        math_env = (
            left_port.analyze_game_math(stim, {"era": era})
            if hasattr(left_port, "analyze_game_math")
            else {}
        )
        spatial_env = (
            right_port.synthesize_spatial_aesthetic_profile(stim, {"era": era})
            if hasattr(right_port, "synthesize_spatial_aesthetic_profile")
            else {}
        )
        slice_plan = (
            pfc_port.plan_game_slice(stim, {"era": era, "genre": genre})
            if hasattr(pfc_port, "plan_game_slice")
            else {}
        )
        coop = self.moe.cooperate(self._stream(stim))

        mix = coop.get("mix") or (
            tuple(math_env.get("encounter_mix", {}).values())
            if isinstance(math_env.get("encounter_mix"), dict)
            else (3, 1, 0)
        )
        bias = coop.get("bias") or spatial_env.get("spatial_bias") or "balanced"
        pacing = coop.get("pacing") or {}
        ttk_targets = math_env.get("ttk_targets") or {"trash": 1.1, "elite": 4.5, "boss": 60.0}
        fixed_tick = math_env.get("fixed_tick") or {"hz": 60, "frame_budget_ms": 16.67}
        econ = math_env.get("economy_equilibrium") or {"tap_sink_ratio": 0.82}
        art = spatial_env.get("art_scale_ladder") or {"authoring_divisor": 2, "palette_profile": "hearth_linen_readable"}
        audio = spatial_env.get("audio_cadence") or {"bpm": 116}
        readability = spatial_env.get("combat_readability") or {"telegraph_ticks": 18}

        existing_prod = dict(spec.get("production") or {}) if isinstance(spec.get("production"), dict) else {}
        enriched_prod: Dict[str, str] = {}
        for k, v in existing_prod.items():
            if isinstance(k, str) and isinstance(v, str) and len(enriched_prod) < 4:
                enriched_prod[k[:32]] = v[:240]

        cortex_notes = {
            "cortex_mouth": f"{trace.mouth} hive={trace.hive_value:.2f} G={trace.G:.3f}",
            "encounter_mix": f"trash={mix[0]} elite={mix[1]} boss={mix[2]} bias={bias}",
            "ttk_envelope": (
                f"dps={math_env.get('primary_dps', 108.0)} "
                f"trash={ttk_targets.get('trash', 1.1)}s "
                f"elite={ttk_targets.get('elite', 4.5)}s "
                f"boss={ttk_targets.get('boss', 60.0)}s"
            ),
            "thermal_budget": (
                f"vent_duty={math_env.get('vent_duty_cycle', 0.0)} "
                f"thermal_mult={math_env.get('thermal_multiplier', 1.0)} "
                f"collapse_max={math_env.get('collapse_max_s', 320.0)}s"
            ),
            "fixed_tick_contract": (
                f"{fixed_tick.get('hz', 60)}Hz dt={fixed_tick.get('dt_s', 0.016667)}s "
                f"budget={fixed_tick.get('frame_budget_ms', 16.67)}ms catchup=4"
            ),
            "level_topology": (
                f"{spatial_env.get('level_topology', 'landmark_spoke_region')} "
                f"telegraph={readability.get('telegraph_ticks', 18)}t "
                f"bpm={audio.get('bpm', 116)}"
            ),
            "art_scale_ladder": (
                f"divisor={art.get('authoring_divisor', 2)} "
                f"palette={art.get('palette_profile', 'hearth_linen_readable')} "
                f"no_65536_alloc=true"
            ),
            "economy_pacing": (
                f"tap_sink={econ.get('tap_sink_ratio', 0.82)} "
                f"ttk_norm={pacing.get('ttk_norm', 0.6)} "
                f"core_verb={slice_plan.get('core_verb', genre)}"
            ),
        }
        for k, v in cortex_notes.items():
            if len(enriched_prod) < 12:
                enriched_prod[k[:32]] = str(v)[:240]

        out = dict(spec)
        out["production"] = enriched_prod
        return out

    def review_game_build(self, build: Dict[str, Any]) -> Dict[str, Any]:
        """Inspect a proved game build, score quality, and request repair if recoverable."""
        if not isinstance(build, dict):
            return {"passed": False, "issues": [{"severity": "blocker", "source": "cortex_qa", "detail": "invalid build"}], "repair_requested": False}

        spec = build.get("spec") if isinstance(build.get("spec"), dict) else {}
        check_info = build.get("check") if isinstance(build.get("check"), dict) else {}
        core_loop = build.get("core_loop") if isinstance(build.get("core_loop"), dict) else {}
        playtest_info = build.get("playtest") if isinstance(build.get("playtest"), dict) else None
        files = build.get("files") if isinstance(build.get("files"), dict) else {}

        issues: List[Dict[str, Any]] = []
        repair_requested = False

        check_ok = bool(check_info.get("ok", True))
        problems = [str(p) for p in (check_info.get("problems") or [])]
        if not check_ok or problems:
            for prob in problems[:6]:
                issues.append({"severity": "blocker", "source": "gdscript_check", "detail": prob})
            if not any("deadline exceeded" in p for p in problems):
                repair_requested = True

        loop_passed = bool(core_loop.get("passed", True))
        if not loop_passed and core_loop:
            issues.append({
                "severity": "blocker",
                "source": "core_loop",
                "detail": f"core loop marker failed: {core_loop.get('marker')!r}",
            })
            repair_requested = True

        if files and "project.godot" not in files:
            issues.append({
                "severity": "blocker",
                "source": "project_structure",
                "detail": "missing project.godot in emitted files",
            })
            repair_requested = True

        if playtest_info is not None:
            status = str(playtest_info.get("status") or "")
            if status not in {"", "passed", "unavailable"} and not playtest_info.get("passed", False):
                issues.append({
                    "severity": "blocker",
                    "source": "playtest",
                    "detail": f"playtest status={status}",
                })
                if status != "unavailable":
                    repair_requested = True

        era = str(spec.get("era") or "extraction_now")
        genre = str(spec.get("genre") or "action")
        stim = f"qa review {era} {genre} files={len(files)} ok={bool(build.get('ok'))}"
        trace = self.think(stim, {"era": era, "genre": genre})
        scrutiny = self.hyper_scrutinize(build, console_target=era)
        innsight_out = self.innsight_outrospect(stim, {"era": era, "genre": genre})

        passed = bool(build.get("ok", False)) and len(issues) == 0
        return {
            "passed": passed,
            "issues": issues,
            "repair_requested": repair_requested and not passed,
            "cortex_review": {
                "mouth": trace.mouth,
                "hive_confidence": round(trace.hive_value, 4),
                "genos_G": round(trace.G, 4),
                "era": era,
                "genre": genre,
                "file_count": len(files),
                "scrutiny_factor": scrutiny.get("scrutiny_factor"),
                "review_factor": scrutiny.get("review_factor"),
                "hemispheric_resonance": innsight_out.get("innsight", {}).get("hemispheric_resonance"),
            },
            "hyper_scrutiny": scrutiny,
            "innsight_outrospect": innsight_out,
        }

    def learn_from_game_build(self, build_result: Dict[str, Any]) -> Dict[str, Any]:
        """Close the self-learning loop from a completed game build, simulation, and walk."""
        if not isinstance(build_result, dict):
            return {"learned": 0}
        spec = build_result.get("spec") if isinstance(build_result.get("spec"), dict) else {}
        pipeline = build_result.get("pipeline") if isinstance(build_result.get("pipeline"), dict) else {}
        operator = build_result.get("_operator") if isinstance(build_result.get("_operator"), dict) else {}
        era = str(spec.get("era") or pipeline.get("era") or operator.get("era") or "extraction_now")
        genre = str(spec.get("genre") or "action")
        ok = bool(build_result.get("ok"))

        sim_data = operator.get("sim") if isinstance(operator.get("sim"), dict) else {}
        walk_data = sim_data.get("walk") if isinstance(sim_data.get("walk"), dict) else {}
        collapse_max = float(walk_data.get("collapse_max") or sim_data.get("collapse_max") or 320.0)
        walk_t = float(walk_data.get("t") or (collapse_max * 0.35 if ok else collapse_max))
        slack = max(0.0, min(1.0, (collapse_max - walk_t) / max(collapse_max, 1.0))) if ok else 0.0

        left_port = self.slots.get("left")
        math_env = (
            left_port.analyze_game_math(f"{era} {genre}", {"era": era})
            if hasattr(left_port, "analyze_game_math")
            else {}
        )
        mix_dict = math_env.get("encounter_mix") or {"trash": 4, "elite": 1, "boss": 0}
        mix_tuple = (
            int(mix_dict.get("trash", 4)),
            int(mix_dict.get("elite", 1)),
            int(mix_dict.get("boss", 0)),
        )

        observed_stim = (
            f"HP = DPS x TTK ; observed mix trash={mix_tuple[0]} "
            f"elite={mix_tuple[1]} boss={mix_tuple[2]} slack={slack:.2f} {era.replace('_', ' ')}"
        )
        self.think(observed_stim, {"era": era, "genre": genre})
        from skeleton.cortex.curriculum import _ingest_observed_mix
        _ingest_observed_mix(self, observed_stim)

        reward = round((0.65 * slack + 0.35 * (1.0 if ok else 0.0)), 4)
        rl_info = self.reinforce(observed_stim, mix_tuple, reward)

        h = self._stream(observed_stim)
        if "left" in self.moe.experts and getattr(self.moe.experts["left"], "aux", None) is not None:
            thermal_margin = max(0.0, min(1.0, 1.0 - float(walk_data.get("heat_peak", 40.0)) / 100.0))
            self.moe.experts["left"].aux.step(
                h,
                (slack, thermal_margin, 0.82, 0.78),
                lr=0.10,
            )

        for slot in SLOTS:
            port = self.slots.get(slot)
            if port is not None and hasattr(port, "fit"):
                port.fit(observed_stim)
            self.acquire(slot)

        sleep_info = self.sleep_cycle(n=4)
        return {
            "learned": 1,
            "era": era,
            "genre": genre,
            "ok": ok,
            "slack": round(slack, 4),
            "reward": reward,
            "mix": mix_tuple,
            "reinforce": rl_info,
            "sleep": sleep_info,
            "own_size": self.own.size,
        }

    def build_and_learn_game(
        self,
        brief: str | Dict[str, Any],
        *,
        era: str | None = None,
        playtest_mode: str = "off",
        max_rounds: int = 2,
        deadline_s: float | None = 120.0,
    ) -> Dict[str, Any]:
        """End-to-end cortex-guided game creation: plan -> build -> QA -> self-learn."""
        from skeleton.forge.game_builder import build_playable_game, cortex_planner_hook, cortex_qa_hook

        planner = cortex_planner_hook(self)
        qa = cortex_qa_hook(self, learn=False)
        result = build_playable_game(
            brief,
            era=era,
            playtest_mode=playtest_mode,
            max_rounds=max_rounds,
            planner=planner,
            qa=qa,
            deadline_s=deadline_s,
        )
        learning = self.learn_from_game_build(result)
        return {
            "build": result,
            "learning": learning,
        }

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
            "backup_transformer": self.backup_transformer.snapshot() if getattr(self, "backup_transformer", None) is not None else None,
            "callosum": self.callosum.snapshot(),
            "moe": self.moe.snapshot(),
            "sleep": self.sleep.snapshot(),
            "rl": self.rl.snapshot(),
            "bpe": self.bpe.snapshot(),
            "winner": self._winner_mouth,
            "mouth_override": self._mouth_override,
            "contact": self.contact_engine.snapshot(),
            "genos": self.genos_engine.snapshot(),
        }
        # Never truncate live weights on a crash or overwrite a symlink.
        # Temporary and destination are on the same filesystem for os.replace.
        import os
        import tempfile
        if p.is_symlink():
            raise CortexError("refusing symlink as Jeeves production state")
        raw = json.dumps(blob, ensure_ascii=False, allow_nan=False).encode("utf-8")
        staged = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=".jeeves-cortex-", suffix=".tmp",
                dir=p.parent, delete=False,
            ) as handle:
                staged = Path(handle.name)
                os.chmod(staged, 0o600)
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            if p.is_symlink():
                raise CortexError("Jeeves persistence target changed into symlink")
            os.replace(staged, p)
            staged = None
            if os.name == "posix":
                fd = os.open(p.parent, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)
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
                # Failure to restore the actual torch architecture must not
                # silently replace its trained weights with a random native LM.
                from skeleton.cortex.torch_lm import TorchTransformer
                self.transformer = TorchTransformer.from_snapshot(snap)
            else:
                from skeleton.cortex.transformer import TinyTransformer
                self.transformer = TinyTransformer.from_snapshot(snap)
        if blob.get("neo_rms"):
            rms_snapshot = blob["neo_rms"]
            if (rms_snapshot or {}).get("kind") == "torch-stack":
                from skeleton.cortex.torch_lm import TorchTransformer
                self.neo_rms = TorchTransformer.from_snapshot(rms_snapshot)
            else:
                from skeleton.cortex.transformer import TinyTransformer
                self.neo_rms = TinyTransformer.from_snapshot(rms_snapshot)
        if blob.get("backup_transformer"):
            backup_snap = blob["backup_transformer"]
            if (backup_snap or {}).get("kind") == "torch-stack":
                from skeleton.cortex.torch_lm import TorchTransformer
                self.backup_transformer = TorchTransformer.from_snapshot(backup_snap)
            else:
                from skeleton.cortex.transformer import TinyTransformer
                self.backup_transformer = TinyTransformer.from_snapshot(backup_snap)
        if blob.get("winner"):
            self._winner_mouth = str(blob.get("winner") or "neo")
        if "mouth_override" in blob:
            self._mouth_override = blob.get("mouth_override")
        if blob.get("contact"):
            self.contact_engine.restore(blob.get("contact"))
        if blob.get("genos"):
            self.genos_engine.restore(blob.get("genos"))
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
        # Bind the restored encoder, not the bootstrap encoder.  This must
        # happen AFTER loading the saved BPE vocabulary and merge rules so
        # that resumed production inference uses the tokenizer it persisted.
        if getattr(self, "bpe", None) is not None:
            self.transformer.bpe = self.bpe
            if getattr(self, "neo_rms", None) is not None:
                self.neo_rms.bpe = self.bpe
            if getattr(self, "backup_transformer", None) is not None:
                self.backup_transformer.bpe = self.bpe
        return {"loaded": n, "own": self.own.size, "surpass": sorted(self._surpass)}

    def recent_events(self, topic: str = "*", n: int = 20) -> List[DomainEvent]:
        """Read the shared bus's bounded replay window without a second log."""
        if isinstance(n, bool) or not isinstance(n, int) or n < 0:
            raise ValueError("n must be a non-negative integer")
        return self._bus.replay(topic)[-n:] if n else []

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
            "genos": self.genos_engine.snapshot() if getattr(self, "genos_engine", None) else None,
            "massive_steps_completed": int(getattr(self, "massive_steps_completed", 0) or 0),
            "ai_tools_count": len(self.list_ai_tools()),
            "law": "ok",
        }

    def mouth(self, name: str = "gelu"):
        key = str(name or "gelu").lower()
        if key in {"rms", "swiglu", "neo_rms"}:
            return getattr(self, "neo_rms", None) or self.transformer
        if key in {"backup", "standby", "backup_transformer"}:
            return getattr(self, "backup_transformer", None) or getattr(self, "neo_rms", None) or self.transformer
        if key in {"pfc", "midbrain", "left", "right"}:
            port = (getattr(self, "slots", {}) or {}).get(key)
            xf = getattr(port, "transformer", None) if port is not None else None
            return xf or self.transformer
        return self.transformer

    def sync_backup_transformer(self) -> Dict[str, Any]:
        """Synchronize the hot-standby backup transformer from the healthiest trained mouth."""
        from skeleton.cortex.gossip import absorb_mouth

        xf = self.transformer
        rms = getattr(self, "neo_rms", None)
        backup = getattr(self, "backup_transformer", None)
        if backup is None:
            return {"synced": 0, "reason": "no-backup"}

        xf_healthy = bool(xf is not None and (not hasattr(xf, "validate_finite_weights") or xf.validate_finite_weights().get("healthy", True)))
        rms_healthy = bool(rms is not None and (not hasattr(rms, "validate_finite_weights") or rms.validate_finite_weights().get("healthy", True)))

        if xf_healthy and xf is not None:
            if hasattr(xf, "checkpoint_redundant_standby"):
                xf.checkpoint_redundant_standby()
            snap = xf.snapshot()
            restored = type(backup).from_snapshot(snap)
            backup.E, backup.P, backup.Wout, backup.bout = restored.E, restored.P, restored.Wout, restored.bout
            backup.layers, backup.n_layers = restored.layers, restored.n_layers
            backup.fitted, backup.steps = restored.fitted, restored.steps
            if getattr(xf, "tied", False) and hasattr(backup, "tie"):
                backup.tie()
            if rms_healthy and rms is not None and int(getattr(rms, "steps", 0) or 0) > 0:
                absorb_mouth(backup, rms, alpha=0.15)
            if hasattr(backup, "checkpoint_redundant_standby"):
                backup.checkpoint_redundant_standby()
            return {"synced": 1, "source": "transformer", "steps": backup.steps, "layers": backup.n_layers}

        if rms_healthy and rms is not None:
            if hasattr(rms, "checkpoint_redundant_standby"):
                rms.checkpoint_redundant_standby()
            snap = rms.snapshot()
            restored = type(backup).from_snapshot(snap)
            backup.E, backup.P, backup.Wout, backup.bout = restored.E, restored.P, restored.Wout, restored.bout
            backup.layers, backup.n_layers = restored.layers, restored.n_layers
            backup.fitted, backup.steps = restored.fitted, restored.steps
            if hasattr(backup, "checkpoint_redundant_standby"):
                backup.checkpoint_redundant_standby()
            return {"synced": 1, "source": "neo_rms", "steps": backup.steps, "layers": backup.n_layers}

        return {"synced": 0, "reason": "sources-unhealthy"}

    def redundant_transformers(self) -> Dict[str, Any]:
        """Return health and capacity diagnostics across the redundant transformer ring."""
        ring: Dict[str, Dict[str, Any]] = {}
        members = [
            ("neo", self.transformer),
            ("neo_rms", getattr(self, "neo_rms", None)),
            ("backup", getattr(self, "backup_transformer", None)),
        ]
        for slot in SLOTS:
            port = self.slots.get(slot)
            xf = getattr(port, "transformer", None) if port is not None else None
            if xf is not None:
                members.append((f"slot_{slot}", xf))

        healthy_count = 0
        for name, model in members:
            if model is None:
                continue
            health = (
                model.validate_finite_weights()
                if hasattr(model, "validate_finite_weights")
                else {"healthy": True, "nonfinite_count": 0, "checked_parameters": 0}
            )
            if health.get("healthy"):
                healthy_count += 1
            ring[name] = {
                "healthy": bool(health.get("healthy")),
                "nonfinite_count": int(health.get("nonfinite_count", 0)),
                "dim": int(getattr(model, "dim", 0) or 0),
                "n_layers": int(getattr(model, "n_layers", 1) or 1),
                "steps": int(getattr(model, "steps", 0) or 0),
                "fitted": int(getattr(model, "fitted", 0) or 0),
                "norm": str(getattr(model, "norm", "ln") or "ln"),
                "ffn_kind": str(getattr(model, "ffn_kind", "gelu") or "gelu"),
            }
        return {
            "total_models": len(ring),
            "healthy_models": healthy_count,
            "quorum_ready": healthy_count >= 2,
            "ring": ring,
        }

    def backup_infer(
        self,
        stimulus: str,
        *,
        n: int = 16,
        seed: int = 0,
        consensus: bool = True,
        min_p: float = 0.05,
    ) -> Dict[str, Any]:
        """Redundant backup inference for heavy tasks with automatic health repair and quorum consensus."""
        import math
        from skeleton.cortex.curriculum import CORE_PAIRS
        from skeleton.cortex.gossip import redundant_consensus_decode

        stim = stimulus or ""
        xf = self.transformer
        rms = getattr(self, "neo_rms", None)
        backup = getattr(self, "backup_transformer", None)

        backups = [m for m in (rms, backup) if m is not None]
        for slot in SLOTS:
            port = self.slots.get(slot)
            s_xf = getattr(port, "transformer", None) if port is not None else None
            if s_xf is not None and int(getattr(s_xf, "V", -1)) == int(getattr(xf, "V", -2)):
                backups.append(s_xf)

        heavy_out = xf.heavy_task_infer(
            stim,
            n=n,
            seed=seed,
            backup_models=backups,
            min_p=min_p,
        )

        consensus_out = None
        if consensus:
            ring_models = [xf] + backups[:3]
            probe_texts = [a for a, _ in list(CORE_PAIRS)[:4]] or [stim or "soulslike ttk"]
            weights = []
            for m in ring_models:
                try:
                    ppl = float(m.perplexity(probe_texts))
                    weights.append(1.0 / max(ppl if math.isfinite(ppl) else 1e6, 1e-6))
                except Exception:
                    weights.append(1e-6)
            consensus_out = redundant_consensus_decode(
                ring_models,
                stim,
                n=n,
                seed=seed,
                weights=weights,
                min_p=min_p,
            )

        trace = self.think(stim)
        winner_text = (
            consensus_out["text"]
            if (consensus_out and consensus_out.get("quorum_agreement", 0.0) >= 0.5)
            else heavy_out["text"]
        )
        return {
            "kind": "heavy-backup-inference",
            "stimulus": stim[:160],
            "text": winner_text,
            "heavy_chunked": heavy_out,
            "consensus": consensus_out,
            "used_backup": bool(heavy_out.get("used_backup") or (consensus_out and consensus_out.get("step_failovers", 0) > 0)),
            "repaired_from_standby": bool(heavy_out.get("repaired_from_standby")),
            "failover_reason": heavy_out.get("failover_reason"),
            "hive_confidence": round(trace.hive_value, 4),
            "ring_status": self.redundant_transformers(),
        }

    def parse_shadow_weights(self) -> Dict[str, Any]:
        """Parse shadow vs. teacher trial statistics, transformer layer deltas, LoRA, and MoE heads."""
        from skeleton.cortex.own import parse_shadow_weights
        return parse_shadow_weights(self)

    def create_hyperweights(
        self,
        *,
        alpha: float = 0.30,
        rank: int = 4,
        tag_filter: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """Synthesize a content-addressed Hyperweight Bundle from verified shadow weights and MoE priors."""
        from skeleton.cortex.own import create_hyperweights
        return create_hyperweights(self, alpha=alpha, rank=rank, tag_filter=tag_filter)

    def apply_hyperweights(self, bundle: Dict[str, Any], *, blend: float = 0.25) -> Dict[str, Any]:
        """Apply a Hyperweight Bundle with coherence-gated rollback protection."""
        from skeleton.cortex.own import apply_hyperweights
        return apply_hyperweights(self, bundle, blend=blend)

    def run_repetition_automation(
        self,
        stimuli: Optional[Sequence[str]] = None,
        *,
        cycles: int = 2,
        top_k: int = 8,
        base_lr: float = 0.035,
        synthesize_hyperweights: bool = True,
    ) -> Dict[str, Any]:
        """Execute automated spaced-repetition training, shadow parsing, and hyperweight synthesis."""
        return self.repetition_automation.run_cycle(
            self,
            stimuli,
            cycles=cycles,
            top_k=top_k,
            base_lr=base_lr,
            synthesize_hyperweights=synthesize_hyperweights,
        )

    def train_console_rom_assets(
        self,
        *,
        consoles: Optional[Sequence[str]] = None,
        rounds: int = 2,
    ) -> Dict[str, Any]:
        """Train across the console and ROM asset engineering suite (8-bit DMG/NES to modern)."""
        from skeleton.cortex.improve import train_console_rom_assets
        return train_console_rom_assets(self, consoles=consoles, rounds=rounds)

    def attach_hyper_lora(self, *, ctx_dim: int = 8, rank: int = 2, alpha: float = 4.0, seed: int = 0) -> Dict[str, Any]:
        """Attach context-conditioned HyperLoRA banks to both speaking and RMS mouths."""
        xf = self.transformer
        out: Dict[str, Any] = {"attached": []}
        if xf is not None and hasattr(xf, "attach_hyper_lora"):
            out = dict(xf.attach_hyper_lora(ctx_dim=ctx_dim, rank=rank, alpha=alpha, seed=seed))
        rms = getattr(self, "neo_rms", None)
        if rms is not None and hasattr(rms, "attach_hyper_lora"):
            out["neo_rms"] = rms.attach_hyper_lora(ctx_dim=ctx_dim, rank=rank, alpha=alpha, seed=seed + 97)
        return out

    def merge_model_soup(
        self,
        *,
        density: float = 0.75,
        scaling_lambda: float = 0.85,
        slerp_blend: float = 0.25,
    ) -> Dict[str, Any]:
        """Merge specialist transformer mouths and slot transformers via TIES-Merging + SLERP Model Soup."""
        from skeleton.cortex.curriculum import CORE_PAIRS
        from skeleton.cortex.gossip import task_vector_soup_merge

        xf = self.transformer
        donors = []
        for cand in (getattr(self, "neo_rms", None), getattr(self, "backup_transformer", None)):
            if cand is not None:
                donors.append(cand)
        for slot in SLOTS:
            port = self.slots.get(slot)
            s_xf = getattr(port, "transformer", None) if port is not None else None
            if s_xf is not None:
                donors.append(s_xf)
        probe = [a for a, _ in list(CORE_PAIRS)[:6]]
        return task_vector_soup_merge(
            xf,
            donors,
            corpus=probe,
            density=density,
            scaling_lambda=scaling_lambda,
            slerp_blend=slerp_blend,
        )

    def dream_cycle(self, *, dreams: int = 6, lr: float = 0.04) -> Dict[str, Any]:
        """Execute counterfactual dreaming consolidation across episodic traces."""
        return self.sleep.dream_counterfactuals(self, dreams=dreams, lr=lr)

    def dpo_align(
        self,
        prompt: str,
        chosen_text: str,
        rejected_text: str,
        *,
        chosen_mix: Optional[Sequence[float]] = None,
        rejected_mix: Optional[Sequence[float]] = None,
    ) -> Dict[str, Any]:
        """Direct Preference Optimization step aligning language mouth and encounter-mix head."""
        h = self._stream(prompt)
        left_head = self.moe.experts["left"].head if (self.moe is not None and "left" in self.moe.experts) else None
        return self.dpo_optimizer.step_preference_pair(
            self.transformer,
            prompt,
            chosen_text,
            rejected_text,
            head=left_head,
            hidden=h,
            chosen_mix=chosen_mix,
            rejected_mix=rejected_mix,
        )

    def lookahead_speak(
        self,
        stimulus: str,
        *,
        n: int = 10,
        lookahead_window: int = 4,
        required_tokens: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """Multi-branch lookahead Jacobi speculative decode with neuro-symbolic grammar/budget masking."""
        from skeleton.cortex.speculative import GrammarBudgetLogitProcessor, lookahead_jacobi_decode

        xf = self.transformer
        rms = getattr(self, "neo_rms", None)
        backup = getattr(self, "backup_transformer", None)
        drafts = [m for m in (rms, backup) if m is not None and int(getattr(m, "V", -1)) == int(getattr(xf, "V", -2))]
        ids = list(xf._ids(stimulus or "")) or [int(getattr(xf, "unk", 0))]
        proc = GrammarBudgetLogitProcessor(
            xf.itos,
            required_tokens=required_tokens,
            no_repeat_ngram_size=2,
        )
        return lookahead_jacobi_decode(
            xf,
            drafts or [xf],
            ids,
            n,
            lookahead_window=lookahead_window,
            logit_processor=proc,
        )

    def compile_zero_shot_blueprint(
        self,
        brief: str,
        *,
        console_target: str = "gb_dmg_rom",
        genre: str = "action_platformer",
        tile_count: int = 6,
        seed: int = 19,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """Compile a zero-shot playable game blueprint + ROM tile/palette/OAM/audio bank with memoization."""
        return self.blueprint_compiler.compile(
            self,
            brief,
            console_target=console_target,
            genre=genre,
            tile_count=tile_count,
            seed=seed,
            use_cache=use_cache,
        )

    def decompile_sequential(
        self,
        payload: Any,
        *,
        filename: str = "artifact.gb",
        arch: str = "auto",
        window_size: int = 32,
        adaptive_passes: int = 3,
    ) -> Dict[str, Any]:
        """Decompile a binary ROM, hex dump, or script sequentially into CFG, symbol table, and semantic IR."""
        return self.decompiler.decompile(
            payload,
            filename=filename,
            arch=arch,
            window_size=window_size,
            adaptive_passes=adaptive_passes,
            neo=self,
        )

    def comprehend(self, stimulus: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute deep multi-order comprehension and semantic role-frame + causal DAG extraction."""
        from skeleton.cortex.own import comprehend_and_semanticize
        return comprehend_and_semanticize(self, stimulus, context)

    def innsight_outrospect(self, stimulus: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute deep introspective ('innsight') and external player/hardware ('outrospect') synthesis."""
        from skeleton.cortex.own import innsight_and_outrospect
        return innsight_and_outrospect(self, stimulus, context)

    def hyper_scrutinize(self, target: Any, *, console_target: str = "gb_dmg_rom") -> Dict[str, Any]:
        """Run 12-axis trans-human scrutiny and review across a prompt, blueprint, or game build."""
        from skeleton.cortex.own import hyper_scrutiny_and_review
        return hyper_scrutiny_and_review(self, target, console_target=console_target)

    def run_100_enhancing_todos(self) -> Dict[str, Any]:
        """Execute and verify all 100 cognitive enhancement to-dos across the cortex."""
        from skeleton.cortex.own import execute_100_enhancing_todos
        return execute_100_enhancing_todos(self)

    def run_massive_steps(
        self,
        *,
        total_steps: int = 900_000,
        lr: float = 0.025,
        console_target: str = "gb_dmg_rom",
    ) -> Dict[str, Any]:
        """Execute a massive vectorized hyper-training run (default 900,000 steps) across the cortex."""
        from skeleton.cortex.own import run_massive_hyper_steps
        return run_massive_hyper_steps(
            self,
            total_steps=total_steps,
            lr=lr,
            console_target=console_target,
        )

    def list_ai_tools(self) -> List[Dict[str, Any]]:
        """List all 16 callable tools in the Jeeves Cognitive Tool Suite."""
        return self.tool_suite.list_tools()

    def invoke_ai_tool(self, tool_name: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Invoke a named tool from the Jeeves Cognitive Tool Suite."""
        return self.tool_suite.invoke(tool_name, payload)

    def upload_all_files(self, files: Sequence[Any]) -> Dict[str, Any]:
        """Batch-upload, decompile, comprehend, and scrutinize all provided files into the AI memory."""
        return self.tool_suite.upload_all_files(files)


    def speaking_name(self) -> str:
        if self._mouth_override:
            return str(self._mouth_override)
        return str(self._winner_mouth or "neo")

    def speaking_lm(self):
        return self.mouth(self.speaking_name())

    def set_mouth(self, name: Optional[str] = None) -> str:
        self._mouth_override = None if not name else str(name).lower()
        return self.speaking_name()

    def dodeca(self) -> Dict[str, Any]:
        from skeleton.cortex.dodeca import face_card
        return face_card(self)

    def dispatch(self, stimulus: str) -> Dict[str, Any]:
        """Hivemind job: ledger the stimulus as a swarm act. No network."""
        thought = Thought(
            slot="neo", kind="dispatch",
            text=f"DISPATCH {(stimulus or '')[:160]}",
            confidence=0.8, tags=("dispatch", "hive", "mesh"),
        )
        self.ledger.record(thought, stimulus or "")
        self._bus.emit("cortex.dispatch", {"stim": (stimulus or "")[:160]})
        return {"dispatched": 1, "ledger": self.ledger.to_dict()}

    def elect_mouth(self, *, texts=None) -> Dict[str, Any]:
        from skeleton.cortex.zaibatsu import tournament
        seal = tournament(self, texts=texts)
        winner = str(seal.get("winner") or "neo")
        self._winner_mouth = winner
        self._seal = seal
        return seal

    def speculative_speak(self, stimulus: str, *, n: int = 8, proposals: int = 4) -> Dict[str, Any]:
        """Draft with the RMS mouth and publish only the speaking mouth's greedy ids."""
        from skeleton.cortex.speculative import greedy_speculative
        from skeleton.cortex.transformer import UNK

        verifier = self.transformer
        draft = getattr(self, "neo_rms", None)
        if verifier is None or draft is None:
            raise CortexError("speculative speak requires the speaking mouth and the RMS mouth")
        if int(verifier.V) != int(draft.V) or list(verifier.itos) != list(draft.itos):
            raise CortexError("speculative mouths must share a vocabulary")
        ids = verifier._ids(stimulus or "") or [verifier.unk]
        published, result = greedy_speculative(verifier, draft, ids, n, proposals=proposals)
        return {
            "text": " ".join(
                verifier.itos[token] if 0 <= token < len(verifier.itos) else UNK
                for token in published
            ),
            "token_ids": list(published),
            "proposed": result.proposed,
            "accepted_draft_tokens": result.accepted_count,
            "acceptance_rate": result.acceptance_rate,
            "weights_changed": False,
            "authoritative_mouth": "transformer",
            "draft_mouth": "neo_rms",
        }

    def speak(self, stimulus: str, *, n: int = 12, seed: int = 0, mouth: str = "gelu") -> str:
        xf = self.mouth(mouth)
        if xf is None:
            return ""
        if hasattr(xf, "decode"):
            return str(xf.decode(stimulus or "", n=n, seed=seed))
        return " ".join(xf.generate(stimulus or "", n=n, seed=seed))

    def cooperative_speak(
        self,
        stimulus: str,
        *,
        n: int = 12,
        seed: int = 0,
        min_p: float = 0.0,
    ) -> Dict[str, Any]:
        """Cooperatively decode across speaking and RMS mouths weighted by inverse perplexity."""
        import math
        from skeleton.cortex.curriculum import CORE_PAIRS
        from skeleton.cortex.gossip import cooperative_decode

        xf = self.transformer
        rms = getattr(self, "neo_rms", None)
        if xf is None:
            return {"text": "", "mouths": [], "weights": []}
        if rms is None or int(getattr(xf, "V", -1)) != int(getattr(rms, "V", -2)):
            text = self.speak(stimulus, n=n, seed=seed)
            return {"text": text, "mouths": ["neo"], "weights": [1.0]}
        probe_texts = [a for a, _ in list(CORE_PAIRS)[:4]] or [stimulus or "soulslike ttk"]
        ppl_xf = float(xf.perplexity(probe_texts))
        ppl_rms = float(rms.perplexity(probe_texts))
        w_xf = 1.0 / max(ppl_xf if math.isfinite(ppl_xf) else 1e6, 1e-6)
        w_rms = 1.0 / max(ppl_rms if math.isfinite(ppl_rms) else 1e6, 1e-6)
        total = w_xf + w_rms
        weights = [w_xf / total, w_rms / total]
        text = cooperative_decode(
            (xf, rms),
            stimulus or "",
            n=n,
            seed=seed,
            weights=weights,
            min_p=min_p,
        )
        return {
            "text": text,
            "mouths": ["neo", "neo_rms"],
            "weights": [round(w, 4) for w in weights],
            "ppl": {"neo": round(ppl_xf, 4), "neo_rms": round(ppl_rms, 4)},
        }

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
        MoE mix stitches in when the left expert is fitted and compose
        has no mix numbers of its own.
        """
        xf = self.speaking_lm()
        mouth_name = self.speaking_name()
        fitted = int(getattr(xf, "fitted", 0) or 0) if xf is not None else 0
        if xf is None or fitted <= 0:
            return Thought(
                slot="neo",
                kind="own",
                text=composed.text or "",
                confidence=min(1.0, 0.5 + 0.3 * float(jaccard or 0.0)),
                tags=tuple(dict.fromkeys(list(composed.tags) + ["own", "surpass", mouth_name])),
                numbers=composed.numbers,
            )
        seed = int(fingerprint(stim)[:8], 16) if stim else 0
        gen = ""
        if hasattr(xf, "decode"):
            gen = str(xf.decode(stim or "", n=14, seed=seed) or "")
        tags = tuple(dict.fromkeys(list(composed.tags) + ["lm", "neo", "own", "surpass", mouth_name]))
        numbers = composed.numbers
        moe_mix = self.moe.predict_mix(self._hidden(stim))
        if moe_mix is not None and (not numbers or len(numbers) < 3):
            numbers = tuple(float(x) for x in moe_mix)
            tags = tuple(dict.fromkeys(list(tags) + ["moe", "mix"]))
        # Keep acquired/composed text beside the LM decode (sigil survival).
        body = f"{gen} || {composed.text}" if (gen or composed.text) else (gen or composed.text or "")
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


# --- Observability surface (compose with GameForge neocortex; from cc7957c stub) ---
import time as _obs_time
from dataclasses import field as _obs_field


@dataclass
class CortexSnapshot:
    """Point-in-time capture of system state."""

    timestamp: float
    event_counts: Dict[str, int] = _obs_field(default_factory=dict)
    handle_status: Dict[str, str] = _obs_field(default_factory=dict)
    bus_stats: Dict[str, Any] = _obs_field(default_factory=dict)
    invariant_violations: List[str] = _obs_field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_counts": self.event_counts,
            "handle_status": self.handle_status,
            "bus_stats": self.bus_stats,
            "invariant_violations": self.invariant_violations,
        }


class ControlSurface:
    """Runtime control and intervention surface over the event bus."""

    def __init__(self, cortex: "JeevesCortex", bus: Optional[EventBus] = None) -> None:
        self._cortex = cortex
        self._bus = bus if bus is not None else getattr(cortex, "_bus", None)
        self._interventions: List[Dict[str, Any]] = []

    def pause_topic(self, topic: str) -> None:
        if self._bus:
            self._bus.emit("control.pause", {"topic": topic})
        self._interventions.append({"action": "pause", "topic": topic, "time": _obs_time.time()})

    def resume_topic(self, topic: str) -> None:
        if self._bus:
            self._bus.emit("control.resume", {"topic": topic})
        self._interventions.append({"action": "resume", "topic": topic, "time": _obs_time.time()})

    def inject_event(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._bus:
            # Inherit active observability correlation when callers omit it.
            from skeleton.observability.correlation import get_correlation_id

            cid = get_correlation_id()
            self._bus.publish(
                DomainEvent(topic=topic, payload=payload, correlation_id=cid)
            )
        self._interventions.append({"action": "inject", "topic": topic, "time": _obs_time.time()})

    def stats(self) -> Dict[str, Any]:
        return {"interventions": len(self._interventions)}
