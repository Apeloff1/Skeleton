"""Adversarial, bias-aware verification for Jeeves.

Verification is increasingly the bottleneck for strong agents.  A single model
judge is a fragile proxy: it can share the generator's blind spots, be sensitive
to presentation, or learn to reward whatever the policy optimizes.  This module
therefore treats learned judges as *fallible sensors* around authoritative host
checks rather than as a source of truth.

Key properties:

* independent judge identities and family-aware quorum requirements;
* abstention as a first-class outcome;
* per-axis verdicts instead of one opaque scalar;
* correlated-judge down-weighting from historical agreement;
* influence caps so one judge cannot dominate a council;
* order/style/label perturbation probes for judge-instability detection;
* adversarial counterexample and missing-evidence challenges;
* lower/upper acceptance bounds rather than false precision;
* explicit separation between host facts and model opinions;
* reward-hacking alarms when verifier scores improve while host checks regress.

The module intentionally does not execute models.  Provider-backed judge calls
are supplied by an adapter, which keeps this layer deterministic and testable.
"""

from __future__ import annotations

import math
import statistics
import threading
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Protocol, Sequence

from .evidence import EvidenceLedger, GroundingGate, GroundingPolicy
from .types import (
    AgentContractError,
    Claim,
    EvidenceRef,
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


class VerificationCouncilError(RuntimeError):
    pass


class Verdict(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    ABSTAIN = "abstain"


class JudgeAxis(str, Enum):
    CORRECTNESS = "correctness"
    GROUNDING = "grounding"
    COMPLETENESS = "completeness"
    INTERNAL_CONSISTENCY = "internal_consistency"
    RISK = "risk"
    INSTRUCTION_FIDELITY = "instruction_fidelity"
    CALIBRATION = "calibration"
    ROBUSTNESS = "robustness"


class ProbeKind(str, Enum):
    ORDER_SWAP = "order_swap"
    LABEL_SWAP = "label_swap"
    STYLE_NORMALIZE = "style_normalize"
    DISTRACTOR = "distractor"
    EVIDENCE_MASK = "evidence_mask"
    COUNTEREXAMPLE = "counterexample"
    CONTRADICTION = "contradiction"
    MINIMAL_PAIR = "minimal_pair"


class ChallengeKind(str, Enum):
    MISSING_EVIDENCE = "missing_evidence"
    CONTRADICTORY_EVIDENCE = "contradictory_evidence"
    COUNTEREXAMPLE = "counterexample"
    UNSAFE_GENERALIZATION = "unsafe_generalization"
    UNVERIFIED_CAUSALITY = "unverified_causality"
    STALE_EVIDENCE = "stale_evidence"
    OVERCONFIDENCE = "overconfidence"
    SCOPE_DRIFT = "scope_drift"


@dataclass(frozen=True, slots=True)
class JudgeIdentity:
    judge_id: str
    provider: str
    model: str
    family: str
    rubric_version: str
    prompt_fingerprint: str
    independent_group: str
    is_host: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "judge_id", require_id("judge_id", self.judge_id))
        for name in ("provider", "model", "family", "rubric_version", "independent_group"):
            object.__setattr__(self, name, require_id(name, getattr(self, name)))
        fingerprint = str(self.prompt_fingerprint).strip().lower()
        if len(fingerprint) < 16:
            raise AgentContractError("prompt_fingerprint too short")
        object.__setattr__(self, "prompt_fingerprint", fingerprint)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def independence_key(self) -> str:
        return f"{self.provider}:{self.family}:{self.independent_group}"


@dataclass(frozen=True, slots=True)
class AxisScore:
    axis: JudgeAxis
    score: float
    confidence: float
    rationale: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.axis, JudgeAxis):
            object.__setattr__(self, "axis", JudgeAxis(str(self.axis)))
        object.__setattr__(self, "score", probability("axis score", self.score))
        object.__setattr__(self, "confidence", probability("axis confidence", self.confidence))
        object.__setattr__(self, "rationale", bounded_text("axis rationale", self.rationale, maximum=4096))
        object.__setattr__(self, "evidence_ids", tuple(require_id("evidence_id", value) for value in self.evidence_ids))


@dataclass(frozen=True, slots=True)
class JudgeVote:
    vote_id: str
    judge: JudgeIdentity
    verdict: Verdict
    confidence: float
    axes: tuple[AxisScore, ...]
    critical_findings: tuple[str, ...] = ()
    uncertainty_notes: tuple[str, ...] = ()
    at: float = field(default_factory=time.time)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "vote_id", require_id("vote_id", self.vote_id))
        if not isinstance(self.judge, JudgeIdentity):
            raise AgentContractError("judge must be JudgeIdentity")
        if not isinstance(self.verdict, Verdict):
            object.__setattr__(self, "verdict", Verdict(str(self.verdict)))
        object.__setattr__(self, "confidence", probability("vote confidence", self.confidence))
        axes = tuple(self.axes)
        if any(not isinstance(item, AxisScore) for item in axes):
            raise AgentContractError("axes must contain AxisScore")
        if len({item.axis for item in axes}) != len(axes):
            raise AgentContractError("duplicate judge axis")
        object.__setattr__(self, "axes", axes)
        object.__setattr__(self, "critical_findings", tuple(bounded_text("critical finding", value, maximum=2048) for value in self.critical_findings))
        object.__setattr__(self, "uncertainty_notes", tuple(bounded_text("uncertainty note", value, maximum=2048) for value in self.uncertainty_notes))
        at = finite_number("at", self.at)
        if at < 0:
            raise AgentContractError("vote timestamp must be non-negative")
        object.__setattr__(self, "at", at)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def mean_axis_score(self) -> float:
        return statistics.fmean(item.score for item in self.axes) if self.axes else 0.5

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "judge": self.judge.judge_id,
                "verdict": self.verdict.value,
                "confidence": self.confidence,
                "axes": [(item.axis.value, item.score, item.confidence, item.evidence_ids) for item in self.axes],
                "critical": self.critical_findings,
            }
        )


class JudgeAdapter(Protocol):
    identity: JudgeIdentity

    def evaluate(self, subject: "VerificationSubject") -> JudgeVote:
        ...


@dataclass(frozen=True, slots=True)
class VerificationSubject:
    subject_id: str
    answer: str
    claims: tuple[Claim, ...]
    required_criteria: tuple[str, ...] = ()
    risk: RiskTier = RiskTier.READ_ONLY
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_id", require_id("subject_id", self.subject_id))
        object.__setattr__(self, "answer", bounded_text("answer", self.answer, maximum=256_000, allow_empty=True))
        claims = tuple(self.claims)
        if any(not isinstance(claim, Claim) for claim in claims):
            raise AgentContractError("claims must contain Claim")
        object.__setattr__(self, "claims", claims)
        object.__setattr__(self, "required_criteria", tuple(bounded_text("criterion", value, maximum=4096) for value in self.required_criteria))
        if not isinstance(self.risk, RiskTier):
            object.__setattr__(self, "risk", RiskTier(str(self.risk)))
        object.__setattr__(self, "context", json_safe(dict(self.context)))

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint(
            {
                "answer": self.answer,
                "claims": [(claim.claim_id, claim.text, claim.confidence, [(ref.evidence_id, ref.fingerprint) for ref in claim.evidence]) for claim in self.claims],
                "criteria": self.required_criteria,
                "risk": self.risk.value,
                "context": self.context,
            }
        )


@dataclass(frozen=True, slots=True)
class AdversarialChallenge:
    challenge_id: str
    kind: ChallengeKind
    target_claim_id: str | None
    description: str
    severity: float
    evidence_ids: tuple[str, ...] = ()
    resolved: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "challenge_id", require_id("challenge_id", self.challenge_id))
        if not isinstance(self.kind, ChallengeKind):
            object.__setattr__(self, "kind", ChallengeKind(str(self.kind)))
        if self.target_claim_id is not None:
            object.__setattr__(self, "target_claim_id", require_id("target_claim_id", self.target_claim_id))
        object.__setattr__(self, "description", bounded_text("challenge description", self.description, maximum=4096))
        object.__setattr__(self, "severity", probability("challenge severity", self.severity))
        object.__setattr__(self, "evidence_ids", tuple(require_id("evidence_id", value) for value in self.evidence_ids))
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))


class HostChallengeGenerator:
    """Generate deterministic challenges from claim/evidence structure."""

    def __init__(self, *, stale_after_seconds: float = 24 * 3600.0, clock: Callable[[], float] = time.time) -> None:
        stale = finite_number("stale_after_seconds", stale_after_seconds)
        if stale <= 0:
            raise ValueError("stale_after_seconds must be positive")
        self.stale_after_seconds = stale
        self._clock = clock

    def generate(self, subject: VerificationSubject, ledger: EvidenceLedger | None = None) -> tuple[AdversarialChallenge, ...]:
        challenges: list[AdversarialChallenge] = []
        now = self._clock()
        for claim in subject.claims:
            if claim.derived and not claim.evidence:
                challenges.append(self._challenge(ChallengeKind.MISSING_EVIDENCE, claim, "Derived claim has no evidence binding.", 1.0))
            if claim.confidence >= 0.90 and len(claim.evidence) < 2:
                challenges.append(self._challenge(ChallengeKind.OVERCONFIDENCE, claim, "High-confidence claim has little independent support.", 0.55, [ref.evidence_id for ref in claim.evidence]))
            sources = Counter(ref.source for ref in claim.evidence)
            if claim.evidence and len(sources) == 1 and len(claim.evidence) > 1:
                challenges.append(self._challenge(ChallengeKind.COUNTEREXAMPLE, claim, "All cited evidence originates from one source; seek an independent countercheck.", 0.45, [ref.evidence_id for ref in claim.evidence]))
            stale_refs = [ref for ref in claim.evidence if now - ref.observed_at > self.stale_after_seconds]
            if stale_refs:
                challenges.append(self._challenge(ChallengeKind.STALE_EVIDENCE, claim, "Claim relies on stale evidence.", min(0.9, 0.35 + len(stale_refs) * 0.15), [ref.evidence_id for ref in stale_refs]))
            if ledger is not None:
                contradictions = ledger.contradictions_for(*(ref.evidence_id for ref in claim.evidence)) if claim.evidence else ()
                if contradictions:
                    evidence_ids = sorted({value for contradiction in contradictions for value in (contradiction.left_evidence_id, contradiction.right_evidence_id)})
                    challenges.append(self._challenge(ChallengeKind.CONTRADICTORY_EVIDENCE, claim, "Claim evidence participates in unresolved contradiction(s).", 0.85, evidence_ids))
            lowered = claim.text.casefold()
            if any(token in lowered for token in ("causes", "caused", "therefore caused", "proves that")) and len(claim.evidence) < 2:
                challenges.append(self._challenge(ChallengeKind.UNVERIFIED_CAUSALITY, claim, "Causal language is stronger than the available support structure.", 0.65, [ref.evidence_id for ref in claim.evidence]))
        return tuple(challenges)

    @staticmethod
    def _challenge(kind: ChallengeKind, claim: Claim, description: str, severity: float, evidence_ids: Sequence[str] = ()) -> AdversarialChallenge:
        payload = {"kind": kind.value, "claim": claim.claim_id, "description": description, "evidence": tuple(evidence_ids)}
        return AdversarialChallenge(stable_id("challenge", payload), kind, claim.claim_id, description, severity, tuple(evidence_ids), False, {})


@dataclass(frozen=True, slots=True)
class BiasProbeResult:
    probe_id: str
    judge_id: str
    kind: ProbeKind
    baseline_score: float
    perturbed_score: float
    delta: float
    unstable: bool
    fingerprint: str


class JudgeStabilityTracker:
    """Track judge agreement, instability, and empirical calibration."""

    def __init__(self, *, history_limit: int = 4096) -> None:
        self._votes: dict[str, deque[tuple[str, float, bool | None]]] = defaultdict(lambda: deque(maxlen=history_limit))
        self._pair_history: dict[tuple[str, str], deque[tuple[float, float]]] = defaultdict(lambda: deque(maxlen=history_limit))
        self._probe_deltas: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=history_limit))
        self._lock = threading.RLock()

    def observe_council(self, subject_id: str, votes: Sequence[JudgeVote], *, ground_truth: bool | None = None) -> None:
        subject_id = require_id("subject_id", subject_id)
        with self._lock:
            for vote in votes:
                score = vote.mean_axis_score
                self._votes[vote.judge.judge_id].append((subject_id, score, ground_truth))
            for index, left in enumerate(votes):
                for right in votes[index + 1 :]:
                    key = tuple(sorted((left.judge.judge_id, right.judge.judge_id)))
                    self._pair_history[key].append((left.mean_axis_score, right.mean_axis_score))

    def observe_probe(self, result: BiasProbeResult) -> None:
        with self._lock:
            self._probe_deltas[result.judge_id].append(abs(result.delta))

    def pair_correlation(self, left_id: str, right_id: str) -> float:
        key = tuple(sorted((require_id("judge_id", left_id), require_id("judge_id", right_id))))
        with self._lock:
            values = tuple(self._pair_history.get(key, ()))
        if len(values) < 3:
            return 0.0
        xs = [value[0] for value in values]
        ys = [value[1] for value in values]
        mean_x = statistics.fmean(xs)
        mean_y = statistics.fmean(ys)
        covariance = sum((x - mean_x) * (y - mean_y) for x, y in values)
        var_x = sum((x - mean_x) ** 2 for x in xs)
        var_y = sum((y - mean_y) ** 2 for y in ys)
        if var_x <= 1e-12 or var_y <= 1e-12:
            return 1.0 if all(abs(x - y) < 1e-9 for x, y in values) else 0.0
        return max(-1.0, min(1.0, covariance / math.sqrt(var_x * var_y)))

    def judge_instability(self, judge_id: str) -> float:
        judge_id = require_id("judge_id", judge_id)
        with self._lock:
            values = tuple(self._probe_deltas.get(judge_id, ()))
        return min(1.0, statistics.fmean(values)) if values else 0.0

    def calibration_error(self, judge_id: str) -> float:
        judge_id = require_id("judge_id", judge_id)
        with self._lock:
            values = [item for item in self._votes.get(judge_id, ()) if item[2] is not None]
        if not values:
            return 0.25
        return min(1.0, statistics.fmean(abs(score - (1.0 if truth else 0.0)) for _, score, truth in values))


@dataclass(frozen=True, slots=True)
class CouncilPolicy:
    minimum_judges: int = 3
    minimum_independent_groups: int = 2
    accept_threshold: float = 0.72
    reject_threshold: float = 0.35
    minimum_host_score: float = 0.70
    maximum_single_judge_influence: float = 0.40
    correlation_penalty: float = 0.55
    instability_penalty: float = 0.45
    abstention_penalty: float = 0.25
    critical_challenge_block: float = 0.80

    def __post_init__(self) -> None:
        object.__setattr__(self, "minimum_judges", positive_int("minimum_judges", self.minimum_judges, maximum=100))
        object.__setattr__(self, "minimum_independent_groups", positive_int("minimum_independent_groups", self.minimum_independent_groups, maximum=100))
        for name in ("accept_threshold", "reject_threshold", "minimum_host_score", "maximum_single_judge_influence", "correlation_penalty", "instability_penalty", "abstention_penalty", "critical_challenge_block"):
            object.__setattr__(self, name, probability(name, getattr(self, name)))
        if self.reject_threshold >= self.accept_threshold:
            raise AgentContractError("reject threshold must be below accept threshold")


@dataclass(frozen=True, slots=True)
class WeightedVote:
    vote: JudgeVote
    base_weight: float
    independence_weight: float
    stability_weight: float
    calibration_weight: float
    final_weight: float


@dataclass(frozen=True, slots=True)
class CouncilVerdict:
    subject_id: str
    verdict: Verdict
    score: float
    lower_bound: float
    upper_bound: float
    host_score: float
    weighted_votes: tuple[WeightedVote, ...]
    axis_scores: Mapping[str, float]
    challenges: tuple[AdversarialChallenge, ...]
    quorum_satisfied: bool
    reward_hacking_alarm: bool
    reasons: tuple[str, ...]
    fingerprint: str


class BiasBoundedAggregator:
    def __init__(self, policy: CouncilPolicy | None = None, tracker: JudgeStabilityTracker | None = None) -> None:
        self.policy = policy or CouncilPolicy()
        self.tracker = tracker or JudgeStabilityTracker()

    def aggregate(
        self,
        subject: VerificationSubject,
        votes: Sequence[JudgeVote],
        *,
        host_score: float,
        challenges: Sequence[AdversarialChallenge] = (),
        previous_host_score: float | None = None,
        previous_judge_score: float | None = None,
    ) -> CouncilVerdict:
        host_score = probability("host_score", host_score)
        if any(not isinstance(vote, JudgeVote) for vote in votes):
            raise TypeError("votes must contain JudgeVote")
        unique_judges = {vote.judge.judge_id for vote in votes}
        if len(unique_judges) != len(votes):
            raise VerificationCouncilError("duplicate judge vote")
        independent_groups = {vote.judge.independence_key for vote in votes}
        quorum = len(votes) >= self.policy.minimum_judges and len(independent_groups) >= self.policy.minimum_independent_groups
        weighted = self._weight_votes(votes)
        model_score = self._weighted_mean(weighted)
        # Host checks are the anchor.  Learned judges can strengthen or weaken
        # confidence around them, but cannot override a catastrophically low
        # host score.
        combined = host_score * 0.55 + model_score * 0.45 if weighted else host_score
        unresolved_critical = [item for item in challenges if not item.resolved and item.severity >= self.policy.critical_challenge_block]
        if unresolved_critical:
            combined = min(combined, self.policy.reject_threshold)
        if not quorum:
            combined = min(combined, (self.policy.accept_threshold + self.policy.reject_threshold) / 2)
        lower, upper = self._bounds(weighted, host_score, combined)
        if host_score < self.policy.minimum_host_score:
            verdict = Verdict.REJECT
        elif unresolved_critical:
            verdict = Verdict.REJECT
        elif quorum and lower >= self.policy.accept_threshold:
            verdict = Verdict.ACCEPT
        elif upper <= self.policy.reject_threshold:
            verdict = Verdict.REJECT
        else:
            verdict = Verdict.ABSTAIN
        axes = self._axis_scores(weighted)
        reward_alarm = False
        if previous_host_score is not None and previous_judge_score is not None:
            prior_host = probability("previous_host_score", previous_host_score)
            prior_judge = probability("previous_judge_score", previous_judge_score)
            reward_alarm = model_score > prior_judge + 0.08 and host_score < prior_host - 0.05
        reasons = self._reasons(verdict, quorum, host_score, model_score, unresolved_critical, reward_alarm)
        payload = {
            "subject": subject.subject_id,
            "verdict": verdict.value,
            "score": combined,
            "lower": lower,
            "upper": upper,
            "host": host_score,
            "votes": [(item.vote.vote_id, item.final_weight, item.vote.fingerprint) for item in weighted],
            "challenges": [(item.challenge_id, item.severity, item.resolved) for item in challenges],
            "alarm": reward_alarm,
        }
        return CouncilVerdict(subject.subject_id, verdict, combined, lower, upper, host_score, tuple(weighted), axes, tuple(challenges), quorum, reward_alarm, reasons, stable_fingerprint(payload))

    def _weight_votes(self, votes: Sequence[JudgeVote]) -> list[WeightedVote]:
        raw: list[WeightedVote] = []
        for vote in votes:
            correlations = [max(0.0, self.tracker.pair_correlation(vote.judge.judge_id, other.judge.judge_id)) for other in votes if other.judge.judge_id != vote.judge.judge_id]
            mean_correlation = statistics.fmean(correlations) if correlations else 0.0
            independence = max(0.05, 1.0 - mean_correlation * self.policy.correlation_penalty)
            instability = self.tracker.judge_instability(vote.judge.judge_id)
            stability = max(0.05, 1.0 - instability * self.policy.instability_penalty)
            calibration = max(0.05, 1.0 - self.tracker.calibration_error(vote.judge.judge_id))
            base = vote.confidence * (0.25 if vote.verdict is Verdict.ABSTAIN else 1.0)
            if vote.judge.is_host:
                base *= 1.25
            final = base * independence * stability * calibration
            raw.append(WeightedVote(vote, base, independence, stability, calibration, final))
        total = sum(item.final_weight for item in raw)
        if total <= 0:
            return raw
        capped: list[WeightedVote] = []
        for item in raw:
            normalized = item.final_weight / total
            normalized = min(self.policy.maximum_single_judge_influence, normalized)
            capped.append(WeightedVote(item.vote, item.base_weight, item.independence_weight, item.stability_weight, item.calibration_weight, normalized))
        renormalizer = sum(item.final_weight for item in capped)
        if renormalizer > 0:
            capped = [WeightedVote(item.vote, item.base_weight, item.independence_weight, item.stability_weight, item.calibration_weight, item.final_weight / renormalizer) for item in capped]
        return capped

    @staticmethod
    def _weighted_mean(weighted: Sequence[WeightedVote]) -> float:
        if not weighted:
            return 0.5
        score = 0.0
        total = 0.0
        for item in weighted:
            if item.vote.verdict is Verdict.ABSTAIN:
                vote_score = 0.5
            else:
                vote_score = item.vote.mean_axis_score
            score += vote_score * item.final_weight
            total += item.final_weight
        return score / total if total else 0.5

    @staticmethod
    def _bounds(weighted: Sequence[WeightedVote], host_score: float, combined: float) -> tuple[float, float]:
        if not weighted:
            uncertainty = 0.15
        else:
            scores = [item.vote.mean_axis_score for item in weighted if item.vote.verdict is not Verdict.ABSTAIN]
            disagreement = statistics.pstdev(scores) if len(scores) > 1 else 0.08
            confidence_gap = statistics.fmean(1.0 - item.vote.confidence for item in weighted)
            uncertainty = min(0.45, 0.08 + disagreement * 0.65 + confidence_gap * 0.25)
        uncertainty += abs(host_score - combined) * 0.20
        return max(0.0, combined - uncertainty), min(1.0, combined + uncertainty)

    @staticmethod
    def _axis_scores(weighted: Sequence[WeightedVote]) -> Mapping[str, float]:
        values: dict[JudgeAxis, list[tuple[float, float]]] = defaultdict(list)
        for item in weighted:
            for axis in item.vote.axes:
                values[axis.axis].append((axis.score, item.final_weight * axis.confidence))
        result: dict[str, float] = {}
        for axis, entries in values.items():
            total = sum(weight for _, weight in entries)
            result[axis.value] = sum(score * weight for score, weight in entries) / total if total else 0.5
        return dict(sorted(result.items()))

    @staticmethod
    def _reasons(verdict: Verdict, quorum: bool, host_score: float, model_score: float, critical: Sequence[AdversarialChallenge], reward_alarm: bool) -> tuple[str, ...]:
        reasons = [f"host_score={host_score:.3f}", f"judge_score={model_score:.3f}", f"quorum={'yes' if quorum else 'no'}"]
        if critical:
            reasons.append(f"unresolved critical challenges={len(critical)}")
        if reward_alarm:
            reasons.append("reward-hacking alarm: learned verifier improved while host verifier regressed")
        reasons.append(f"verdict={verdict.value}")
        return tuple(reasons)


@dataclass(frozen=True, slots=True)
class HostVerificationResult:
    score: float
    grounding_score: float
    evidence_integrity: float
    claim_coverage: float
    critical_failures: tuple[str, ...]


class HostVerifier:
    """Evidence/contract verifier that never asks a language model to grade itself."""

    def __init__(self, policy: GroundingPolicy | None = None) -> None:
        self.policy = policy or GroundingPolicy()

    def verify(self, subject: VerificationSubject, ledger: EvidenceLedger) -> HostVerificationResult:
        gate = GroundingGate(ledger, self.policy)
        report = gate.validate(subject.claims)
        grounding = 1.0 if report.accepted else max(0.0, 1.0 - len(report.errors) * 0.20 - len(report.warnings) * 0.05)
        integrity_values: list[float] = []
        covered = 0
        failures: list[str] = []
        for claim in subject.claims:
            valid = 0
            for ref in claim.evidence:
                artifact = ledger.get(ref.evidence_id)
                if artifact is not None and artifact.fingerprint == ref.fingerprint:
                    valid += 1
                    integrity_values.append(1.0)
                else:
                    integrity_values.append(0.0)
            if claim.evidence and valid == len(claim.evidence):
                covered += 1
            if claim.derived and not claim.evidence:
                failures.append(f"derived claim lacks evidence: {claim.claim_id}")
        integrity = statistics.fmean(integrity_values) if integrity_values else (1.0 if not subject.claims else 0.0)
        coverage = covered / len(subject.claims) if subject.claims else 1.0
        score = grounding * 0.45 + integrity * 0.35 + coverage * 0.20
        failures.extend(report.errors)
        return HostVerificationResult(max(0.0, min(1.0, score)), grounding, integrity, coverage, tuple(failures))


class VerificationCouncil:
    def __init__(
        self,
        judges: Sequence[JudgeAdapter],
        *,
        host_verifier: HostVerifier | None = None,
        aggregator: BiasBoundedAggregator | None = None,
        challenge_generator: HostChallengeGenerator | None = None,
    ) -> None:
        self.judges = tuple(judges)
        identities = [judge.identity.judge_id for judge in self.judges]
        if len(set(identities)) != len(identities):
            raise VerificationCouncilError("duplicate judge identity")
        self.host = host_verifier or HostVerifier()
        self.aggregator = aggregator or BiasBoundedAggregator()
        self.challenges = challenge_generator or HostChallengeGenerator()

    def evaluate(
        self,
        subject: VerificationSubject,
        ledger: EvidenceLedger,
        *,
        previous_host_score: float | None = None,
        previous_judge_score: float | None = None,
    ) -> CouncilVerdict:
        host = self.host.verify(subject, ledger)
        challenges = self.challenges.generate(subject, ledger)
        votes: list[JudgeVote] = []
        for judge in self.judges:
            try:
                vote = judge.evaluate(subject)
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as exc:
                vote = JudgeVote(
                    vote_id=stable_id("vote", {"judge": judge.identity.judge_id, "subject": subject.subject_id, "error": type(exc).__name__}),
                    judge=judge.identity,
                    verdict=Verdict.ABSTAIN,
                    confidence=0.0,
                    axes=(),
                    critical_findings=(f"judge unavailable: {type(exc).__name__}",),
                )
            if vote.judge.judge_id != judge.identity.judge_id:
                raise VerificationCouncilError("judge adapter returned another identity")
            votes.append(vote)
        verdict = self.aggregator.aggregate(
            subject,
            votes,
            host_score=host.score,
            challenges=challenges,
            previous_host_score=previous_host_score,
            previous_judge_score=previous_judge_score,
        )
        self.aggregator.tracker.observe_council(subject.subject_id, votes, ground_truth=verdict.verdict is Verdict.ACCEPT if verdict.host_score >= 0.90 else None)
        return verdict


class DeterministicJudge:
    """Fixture judge for replay/evaluation; useful for testing council math."""

    def __init__(self, identity: JudgeIdentity, evaluator: Callable[[VerificationSubject], Mapping[str, Any]]) -> None:
        self.identity = identity
        self._evaluator = evaluator

    def evaluate(self, subject: VerificationSubject) -> JudgeVote:
        raw = json_safe(dict(self._evaluator(subject)))
        axes: list[AxisScore] = []
        for key, value in dict(raw.get("axes", {})).items():
            axis = JudgeAxis(str(key))
            if isinstance(value, dict):
                score = float(value.get("score", 0.5))
                confidence = float(value.get("confidence", raw.get("confidence", 0.5)))
                rationale = str(value.get("rationale", "fixture"))
                evidence_ids = tuple(value.get("evidence_ids", ()))
            else:
                score = float(value)
                confidence = float(raw.get("confidence", 0.5))
                rationale = "fixture"
                evidence_ids = ()
            axes.append(AxisScore(axis, score, confidence, rationale, evidence_ids))
        verdict = Verdict(str(raw.get("verdict", Verdict.ABSTAIN.value)))
        confidence = probability("confidence", raw.get("confidence", 0.5))
        vote_id = stable_id("vote", {"judge": self.identity.judge_id, "subject": subject.subject_id, "raw": raw})
        return JudgeVote(
            vote_id,
            self.identity,
            verdict,
            confidence,
            tuple(axes),
            tuple(str(value) for value in raw.get("critical_findings", ())),
            tuple(str(value) for value in raw.get("uncertainty_notes", ())),
            metadata=raw.get("metadata", {}),
        )


def make_judge_identity(
    judge_id: str,
    *,
    provider: str,
    model: str,
    family: str,
    rubric_version: str = "v1",
    independent_group: str | None = None,
    prompt: str = "default-rubric",
    is_host: bool = False,
) -> JudgeIdentity:
    return JudgeIdentity(
        judge_id=judge_id,
        provider=provider,
        model=model,
        family=family,
        rubric_version=rubric_version,
        prompt_fingerprint=stable_fingerprint(prompt),
        independent_group=independent_group or family,
        is_host=is_host,
    )
