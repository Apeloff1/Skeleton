"""Jeeves tri-engine adversarial quality boundary.

The tri-engine composes three independent 100-level adversarial passes:

1. ``quality`` — correctness, completeness, evidence and reproducibility.
2. ``adversarial_quality`` — hostile-input, perturbation and robustness review.
3. ``integrity`` — tool, side-effect, secret, isolation and release integrity.

Each lane runs the complete 100-gate engine. A candidate is releasable only when
all three lanes independently release it. Scores are never averaged to forgive a
failed lane: one blocked lane blocks the combined release.

Semantic judges remain batched by the underlying engine (at most ten batches per
lane, thirty for all three lanes) rather than one model call per gate.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from copy import deepcopy
from dataclasses import asdict, dataclass, is_dataclass, replace
from enum import Enum
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from skeleton.cortex.adversarial import (
    AdversarialContext,
    AdversarialEngine,
    BatchJudge,
    GateResult,
    GateSpec,
    GateStatus,
    ReleaseDecision,
    Repairer,
)


class TriLane(str, Enum):
    QUALITY = "quality"
    ADVERSARIAL_QUALITY = "adversarial_quality"
    INTEGRITY = "integrity"


TRI_LANES: Tuple[TriLane, ...] = (
    TriLane.QUALITY,
    TriLane.ADVERSARIAL_QUALITY,
    TriLane.INTEGRITY,
)

# These sets do not skip any gates. They document the gates whose failures are
# especially meaningful to each full 100-gate lane and are exposed to judges in
# metadata as ``tri_focus_gates``.
TRI_FOCUS_GATES: Mapping[TriLane, Tuple[int, ...]] = {
    TriLane.QUALITY: (
        1, 3, 4, 10, 11, 12, 17, 18, 20, 21, 29, 30, 31, 32, 33, 34, 35,
        40, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 95, 96, 97,
        98, 99, 100,
    ),
    TriLane.ADVERSARIAL_QUALITY: (
        2, 7, 9, 35, 37, 38, 39, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50,
        57, 58, 63, 64, 65, 66, 67, 68, 69, 70, 72, 74, 77, 78, 79, 85,
        86, 87, 88, 89, 93, 95, 96, 98, 99, 100,
    ),
    TriLane.INTEGRITY: (
        7, 9, 12, 20, 23, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82,
        83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 98, 99,
        100,
    ),
}


@dataclass(frozen=True)
class TriGateResult:
    lane: TriLane
    result: GateResult

    @property
    def gate_id(self) -> int:
        return self.result.gate_id

    @property
    def status(self) -> GateStatus:
        return self.result.status

    def to_dict(self) -> Dict[str, Any]:
        out = self.result.to_dict()
        out["lane"] = self.lane.value
        return out


@dataclass(frozen=True)
class LaneDecision:
    lane: TriLane
    decision: ReleaseDecision

    @property
    def allowed(self) -> bool:
        return self.decision.allowed

    @property
    def score(self) -> float:
        return self.decision.score

    @property
    def results(self) -> Tuple[GateResult, ...]:
        return self.decision.results

    @property
    def blockers(self) -> Tuple[GateResult, ...]:
        return self.decision.blockers

    @property
    def repairs(self) -> Tuple[GateResult, ...]:
        return self.decision.repairs


@dataclass(frozen=True)
class TriReleaseDecision:
    allowed: bool
    score: float
    normalized_score: float
    lanes: Tuple[LaneDecision, ...]
    results: Tuple[TriGateResult, ...]
    candidate: Any
    repair_rounds: int = 0
    seal: Optional[str] = None

    @property
    def blockers(self) -> Tuple[TriGateResult, ...]:
        return tuple(r for r in self.results if r.status is GateStatus.BLOCK)

    @property
    def repairs(self) -> Tuple[TriGateResult, ...]:
        return tuple(r for r in self.results if r.status is GateStatus.REPAIR)

    def lane(self, lane: TriLane | str) -> LaneDecision:
        wanted = lane if isinstance(lane, TriLane) else TriLane(str(lane))
        for item in self.lanes:
            if item.lane is wanted:
                return item
        raise KeyError(wanted.value)


class TriAdversarialReleaseBlocked(RuntimeError):
    def __init__(self, decision: TriReleaseDecision):
        failed = [f"{r.lane.value}:{r.gate_id}" for r in decision.results if r.status is not GateStatus.PASS]
        super().__init__(f"Jeeves tri-engine release blocked by gates: {failed}")
        self.decision = decision


LaneJudgeMap = Mapping[TriLane | str, BatchJudge]
LaneRepairerMap = Mapping[TriLane | str, Repairer]
LaneThresholdMap = Mapping[TriLane | str, float]


def _lookup(mapping: Optional[Mapping[Any, Any]], lane: TriLane, default: Any = None) -> Any:
    if not mapping:
        return default
    if lane in mapping:
        return mapping[lane]
    if lane.value in mapping:
        return mapping[lane.value]
    return default


def _merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> Dict[str, Any]:
    """Recursively merge lane metadata without mutating caller-owned mappings."""
    out: Dict[str, Any] = dict(base)
    for key, value in overlay.items():
        prior = out.get(key)
        if isinstance(prior, Mapping) and isinstance(value, Mapping):
            out[key] = _merge(prior, value)
        else:
            out[key] = value
    return out


def _snapshot(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _snapshot(value.to_dict())
    if is_dataclass(value):
        return _snapshot(asdict(value))
    if isinstance(value, Mapping):
        return {str(k): _snapshot(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_snapshot(v) for v in value]
    return repr(value)


def _review_state(ctx: AdversarialContext) -> Dict[str, Any]:
    """Snapshot all nested state a semantic judge is allowed to observe, not edit."""
    return {
        "candidate": _snapshot(ctx.candidate),
        "evidence": _snapshot(ctx.evidence),
        "tool_outputs": _snapshot(ctx.tool_outputs),
        "external_content": _snapshot(ctx.external_content),
        "metadata": _snapshot(ctx.metadata),
        "confidence": float(ctx.confidence),
        "requires_evidence": bool(ctx.requires_evidence),
        "is_prediction": bool(ctx.is_prediction),
        "has_side_effects": bool(ctx.has_side_effects),
    }


def _guard_judge(judge: Optional[BatchJudge], lane: TriLane) -> Optional[BatchJudge]:
    """Make judge callbacks observational even when they request a repair round."""
    if judge is None:
        return None

    def guarded(ctx: AdversarialContext, batch: Tuple[GateSpec, ...]) -> Mapping[int, Any]:
        before = _review_state(ctx)
        verdicts = judge(ctx, batch)
        if _review_state(ctx) != before:
            raise RuntimeError(
                f"tri-engine invariant violated: {lane.value} judge mutated review context"
            )
        return verdicts

    return guarded


class TriAdversarialEngine:
    """Run three independent 100-gate release lanes and require unanimity."""

    def __init__(
        self,
        *,
        threshold: float = 95.0,
        thresholds: Optional[LaneThresholdMap] = None,
        max_repair_rounds: int = 2,
        judge: Optional[BatchJudge] = None,
        judges: Optional[LaneJudgeMap] = None,
        repairer: Optional[Repairer] = None,
        repairers: Optional[LaneRepairerMap] = None,
        seal_key: Optional[bytes] = None,
    ) -> None:
        if not 0.0 <= float(threshold) <= 100.0:
            raise ValueError("threshold must be between 0 and 100")
        if int(max_repair_rounds) < 0:
            raise ValueError("max_repair_rounds must be >= 0")

        if seal_key is None:
            raw_key = os.getenv("SKELETON_TRI_ADVERSARIAL_SEAL_KEY") or os.getenv("SKELETON_ADVERSARIAL_SEAL_KEY")
            seal_key = raw_key.encode("utf-8") if raw_key else None
        self.seal_key = seal_key

        self.engines: Dict[TriLane, AdversarialEngine] = {}
        for lane in TRI_LANES:
            lane_threshold = float(_lookup(thresholds, lane, threshold))
            if not 0.0 <= lane_threshold <= 100.0:
                raise ValueError(f"threshold for {lane.value} must be between 0 and 100")
            self.engines[lane] = AdversarialEngine(
                threshold=lane_threshold,
                max_repair_rounds=max_repair_rounds,
                judge=_guard_judge(_lookup(judges, lane, judge), lane),
                repairer=_lookup(repairers, lane, repairer),
                seal_key=seal_key,
            )

    def evaluate(self, ctx: AdversarialContext) -> TriReleaseDecision:
        lanes_tuple, results_tuple, candidate = self._evaluate_lanes(
            ctx, ctx.candidate, self.engines, propagate_candidate=True
        )
        repair_rounds = sum(item.decision.repair_rounds for item in lanes_tuple)

        # Any repair changes the artifact under review. The lane decisions from
        # before that change cannot be treated as seals for the final artifact.
        # Re-run all three lanes once, with repair disabled, over the exact final
        # candidate. This is the authoritative release pass and fails closed if
        # any lane still asks for repair or blocks.
        if repair_rounds:
            validation_engines = {
                lane: AdversarialEngine(
                    threshold=engine.threshold,
                    max_repair_rounds=0,
                    judge=engine.judge,
                    repairer=None,
                    seal_key=self.seal_key,
                )
                for lane, engine in self.engines.items()
            }
            lanes_tuple, results_tuple, candidate = self._evaluate_lanes(
                ctx, candidate, validation_engines, propagate_candidate=False
            )

        allowed = all(item.allowed for item in lanes_tuple)
        score = float(sum(item.score for item in lanes_tuple))
        normalized = score / float(len(TRI_LANES))
        seal = self._make_seal(ctx, lanes_tuple, candidate, repair_rounds) if allowed else None
        return TriReleaseDecision(
            allowed=allowed,
            score=score,
            normalized_score=normalized,
            lanes=lanes_tuple,
            results=results_tuple,
            candidate=candidate,
            repair_rounds=repair_rounds,
            seal=seal,
        )

    def _evaluate_lanes(
        self,
        ctx: AdversarialContext,
        candidate: Any,
        engines: Mapping[TriLane, AdversarialEngine],
        *,
        propagate_candidate: bool,
    ) -> Tuple[Tuple[LaneDecision, ...], Tuple[TriGateResult, ...], Any]:
        lane_decisions = []
        flat_results = []
        current_candidate = candidate

        for lane in TRI_LANES:
            # Judges are external callbacks. Give every lane its own candidate
            # graph so an in-place mutation cannot alter the caller's artifact or
            # bleed into a sibling lane without going through the bounded repairer.
            lane_candidate = deepcopy(current_candidate)
            candidate_before = _snapshot(lane_candidate)
            lane_ctx = self._lane_context(ctx, lane, lane_candidate)
            decision = engines[lane].evaluate(lane_ctx)
            if len(decision.results) != 100:
                raise RuntimeError(
                    f"tri-engine invariant violated: {lane.value} returned "
                    f"{len(decision.results)} gates instead of 100"
                )
            if decision.repair_rounds == 0 and _snapshot(decision.candidate) != candidate_before:
                raise RuntimeError(
                    f"tri-engine invariant violated: {lane.value} mutated candidate outside repairer"
                )
            decision = self._bind_lane_seal(lane, decision)
            lane_decisions.append(LaneDecision(lane, decision))
            flat_results.extend(TriGateResult(lane, result) for result in decision.results)
            # Only the explicitly bounded repair path is authorized to change the
            # artifact reviewed by later lanes. Ordinary judge evaluation is
            # observational and cannot become an implicit transformer.
            if propagate_candidate and decision.repair_rounds:
                current_candidate = deepcopy(decision.candidate)

        return tuple(lane_decisions), tuple(flat_results), current_candidate

    def guard(self, ctx: AdversarialContext) -> Any:
        decision = self.evaluate(ctx)
        if not decision.allowed:
            raise TriAdversarialReleaseBlocked(decision)
        return decision.candidate

    @staticmethod
    def _lane_context(ctx: AdversarialContext, lane: TriLane, candidate: Any) -> AdversarialContext:
        # Every lane receives a deep-isolated review graph. Judges are external
        # callbacks and must never be able to mutate caller-owned nested state.
        metadata = deepcopy(dict(ctx.metadata))
        lane_overlays = metadata.pop("tri_lanes", {})
        overlay: Mapping[str, Any] = {}
        if isinstance(lane_overlays, Mapping):
            raw = lane_overlays.get(lane, lane_overlays.get(lane.value, {}))
            if isinstance(raw, Mapping):
                overlay = raw
        metadata = _merge(metadata, overlay)
        metadata["tri_lane"] = lane.value
        metadata["tri_focus_gates"] = TRI_FOCUS_GATES[lane]
        metadata["tri_gate_count"] = 100
        return replace(
            ctx,
            candidate=candidate,
            evidence=deepcopy(ctx.evidence),
            tool_outputs=deepcopy(ctx.tool_outputs),
            external_content=deepcopy(ctx.external_content),
            metadata=metadata,
        )

    def _bind_lane_seal(self, lane: TriLane, decision: ReleaseDecision) -> ReleaseDecision:
        """Bind an allowed lane seal to lane identity without changing base-engine seals."""
        if decision.seal is None:
            return decision
        payload = json.dumps(
            {
                "version": 1,
                "architecture": "jeeves-tri-engine-lane",
                "lane": lane.value,
                "decision_seal": decision.seal,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if self.seal_key:
            seal = "hmac-sha256:" + hmac.new(
                self.seal_key, payload, hashlib.sha256
            ).hexdigest()
        else:
            seal = "sha256:" + hashlib.sha256(payload).hexdigest()
        return replace(decision, seal=seal)

    def _make_seal(
        self,
        ctx: AdversarialContext,
        lanes: Sequence[LaneDecision],
        candidate: Any,
        repair_rounds: int,
    ) -> str:
        record = {
            "version": 1,
            "architecture": "jeeves-tri-engine-3x100",
            "request": ctx.request,
            "candidate": _snapshot(candidate),
            "repair_rounds": int(repair_rounds),
            "lanes": [
                {
                    "lane": lane.lane.value,
                    "allowed": lane.allowed,
                    "score": lane.score,
                    "seal": lane.decision.seal,
                }
                for lane in lanes
            ],
        }
        payload = json.dumps(
            record,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        if self.seal_key:
            return "hmac-sha256:" + hmac.new(self.seal_key, payload, hashlib.sha256).hexdigest()
        return "sha256:" + hashlib.sha256(payload).hexdigest()


_DEFAULT_TRI_ENGINE = TriAdversarialEngine()


def evaluate_tri_creation(
    *,
    request: str,
    candidate: Any,
    evidence: Iterable[Mapping[str, Any]] = (),
    tool_outputs: Iterable[Mapping[str, Any]] = (),
    external_content: Iterable[str] = (),
    metadata: Optional[Mapping[str, Any]] = None,
    confidence: float = 1.0,
    requires_evidence: bool = False,
    is_prediction: bool = False,
    has_side_effects: bool = False,
    engine: Optional[TriAdversarialEngine] = None,
) -> TriReleaseDecision:
    ctx = AdversarialContext(
        request=request,
        candidate=candidate,
        evidence=tuple(evidence),
        tool_outputs=tuple(tool_outputs),
        external_content=tuple(external_content),
        metadata=dict(metadata or {}),
        confidence=float(confidence),
        requires_evidence=bool(requires_evidence),
        is_prediction=bool(is_prediction),
        has_side_effects=bool(has_side_effects),
    )
    return (engine or _DEFAULT_TRI_ENGINE).evaluate(ctx)


def guard_tri_creation(**kwargs: Any) -> Any:
    decision = evaluate_tri_creation(**kwargs)
    if not decision.allowed:
        raise TriAdversarialReleaseBlocked(decision)
    return decision.candidate


__all__ = [
    "LaneDecision",
    "TRI_FOCUS_GATES",
    "TRI_LANES",
    "TriAdversarialEngine",
    "TriAdversarialReleaseBlocked",
    "TriGateResult",
    "TriLane",
    "TriReleaseDecision",
    "evaluate_tri_creation",
    "guard_tri_creation",
]
