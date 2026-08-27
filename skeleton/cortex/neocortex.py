"""Jeeves neocortex — hivemind that organizes the tracts and is itself an LM.

The four slots (PFC / midbrain / left / right) are agents. Jeeves:
  1. lets midbrain route
  2. fires the hemispheres the route named
  3. lets PFC plan / inhibit
  4. aggregates confidence through HiveMind
  5. amalgamates a teacher thought
  6. composes an own-system thought from Jaccard-nearest acquired tracts
  7. shadows own vs teacher; auto-surpass when own wins
  8. acquire(slot) copies a model's abilities into own-system
  9. surpass(slot) answers from own-system — the neo transformer SPEAKS
     (CPU decode). Compose keeps the numbers. Veto still wins.

Backends are interchangeable: bind(slot, port) hot-swaps the model in
that tract. The neo TinyTransformer is Jeeves' own language model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from skeleton.cortex.curriculum import train as run_curriculum
from skeleton.cortex.distill import Ability, AbilityLedger, ability_from
from skeleton.cortex.hemispheres import LeftHemisphere, RightHemisphere
from skeleton.cortex.midbrain import Midbrain
from skeleton.cortex.own import OwnSystem, Tract, shadow_eval
from skeleton.cortex.pfc import PrefrontalCortex
from skeleton.cortex.port import SLOTS, EchoBackend, ModelPort, Thought, fingerprint
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
        from skeleton.cortex.lm import gameforge_vocab
        from skeleton.cortex.transformer import TinyTransformer
        self.transformer = TinyTransformer(
            vocab=gameforge_vocab(), dim=8, ctx=6, seed=19,
        )

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
            own_size=self.own.size,
        )

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
        self._bus.emit("cortex.acquired", {"slot": slot, "copied": copied})
        return {"slot": slot, "copied": copied, "acquired": dict(self.acquired), "own": self.own.size}

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

    def export_tract(self, slot: str) -> Dict[str, Any]:
        slot = (slot or "").lower()
        backend = self.backends().get(slot, "own")
        scale = getattr(self.slots.get(slot), "scale", "neo")
        tract = self.own.export_tract(slot, backend=backend, scale=str(scale))
        payload = tract.to_dict()
        port = self.slots.get(slot)
        if port is not None and hasattr(port, "snapshot"):
            payload["weights"] = port.snapshot()
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
        self._bus.emit("cortex.imported", {"slot": tract.slot, "copied": n})
        return {"slot": tract.slot, "copied": n, "own": self.own.size,
                "capabilities": list(tract.capabilities)[:16],
                "bound": bound}

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
            from skeleton.cortex.transformer import TinyTransformer
            self.transformer = TinyTransformer.from_snapshot(blob["transformer"])
        return {"loaded": n, "own": self.own.size, "surpass": sorted(self._surpass)}

    def status(self) -> Dict[str, Any]:
        xf = self.transformer
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
                "device": "cpu",
            },
        }

    def _lm_amalgam(self, stim: str, composed: Thought, jaccard: float) -> Thought:
        """Neo transformer speaks. Compose keeps numbers and acquired text.

        Unfitted net falls back to compose (tape). Fitted net is the LM.
        CPU decode only.
        """
        xf = self.transformer
        if xf is None or int(getattr(xf, "fitted", 0) or 0) <= 0:
            return composed
        seed = int(fingerprint(stim)[:8], 16) if stim else 0
        gen = xf.decode(stim, n=14, seed=seed)
        tags = tuple(dict.fromkeys(list(composed.tags) + ["lm", "neo", "own"]))
        return Thought(
            slot="neo",
            kind="own-lm",
            text=f"{gen} || {composed.text}",
            confidence=min(1.0, 0.58 + 0.35 * float(jaccard or 0.0)),
            tags=tags,
            numbers=composed.numbers,
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
