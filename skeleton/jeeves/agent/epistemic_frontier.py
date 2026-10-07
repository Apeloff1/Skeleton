"""Epistemic frontier discovery for Jeeves.

This module gives Jeeves an explicit host-side representation of what remains
unknown.  It does not ask a model to "feel uncertain"; it computes knowledge
debt from typed obligations and turns the highest-value gaps into falsifiable,
bounded probes.

The core design principle is *silence is not confidence*: a high-confidence
answer with weak evidence coverage is treated as a blind spot, not as resolved
knowledge.  Forecasts can also be precommitted before outcomes are observed so
calibration reflects prediction quality rather than hindsight.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from .types import (
    AgentContractError,
    RiskTier,
    bounded_text,
    finite_number,
    json_safe,
    positive_int,
    probability,
    require_id,
    stable_fingerprint,
    stable_id,
)


_EPS = 1e-12


class GapKind(str, Enum):
    COVERAGE = "coverage"
    CONTRADICTION = "contradiction"
    DISAGREEMENT = "disagreement"
    ASSUMPTION = "assumption"
    STALENESS = "staleness"
    BLIND_SPOT = "blind_spot"


class ProbeKind(str, Enum):
    RETRIEVAL = "retrieval"
    ADVERSARIAL_CHECK = "adversarial_check"
    DISCRIMINATING_TEST = "discriminating_test"
    FALSIFICATION = "falsification"
    REFRESH = "refresh"
    RED_TEAM_SEARCH = "red_team_search"


class GapStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    DEFERRED = "deferred"


_RISK_PENALTY = {
    RiskTier.READ_ONLY: 0.00,
    RiskTier.REVERSIBLE: 0.08,
    RiskTier.MUTATING: 0.30,
    RiskTier.EXTERNAL: 0.55,
    RiskTier.HIGH_IMPACT: 1.00,
}


def _bounded_nonnegative(name: str, value: Any, *, maximum: float = 1_000_000.0) -> float:
    result = finite_number(name, value)
    if result < 0 or result > maximum:
        raise AgentContractError(f"{name} must be in [0, {maximum}]")
    return result


def _entropy_binary(p: float) -> float:
    p = min(1.0 - _EPS, max(_EPS, p))
    return -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))


@dataclass(frozen=True, slots=True)
class EpistemicFrontierPolicy:
    """Controls when knowledge debt becomes an explicit frontier gap."""

    minimum_signal: float = 0.18
    blind_spot_minimum_impact: float = 0.55
    blind_spot_maximum_coverage: float = 0.35
    blind_spot_minimum_confidence: float = 0.70
    maximum_probes: int = 16
    information_gain_weight: float = 1.00
    decision_value_weight: float = 1.25
    cost_weight: float = 0.20
    risk_weight: float = 0.65

    def __post_init__(self) -> None:
        for name in (
            "minimum_signal",
            "blind_spot_minimum_impact",
            "blind_spot_maximum_coverage",
            "blind_spot_minimum_confidence",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        object.__setattr__(
            self,
            "maximum_probes",
            positive_int("maximum_probes", self.maximum_probes, maximum=10_000),
        )
        for name in (
            "information_gain_weight",
            "decision_value_weight",
            "cost_weight",
            "risk_weight",
        ):
            object.__setattr__(
                self,
                name,
                _bounded_nonnegative(name, getattr(self, name), maximum=100.0),
            )


@dataclass(frozen=True, slots=True)
class KnowledgeObligation:
    """A decision-relevant fact or question Jeeves is responsible for knowing."""

    obligation_id: str
    question: str
    decision_impact: float
    confidence: float
    evidence_coverage: float
    freshness: float = 1.0
    contradiction_strength: float = 0.0
    model_disagreement: float = 0.0
    assumption_load: float = 0.0
    novelty: float = 0.0
    evidence_refs: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "obligation_id", require_id("obligation_id", self.obligation_id))
        object.__setattr__(
            self,
            "question",
            bounded_text("question", self.question, maximum=8192),
        )
        for name in (
            "decision_impact",
            "confidence",
            "evidence_coverage",
            "freshness",
            "contradiction_strength",
            "model_disagreement",
            "assumption_load",
            "novelty",
        ):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        refs = tuple(require_id("evidence_ref", item) for item in self.evidence_refs)
        object.__setattr__(self, "evidence_refs", tuple(sorted(set(refs))))
        assumptions = tuple(
            bounded_text("assumption", item, maximum=2048)
            for item in self.assumptions
        )
        object.__setattr__(self, "assumptions", assumptions)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def uncertainty(self) -> float:
        return 1.0 - self.confidence

    @property
    def coverage_deficit(self) -> float:
        return 1.0 - self.evidence_coverage

    @property
    def staleness(self) -> float:
        return 1.0 - self.freshness

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(self.as_json())

    def as_json(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "question": self.question,
            "decision_impact": self.decision_impact,
            "confidence": self.confidence,
            "evidence_coverage": self.evidence_coverage,
            "freshness": self.freshness,
            "contradiction_strength": self.contradiction_strength,
            "model_disagreement": self.model_disagreement,
            "assumption_load": self.assumption_load,
            "novelty": self.novelty,
            "evidence_refs": list(self.evidence_refs),
            "assumptions": list(self.assumptions),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class EpistemicGap:
    gap_id: str
    obligation_id: str
    kind: GapKind
    signal: float
    severity: float
    decision_impact: float
    rationale: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    status: GapStatus = GapStatus.OPEN
    fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "gap_id", require_id("gap_id", self.gap_id))
        object.__setattr__(self, "obligation_id", require_id("obligation_id", self.obligation_id))
        if not isinstance(self.kind, GapKind):
            object.__setattr__(self, "kind", GapKind(str(self.kind)))
        if not isinstance(self.status, GapStatus):
            object.__setattr__(self, "status", GapStatus(str(self.status)))
        object.__setattr__(self, "signal", probability("signal", self.signal))
        object.__setattr__(self, "severity", probability("severity", self.severity))
        object.__setattr__(
            self,
            "decision_impact",
            probability("decision_impact", self.decision_impact),
        )
        object.__setattr__(self, "rationale", tuple(str(item)[:4096] for item in self.rationale))
        object.__setattr__(
            self,
            "evidence_refs",
            tuple(sorted(set(require_id("evidence_ref", item) for item in self.evidence_refs))),
        )
        if not self.fingerprint:
            object.__setattr__(
                self,
                "fingerprint",
                stable_fingerprint(
                    {
                        "gap_id": self.gap_id,
                        "obligation_id": self.obligation_id,
                        "kind": self.kind.value,
                        "signal": self.signal,
                        "severity": self.severity,
                        "impact": self.decision_impact,
                        "rationale": self.rationale,
                        "evidence_refs": self.evidence_refs,
                        "status": self.status.value,
                    }
                ),
            )

    def as_json(self) -> dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "obligation_id": self.obligation_id,
            "kind": self.kind.value,
            "signal": self.signal,
            "severity": self.severity,
            "decision_impact": self.decision_impact,
            "rationale": list(self.rationale),
            "evidence_refs": list(self.evidence_refs),
            "status": self.status.value,
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class ProbeCandidate:
    probe_id: str
    gap_id: str
    obligation_id: str
    kind: ProbeKind
    risk: RiskTier
    expected_information_gain_bits: float
    expected_decision_value: float
    expected_cost: float
    score: float
    instruction: str
    preconditions: tuple[str, ...] = ()
    fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "probe_id", require_id("probe_id", self.probe_id))
        object.__setattr__(self, "gap_id", require_id("gap_id", self.gap_id))
        object.__setattr__(self, "obligation_id", require_id("obligation_id", self.obligation_id))
        if not isinstance(self.kind, ProbeKind):
            object.__setattr__(self, "kind", ProbeKind(str(self.kind)))
        if not isinstance(self.risk, RiskTier):
            object.__setattr__(self, "risk", RiskTier(str(self.risk)))
        object.__setattr__(
            self,
            "expected_information_gain_bits",
            _bounded_nonnegative(
                "expected_information_gain_bits",
                self.expected_information_gain_bits,
                maximum=64.0,
            ),
        )
        object.__setattr__(
            self,
            "expected_decision_value",
            _bounded_nonnegative("expected_decision_value", self.expected_decision_value),
        )
        object.__setattr__(
            self,
            "expected_cost",
            _bounded_nonnegative("expected_cost", self.expected_cost),
        )
        object.__setattr__(self, "score", finite_number("score", self.score))
        object.__setattr__(
            self,
            "instruction",
            bounded_text("instruction", self.instruction, maximum=8192),
        )
        object.__setattr__(
            self,
            "preconditions",
            tuple(bounded_text("precondition", item, maximum=2048) for item in self.preconditions),
        )
        if not self.fingerprint:
            object.__setattr__(
                self,
                "fingerprint",
                stable_fingerprint(
                    {
                        "probe_id": self.probe_id,
                        "gap_id": self.gap_id,
                        "kind": self.kind.value,
                        "risk": self.risk.value,
                        "information": self.expected_information_gain_bits,
                        "value": self.expected_decision_value,
                        "cost": self.expected_cost,
                        "score": self.score,
                        "instruction": self.instruction,
                    }
                ),
            )

    def as_json(self) -> dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "gap_id": self.gap_id,
            "obligation_id": self.obligation_id,
            "kind": self.kind.value,
            "risk": self.risk.value,
            "expected_information_gain_bits": self.expected_information_gain_bits,
            "expected_decision_value": self.expected_decision_value,
            "expected_cost": self.expected_cost,
            "score": self.score,
            "instruction": self.instruction,
            "preconditions": list(self.preconditions),
            "fingerprint": self.fingerprint,
        }


@dataclass(frozen=True, slots=True)
class ForecastContract:
    forecast_id: str
    obligation_id: str
    distribution: Mapping[str, float]
    created_at: float
    commitment: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "forecast_id", require_id("forecast_id", self.forecast_id))
        object.__setattr__(self, "obligation_id", require_id("obligation_id", self.obligation_id))
        if not self.distribution:
            raise AgentContractError("forecast distribution cannot be empty")
        normalized: dict[str, float] = {}
        for key, value in self.distribution.items():
            key = require_id("forecast_outcome", key)
            normalized[key] = _bounded_nonnegative(f"forecast[{key}]", value, maximum=1.0)
        total = sum(normalized.values())
        if total <= 0:
            raise AgentContractError("forecast distribution must have positive mass")
        normalized = {key: value / total for key, value in normalized.items()}
        object.__setattr__(self, "distribution", dict(sorted(normalized.items())))
        object.__setattr__(self, "created_at", finite_number("created_at", self.created_at))
        if not self.commitment:
            object.__setattr__(
                self,
                "commitment",
                stable_fingerprint(
                    {
                        "forecast_id": self.forecast_id,
                        "obligation_id": self.obligation_id,
                        "distribution": self.distribution,
                        "created_at": self.created_at,
                    }
                ),
            )


@dataclass(frozen=True, slots=True)
class ForecastSettlement:
    forecast_id: str
    observed_outcome: str
    probability_assigned: float
    brier_score: float
    surprise_bits: float
    settlement_fingerprint: str


@dataclass(frozen=True, slots=True)
class FrontierSnapshot:
    obligations: tuple[KnowledgeObligation, ...]
    gaps: tuple[EpistemicGap, ...]
    probes: tuple[ProbeCandidate, ...]
    frontier_pressure: float
    unresolved_decision_value: float
    fingerprint: str

    def as_json(self) -> dict[str, Any]:
        return {
            "obligations": [item.as_json() for item in self.obligations],
            "gaps": [item.as_json() for item in self.gaps],
            "probes": [item.as_json() for item in self.probes],
            "frontier_pressure": self.frontier_pressure,
            "unresolved_decision_value": self.unresolved_decision_value,
            "fingerprint": self.fingerprint,
        }


class EpistemicFrontierEngine:
    """Find and attack Jeeves' highest-value unresolved knowledge gaps."""

    _PROBE_BY_GAP = {
        GapKind.COVERAGE: ProbeKind.RETRIEVAL,
        GapKind.CONTRADICTION: ProbeKind.ADVERSARIAL_CHECK,
        GapKind.DISAGREEMENT: ProbeKind.DISCRIMINATING_TEST,
        GapKind.ASSUMPTION: ProbeKind.FALSIFICATION,
        GapKind.STALENESS: ProbeKind.REFRESH,
        GapKind.BLIND_SPOT: ProbeKind.RED_TEAM_SEARCH,
    }

    _BASE_COST = {
        ProbeKind.RETRIEVAL: 0.10,
        ProbeKind.ADVERSARIAL_CHECK: 0.20,
        ProbeKind.DISCRIMINATING_TEST: 0.35,
        ProbeKind.FALSIFICATION: 0.30,
        ProbeKind.REFRESH: 0.12,
        ProbeKind.RED_TEAM_SEARCH: 0.28,
    }

    def __init__(
        self,
        *,
        policy: EpistemicFrontierPolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.policy = policy or EpistemicFrontierPolicy()
        self._clock = clock
        self._forecasts: dict[str, ForecastContract] = {}

    def discover(self, obligations: Sequence[KnowledgeObligation]) -> FrontierSnapshot:
        checked = tuple(
            sorted(
                (
                    item
                    if isinstance(item, KnowledgeObligation)
                    else KnowledgeObligation(**dict(item))
                    for item in obligations
                ),
                key=lambda item: item.obligation_id,
            )
        )
        gaps: list[EpistemicGap] = []
        for obligation in checked:
            gaps.extend(self._gaps_for(obligation))
        gaps.sort(
            key=lambda item: (
                item.severity,
                item.signal,
                item.decision_impact,
                item.kind.value,
                item.gap_id,
            ),
            reverse=True,
        )

        probes = [self.propose_probe(gap, self._lookup(checked, gap.obligation_id)) for gap in gaps]
        probes.sort(
            key=lambda item: (
                item.score,
                item.expected_decision_value,
                item.expected_information_gain_bits,
                item.probe_id,
            ),
            reverse=True,
        )
        probes = probes[: self.policy.maximum_probes]

        if gaps:
            frontier_pressure = min(
                1.0,
                sum(item.severity for item in gaps) / max(1.0, len(checked) * 2.0),
            )
            unresolved_value = sum(
                item.severity * item.decision_impact for item in gaps
            )
        else:
            frontier_pressure = 0.0
            unresolved_value = 0.0

        payload = {
            "obligations": [item.fingerprint for item in checked],
            "gaps": [item.fingerprint for item in gaps],
            "probes": [item.fingerprint for item in probes],
            "frontier_pressure": frontier_pressure,
            "unresolved_decision_value": unresolved_value,
        }
        return FrontierSnapshot(
            obligations=checked,
            gaps=tuple(gaps),
            probes=tuple(probes),
            frontier_pressure=frontier_pressure,
            unresolved_decision_value=unresolved_value,
            fingerprint=stable_fingerprint(payload),
        )

    def _gaps_for(self, obligation: KnowledgeObligation) -> list[EpistemicGap]:
        signals = {
            GapKind.COVERAGE: obligation.coverage_deficit,
            GapKind.CONTRADICTION: obligation.contradiction_strength,
            GapKind.DISAGREEMENT: obligation.model_disagreement,
            GapKind.ASSUMPTION: max(
                obligation.assumption_load,
                min(1.0, len(obligation.assumptions) / 4.0),
            ),
            GapKind.STALENESS: obligation.staleness,
        }
        result: list[EpistemicGap] = []
        for kind, signal in signals.items():
            if signal >= self.policy.minimum_signal:
                result.append(self._make_gap(obligation, kind, signal))

        if (
            obligation.decision_impact >= self.policy.blind_spot_minimum_impact
            and obligation.evidence_coverage <= self.policy.blind_spot_maximum_coverage
            and obligation.confidence >= self.policy.blind_spot_minimum_confidence
        ):
            blind_signal = min(
                1.0,
                0.55 * obligation.coverage_deficit
                + 0.25 * obligation.confidence
                + 0.20 * max(obligation.novelty, 0.25),
            )
            result.append(self._make_gap(obligation, GapKind.BLIND_SPOT, blind_signal))
        return result

    def _make_gap(
        self,
        obligation: KnowledgeObligation,
        kind: GapKind,
        signal: float,
    ) -> EpistemicGap:
        uncertainty_bonus = 0.25 * obligation.uncertainty
        novelty_bonus = 0.15 * obligation.novelty
        severity = min(
            1.0,
            obligation.decision_impact
            * min(1.0, signal + uncertainty_bonus + novelty_bonus),
        )
        rationale = self._rationale(obligation, kind, signal)
        gap_id = stable_id(
            "epistemic-gap",
            {
                "obligation": obligation.obligation_id,
                "kind": kind.value,
                "source": obligation.fingerprint,
            },
            length=30,
        )
        return EpistemicGap(
            gap_id=gap_id,
            obligation_id=obligation.obligation_id,
            kind=kind,
            signal=signal,
            severity=severity,
            decision_impact=obligation.decision_impact,
            rationale=rationale,
            evidence_refs=obligation.evidence_refs,
        )

    @staticmethod
    def _rationale(
        obligation: KnowledgeObligation,
        kind: GapKind,
        signal: float,
    ) -> tuple[str, ...]:
        common = (
            f"decision impact={obligation.decision_impact:.3f}",
            f"gap signal={signal:.3f}",
        )
        if kind is GapKind.COVERAGE:
            return common + (
                f"evidence coverage={obligation.evidence_coverage:.3f}",
                "the claim is under-supported by explicit evidence",
            )
        if kind is GapKind.CONTRADICTION:
            return common + (
                f"contradiction strength={obligation.contradiction_strength:.3f}",
                "conflicting evidence should be resolved before promotion",
            )
        if kind is GapKind.DISAGREEMENT:
            return common + (
                f"model disagreement={obligation.model_disagreement:.3f}",
                "competing predictors materially disagree",
            )
        if kind is GapKind.ASSUMPTION:
            return common + (
                f"assumption load={obligation.assumption_load:.3f}",
                f"explicit assumptions={len(obligation.assumptions)}",
            )
        if kind is GapKind.STALENESS:
            return common + (
                f"freshness={obligation.freshness:.3f}",
                "decision evidence may no longer represent the current regime",
            )
        return common + (
            f"confidence={obligation.confidence:.3f}",
            f"evidence coverage={obligation.evidence_coverage:.3f}",
            "high confidence with weak coverage is treated as a blind spot",
        )

    def propose_probe(
        self,
        gap: EpistemicGap,
        obligation: KnowledgeObligation,
        *,
        risk: RiskTier = RiskTier.READ_ONLY,
        expected_cost: float | None = None,
    ) -> ProbeCandidate:
        if not isinstance(risk, RiskTier):
            risk = RiskTier(str(risk))
        kind = self._PROBE_BY_GAP[gap.kind]
        cost = (
            self._BASE_COST[kind]
            if expected_cost is None
            else _bounded_nonnegative("expected_cost", expected_cost)
        )
        information = _entropy_binary(gap.signal)
        decision_value = gap.decision_impact * gap.severity * information
        score = (
            self.policy.information_gain_weight * information
            + self.policy.decision_value_weight * decision_value
            - self.policy.cost_weight * cost
            - self.policy.risk_weight * _RISK_PENALTY[risk]
        )
        instruction = self._probe_instruction(kind, obligation)
        preconditions: tuple[str, ...] = ()
        if risk not in {RiskTier.READ_ONLY, RiskTier.REVERSIBLE}:
            preconditions = (
                "require explicit policy authorization before execution",
                "record rollback or containment plan",
            )
        probe_id = stable_id(
            "epistemic-probe",
            {
                "gap": gap.gap_id,
                "kind": kind.value,
                "risk": risk.value,
                "cost": cost,
                "instruction": instruction,
            },
            length=30,
        )
        return ProbeCandidate(
            probe_id=probe_id,
            gap_id=gap.gap_id,
            obligation_id=gap.obligation_id,
            kind=kind,
            risk=risk,
            expected_information_gain_bits=information,
            expected_decision_value=decision_value,
            expected_cost=cost,
            score=score,
            instruction=instruction,
            preconditions=preconditions,
        )

    @staticmethod
    def _probe_instruction(kind: ProbeKind, obligation: KnowledgeObligation) -> str:
        q = obligation.question
        if kind is ProbeKind.RETRIEVAL:
            return f"Retrieve independent primary evidence for: {q}"
        if kind is ProbeKind.ADVERSARIAL_CHECK:
            return f"Separate conflicting evidence for '{q}' by source, timestamp, and falsifiable prediction."
        if kind is ProbeKind.DISCRIMINATING_TEST:
            return f"Design the smallest safe observation that makes competing predictions diverge for: {q}"
        if kind is ProbeKind.FALSIFICATION:
            return f"Attempt to falsify the strongest unsupported assumption behind: {q}"
        if kind is ProbeKind.REFRESH:
            return f"Refresh the decisive evidence under the current regime for: {q}"
        return (
            f"Search outside the current evidence neighborhood for omitted variables, "
            f"counterexamples, and alternative framings of: {q}"
        )

    def precommit_forecast(
        self,
        obligation_id: str,
        distribution: Mapping[str, float],
        *,
        forecast_id: str | None = None,
    ) -> ForecastContract:
        obligation_id = require_id("obligation_id", obligation_id)
        created_at = finite_number("created_at", self._clock())
        raw_id = forecast_id or stable_id(
            "forecast",
            {
                "obligation": obligation_id,
                "distribution": dict(distribution),
                "created_at": created_at,
            },
            length=30,
        )
        contract = ForecastContract(
            forecast_id=raw_id,
            obligation_id=obligation_id,
            distribution=distribution,
            created_at=created_at,
            commitment="",
        )
        if contract.forecast_id in self._forecasts:
            raise AgentContractError("forecast_id already exists; forecasts are immutable")
        self._forecasts[contract.forecast_id] = contract
        return contract

    def settle_forecast(
        self,
        forecast_id: str,
        observed_outcome: str,
    ) -> ForecastSettlement:
        forecast_id = require_id("forecast_id", forecast_id)
        observed_outcome = require_id("observed_outcome", observed_outcome)
        try:
            contract = self._forecasts[forecast_id]
        except KeyError as exc:
            raise AgentContractError("unknown forecast_id") from exc
        if observed_outcome not in contract.distribution:
            raise AgentContractError("observed outcome is outside forecast support")
        assigned = contract.distribution[observed_outcome]
        outcomes = tuple(contract.distribution)
        brier = sum(
            (
                contract.distribution[outcome]
                - (1.0 if outcome == observed_outcome else 0.0)
            )
            ** 2
            for outcome in outcomes
        )
        surprise = -math.log2(max(_EPS, assigned))
        settlement_fingerprint = stable_fingerprint(
            {
                "commitment": contract.commitment,
                "observed": observed_outcome,
                "assigned": assigned,
                "brier": brier,
                "surprise_bits": surprise,
            }
        )
        return ForecastSettlement(
            forecast_id=forecast_id,
            observed_outcome=observed_outcome,
            probability_assigned=assigned,
            brier_score=brier,
            surprise_bits=surprise,
            settlement_fingerprint=settlement_fingerprint,
        )

    def forecast(self, forecast_id: str) -> ForecastContract:
        forecast_id = require_id("forecast_id", forecast_id)
        try:
            return self._forecasts[forecast_id]
        except KeyError as exc:
            raise AgentContractError("unknown forecast_id") from exc

    def dump_forecasts(self) -> dict[str, Any]:
        """Serialize immutable forecast commitments for replay/audit."""

        forecasts = tuple(
            sorted(self._forecasts.values(), key=lambda item: item.forecast_id)
        )
        return {
            "version": 1,
            "forecasts": [
                {
                    "forecast_id": item.forecast_id,
                    "obligation_id": item.obligation_id,
                    "distribution": dict(item.distribution),
                    "created_at": item.created_at,
                    "commitment": item.commitment,
                }
                for item in forecasts
            ],
            "fingerprint": stable_fingerprint(
                [item.commitment for item in forecasts]
            ),
        }

    def restore_forecasts(
        self,
        state: Mapping[str, Any],
        *,
        replace_existing: bool = True,
    ) -> tuple[ForecastContract, ...]:
        """Restore commitments and verify every commitment hash."""

        payload = json_safe(dict(state))
        if payload.get("version") != 1:
            raise AgentContractError("unsupported forecast state version")
        restored: dict[str, ForecastContract] = {}
        for value in payload.get("forecasts", ()):
            contract = ForecastContract(
                forecast_id=value["forecast_id"],
                obligation_id=value["obligation_id"],
                distribution=dict(value["distribution"]),
                created_at=value["created_at"],
                commitment="",
            )
            if contract.commitment != value.get("commitment"):
                raise AgentContractError(
                    "forecast commitment mismatch during restore"
                )
            if contract.forecast_id in restored:
                raise AgentContractError("duplicate forecast_id in state")
            restored[contract.forecast_id] = contract
        expected = payload.get("fingerprint")
        actual = stable_fingerprint(
            [
                item.commitment
                for item in sorted(
                    restored.values(),
                    key=lambda item: item.forecast_id,
                )
            ]
        )
        if expected is not None and expected != actual:
            raise AgentContractError("forecast state fingerprint mismatch")
        if replace_existing:
            self._forecasts = restored
        else:
            overlap = set(restored) & set(self._forecasts)
            if overlap:
                raise AgentContractError(
                    "forecast restore collides with existing commitments"
                )
            self._forecasts.update(restored)
        return tuple(
            sorted(restored.values(), key=lambda item: item.forecast_id)
        )

    @staticmethod
    def _lookup(
        obligations: Sequence[KnowledgeObligation],
        obligation_id: str,
    ) -> KnowledgeObligation:
        for item in obligations:
            if item.obligation_id == obligation_id:
                return item
        raise AgentContractError(f"unknown obligation {obligation_id}")
