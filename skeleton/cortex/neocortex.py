"""Jeeves neocortex — hivemind that organizes the tracts and trains itself.

The four slots (PFC / midbrain / left / right) are agents. Jeeves:
  1. lets midbrain route
  2. fires the hemispheres the route named
  3. lets PFC plan / inhibit
  4. aggregates confidence through HiveMind
  5. amalgamates a single thought
  6. records every thought as training
  7. acquire(slot) copies that model's abilities into own-system
  8. surpass(slot) answers from own-system instead of the teacher

Backends are interchangeable: bind(slot, port) hot-swaps the model in
that tract. Jeeves keeps the abilities it already acquired.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from skeleton.cortex.distill import Ability, AbilityLedger, ability_from
from skeleton.cortex.hemispheres import LeftHemisphere, RightHemisphere
from skeleton.cortex.midbrain import Midbrain
from skeleton.cortex.pfc import PrefrontalCortex
from skeleton.cortex.port import SLOTS, EchoBackend, ModelPort, Thought, fingerprint
from skeleton.kernel.errors import CortexError
from skeleton.kernel.events import EventBus
from skeleton.swarm.hive import Estimate, HiveMind


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
        self.own: Dict[str, Ability] = {}
        self.acquired: Dict[str, int] = {s: 0 for s in SLOTS}
        self._surpass: Set[str] = set()
        self.shadow: Dict[str, Dict[str, int]] = {s: {"wins": 0, "trials": 0} for s in SLOTS}
        self.hive = HiveMind(bus=self._bus)

    def backends(self) -> Dict[str, str]:
        return {s: getattr(p, "name", type(p).__name__) for s, p in self.slots.items()}

    def bind(self, slot: str, backend: ModelPort) -> Dict[str, str]:
        slot = (slot or "").lower()
        if slot not in SLOTS:
            raise CortexError("unknown slot", context={"slot": slot, "known": list(SLOTS)})
        if getattr(backend, "slot", slot) not in {slot, "neo"}:
            # allow Echo/Callable constructed for this slot
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

        used_own = False
        if self._surpass and fp in self.own:
            amalgam = self.own[fp].as_thought()
            used_own = True
            for s in self._surpass:
                self.shadow[s]["trials"] += 1
                self.shadow[s]["wins"] += 1
        else:
            amalgam = self._amalgam(pfc, left, right, route, hive.value)
            self.own[fp] = ability_from(amalgam, stim)
            self.ledger.record(amalgam, stim)

        self._bus.emit("cortex.thought", {
            "fp": fp, "used_own": used_own, "hive": hive.value,
            "backends": self.backends(),
        })
        return CortexTrace(
            stimulus=stim, fingerprint=fp, route=route, pfc=pfc,
            left=left, right=right, amalgam=amalgam,
            hive_value=hive.value, used_own=used_own,
            acquired=dict(self.acquired), backends=self.backends(),
        )

    def acquire(self, slot: str) -> Dict[str, Any]:
        slot = (slot or "").lower()
        if slot not in SLOTS:
            raise CortexError("unknown slot", context={"slot": slot})
        copied = 0
        for ab in self.ledger.of_slot(slot):
            # own-system now holds this tract's ability under the same fingerprint
            self.own[ab.stimulus_fp] = Ability(
                slot="neo", stimulus_fp=ab.stimulus_fp, signature=ab.signature,
                kind=ab.kind, text=ab.text, tags=ab.tags + ("acquired", slot),
                numbers=ab.numbers, confidence=min(1.0, ab.confidence + 0.05),
                seen=ab.seen,
            )
            copied += 1
        self.acquired[slot] = self.acquired.get(slot, 0) + copied
        self._bus.emit("cortex.acquired", {"slot": slot, "copied": copied})
        return {"slot": slot, "copied": copied, "acquired": dict(self.acquired), "own": len(self.own)}

    def surpass(self, slot: str) -> Dict[str, Any]:
        slot = (slot or "").lower()
        if slot not in SLOTS:
            raise CortexError("unknown slot", context={"slot": slot})
        self._surpass.add(slot)
        self._bus.emit("cortex.surpass", {"slot": slot, "own": len(self.own)})
        return {"slot": slot, "armed": sorted(self._surpass), "own": len(self.own), "shadow": dict(self.shadow)}

    def status(self) -> Dict[str, Any]:
        return {
            "backends": self.backends(),
            "ledger": self.ledger.to_dict(),
            "own": len(self.own),
            "acquired": dict(self.acquired),
            "surpass": sorted(self._surpass),
            "shadow": dict(self.shadow),
        }

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
