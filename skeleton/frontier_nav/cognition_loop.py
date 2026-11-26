"""Closed-loop perceive -> plan -> act -> verify navigation cognition (GF-L).

Covers GF-P2-01 (closed-loop controller with authoritative state checks) and
GF-P2-06 (prediction latency/confidence thresholds, cancellation, rollback)
for navigation.

* **perceive**: the authoritative :class:`FrameGPSHub` NavUpdate (hash-chained).
* **plan**: follow the grounded plan; on a monitor trigger, repair via
  :class:`RouteRepairer` (approved, signed hops only).
* **act**: emit a step command through an injected actuator port. Steps are
  speculative until verified; low-confidence or stale predictions are not
  issued at all.
* **verify**: on a later frame, the authoritative fix must be closer to the
  commanded waypoint. Otherwise the step is rolled back (actuator cancel) and
  the entity is held at its last verified waypoint.

The GF-A runtime binding (Internal Systems, #4595) is consumed through
:class:`RuntimeBindingAdapter`, which reads public attributes only; the loop
refuses to act without a binding for the lane's era whose claim is still
pending native render QA or better. No GF-A module is imported or edited.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from skeleton.frontier_nav.gps import GPSRejected, NavUpdate, PositionFix
from skeleton.frontier_nav.route_grounding import GroundedPlan
from skeleton.frontier_nav.route_repair import (
    RepairFailed,
    RouteMonitor,
)

ALLOWED_CLAIMS = frozenset({"bound_pending_native_render_qa", "native_render_qa_passed"})


class CognitionHalt(RuntimeError):
    """Loop refuses to act (no binding, era mismatch, broken proof chain)."""


@dataclass(frozen=True)
class BindingView:
    binding_id: str
    era: str
    fps: int
    claim: str


class RuntimeBindingAdapter:
    """Adapts a GF-A ``RuntimeBinding`` (or any duck-typed equivalent)."""

    def __init__(self, status_fn: Callable[[object], dict] | None = None) -> None:
        self._status_fn = status_fn

    def view(self, binding: object) -> BindingView:
        binding_id = getattr(binding, "binding_id", None)
        era = getattr(binding, "era", None)
        fps = getattr(binding, "fps", None)
        if not isinstance(binding_id, str) or len(binding_id) != 64:
            raise CognitionHalt("runtime binding id missing")
        if not isinstance(era, str) or not era:
            raise CognitionHalt("runtime binding era missing")
        if type(fps) is not int or fps <= 0:
            raise CognitionHalt("runtime binding fps invalid")
        claim = "bound_pending_native_render_qa"
        if self._status_fn is not None:
            claim = str(self._status_fn(binding).get("claim", ""))
        if claim not in ALLOWED_CLAIMS:
            raise CognitionHalt(f"runtime binding claim {claim!r} not actionable")
        return BindingView(binding_id, era, fps, claim)


class Actuator(Protocol):
    def step(self, entity_id: str, target: str, frame: int) -> str: ...
    def cancel(self, command_id: str) -> None: ...


@dataclass(frozen=True)
class Prediction:
    entity_id: str
    target: str
    confidence: float
    latency_ms: float


@dataclass(frozen=True)
class SpeculationPolicy:
    min_confidence: float = 0.6
    max_latency_ms: float = 50.0
    verify_within_frames: int = 3

    def admits(self, p: Prediction) -> bool:
        return (
            math.isfinite(p.confidence)
            and math.isfinite(p.latency_ms)
            and p.confidence >= self.min_confidence
            and 0 <= p.latency_ms <= self.max_latency_ms
        )


@dataclass
class PendingStep:
    command_id: str
    entity_id: str
    target: str
    issued_frame: int
    start_distance: float


@dataclass(frozen=True)
class TickEvent:
    frame: int
    entity_id: str
    phase: str  # perceive|plan|act|verify|rollback|abstain|hold
    detail: str


Predictor = Callable[[PositionFix, GroundedPlan, int], Prediction]


@dataclass
class CognitionLoop:
    monitor: RouteMonitor
    actuator: Actuator
    predictor: Predictor
    binding: BindingView
    console: str
    policy: SpeculationPolicy = field(default_factory=SpeculationPolicy)
    pending: dict[str, PendingStep] = field(default_factory=dict)
    held: set[str] = field(default_factory=set)
    log: list[TickEvent] = field(default_factory=list)
    _last_proof: str | None = None

    def _emit(self, frame: int, entity: str, phase: str, detail: str) -> None:
        self.log.append(TickEvent(frame, entity, phase, detail))

    def _coord(self, wp: str) -> tuple[float, float, float]:
        return self.monitor.repairer.coords[wp]

    def tick(self, update: NavUpdate) -> list[TickEvent]:
        start = len(self.log)
        if update.console != self.console or update.era != self.binding.era:
            raise CognitionHalt(
                f"lane {update.console}/{update.era} not bound "
                f"(binding era {self.binding.era})"
            )
        if update.proof_hash == self._last_proof:
            raise CognitionHalt("replayed frame proof")
        self._last_proof = update.proof_hash
        fixes = {f.entity_id: f for f in update.fixes}
        for eid, f in fixes.items():
            try:
                f.validate()
            except GPSRejected as exc:
                raise CognitionHalt(str(exc)) from exc
            if eid in self.monitor.tracks:
                self._emit(update.frame, eid, "perceive", f"({f.x:.2f},{f.y:.2f},{f.z:.2f})")
        self._verify(update.frame, fixes)
        for trig in self.monitor(update):
            self._plan_repair(trig, fixes[trig.entity_id])
        for eid, fix in fixes.items():
            if eid in self.monitor.tracks and eid not in self.pending and eid not in self.held:
                self._act(update.frame, fix)
        return self.log[start:]

    def _verify(self, frame: int, fixes: dict[str, PositionFix]) -> None:
        for eid, step in list(self.pending.items()):
            fix = fixes.get(eid)
            if fix is None:
                continue
            d = math.dist((fix.x, fix.y, fix.z), self._coord(step.target))
            if d < step.start_distance - 1e-9:
                del self.pending[eid]
                self._emit(frame, eid, "verify", f"progress to {step.target} {d:.2f}")
            elif frame - step.issued_frame >= self.policy.verify_within_frames:
                self._rollback(frame, step, f"no progress to {step.target} ({d:.2f})")

    def _rollback(self, frame: int, step: PendingStep, why: str) -> None:
        self.actuator.cancel(step.command_id)
        self.pending.pop(step.entity_id, None)
        self.held.add(step.entity_id)
        self._emit(frame, step.entity_id, "rollback", why)

    def _plan_repair(self, trig, fix: PositionFix) -> None:
        eid = trig.entity_id
        step = self.pending.get(eid)
        if step is not None:
            self._rollback(trig.frame, step, f"superseded by {trig.reason} repair")
        track = self.monitor.tracks[eid]
        try:
            repaired = self.monitor.repairer.repair(trig, track.plan, fix)
        except RepairFailed as exc:
            self.held.add(eid)
            self._emit(trig.frame, eid, "hold", str(exc))
            return
        self.monitor.follow(eid, repaired.plan)
        self.held.discard(eid)
        self._emit(trig.frame, eid, "plan",
                   f"{trig.reason}: {'->'.join(repaired.plan.waypoints)} "
                   f"cost={repaired.cost:.2f} routes={','.join(repaired.plan.route_ids)}")

    def _act(self, frame: int, fix: PositionFix) -> None:
        eid = fix.entity_id
        remaining = self.monitor.remaining(eid)
        if len(remaining) < 2:
            return
        pred = self.predictor(fix, self.monitor.tracks[eid].plan, frame)
        if pred.entity_id != eid or pred.target != remaining[1] or not self.policy.admits(pred):
            self._emit(frame, eid, "abstain",
                       f"prediction {pred.target} conf={pred.confidence:.2f} "
                       f"lat={pred.latency_ms:.1f}ms not admitted")
            return
        dist = math.dist((fix.x, fix.y, fix.z), self._coord(pred.target))
        cmd = self.actuator.step(eid, pred.target, frame)
        self.pending[eid] = PendingStep(cmd, eid, pred.target, frame, dist)
        self._emit(frame, eid, "act", f"{cmd} -> {pred.target} [{self.binding.binding_id[:12]}]")

    def resume(self, entity_id: str) -> None:
        """Operator/authority releases a held entity after a rollback or failed repair."""
        self.held.discard(entity_id)
