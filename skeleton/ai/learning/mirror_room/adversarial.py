"""Adversarial 100-attempt ratchet for Mirror Room learning.

The ratchet is intentionally stricter than ordinary adaptive search:

* every attempt proposes exactly one novel candidate;
* an independent adversary supplies fresh TRAIN-only challenges after proposal;
* the candidate must beat the current ratchet baseline on both adversarial
  challenge evidence and stable validation evidence;
* an accepted upgrade becomes the next attempt's baseline;
* a rejected attempt cannot lower or mutate the baseline;
* validation metric floors are chained so accepted standards are monotonic;
* the sealed holdout is not touched before attempt 100;
* delivery evidence cannot exist until all 100 attempts are complete.

Nothing in this module has production mutation authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Mapping, Protocol, Sequence, runtime_checkable

from skeleton.contracts.canonical import EvidenceRef
from skeleton.eval.experiment_registry import MetricDirection

from .contracts import (
    HardExample,
    LearningFeedback,
    MirrorCandidate,
    MirrorRoomError,
    MirrorRoomSpec,
    MirrorScenario,
    ScenarioSplit,
    _digest,
    _non_negative_int,
    _positive_int,
    _sha256,
    _token,
    _tokens,
)
from .engine import (
    CandidateGenerator,
    MirrorRoom,
    _merge_hard_examples,
    _sealed_split_digest,
)
from .evaluation import ComparisonReport, PairedEvaluator
from .sandbox import MirrorSandbox, SandboxExecutor, SandboxUsage
from .observability import MirrorRoomObservatory, get_default_observatory


ADVERSARIAL_ATTEMPTS_REQUIRED = 100
_EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class AdversarialRatchetPolicy:
    """Fixed delivery policy for the adversarial learning campaign."""

    attempts_required: int = ADVERSARIAL_ATTEMPTS_REQUIRED
    challenges_per_attempt: int = 1
    minimum_accepted_upgrades: int = 1
    minimum_weighted_gain: float = 0.0001
    minimum_strict_metric_gain: float = 0.0001
    minimum_strictly_improved_metrics: int = 1
    strict_no_regression: bool = True
    final_minimum_weighted_gain: float = 0.0006
    final_minimum_strict_metric_gain: float = 0.0006
    standard_escalation_exponent: float = 1.25

    def __post_init__(self) -> None:
        attempts = _positive_int("attempts_required", self.attempts_required)
        if attempts != ADVERSARIAL_ATTEMPTS_REQUIRED:
            raise MirrorRoomError(
                "adversarial delivery requires exactly 100 attempts"
            )
        object.__setattr__(self, "attempts_required", attempts)
        object.__setattr__(
            self,
            "challenges_per_attempt",
            _positive_int(
                "challenges_per_attempt",
                self.challenges_per_attempt,
            ),
        )
        minimum = _positive_int(
            "minimum_accepted_upgrades",
            self.minimum_accepted_upgrades,
        )
        if minimum > attempts:
            raise MirrorRoomError(
                "minimum_accepted_upgrades cannot exceed attempts_required"
            )
        object.__setattr__(self, "minimum_accepted_upgrades", minimum)
        gain = float(self.minimum_weighted_gain)
        if not math.isfinite(gain) or gain < 0.0:
            raise MirrorRoomError(
                "minimum_weighted_gain must be finite and non-negative"
            )
        object.__setattr__(self, "minimum_weighted_gain", gain)
        strict_gain = float(self.minimum_strict_metric_gain)
        if not math.isfinite(strict_gain) or strict_gain <= 0.0:
            raise MirrorRoomError(
                "minimum_strict_metric_gain must be finite and positive"
            )
        object.__setattr__(
            self,
            "minimum_strict_metric_gain",
            strict_gain,
        )
        object.__setattr__(
            self,
            "minimum_strictly_improved_metrics",
            _positive_int(
                "minimum_strictly_improved_metrics",
                self.minimum_strictly_improved_metrics,
            ),
        )
        if not isinstance(self.strict_no_regression, bool):
            raise MirrorRoomError("strict_no_regression must be boolean")

        final_weighted = float(self.final_minimum_weighted_gain)
        if not math.isfinite(final_weighted) or final_weighted < 0.0:
            raise MirrorRoomError(
                "final_minimum_weighted_gain must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "final_minimum_weighted_gain",
            max(gain, final_weighted),
        )
        final_strict = float(self.final_minimum_strict_metric_gain)
        if not math.isfinite(final_strict) or final_strict <= 0.0:
            raise MirrorRoomError(
                "final_minimum_strict_metric_gain must be finite and positive"
            )
        object.__setattr__(
            self,
            "final_minimum_strict_metric_gain",
            max(strict_gain, final_strict),
        )
        exponent = float(self.standard_escalation_exponent)
        if not math.isfinite(exponent) or exponent <= 0.0:
            raise MirrorRoomError(
                "standard_escalation_exponent must be finite and positive"
            )
        object.__setattr__(
            self,
            "standard_escalation_exponent",
            exponent,
        )

    def weighted_gain_threshold(self, attempt: int) -> float:
        actual = _positive_int("attempt", attempt)
        if actual > self.attempts_required:
            raise MirrorRoomError("attempt exceeds adversarial policy")
        progress = (actual - 1) / (self.attempts_required - 1)
        shaped = progress ** self.standard_escalation_exponent
        return self.minimum_weighted_gain + (
            self.final_minimum_weighted_gain
            - self.minimum_weighted_gain
        ) * shaped

    def strict_metric_gain_threshold(self, attempt: int) -> float:
        actual = _positive_int("attempt", attempt)
        if actual > self.attempts_required:
            raise MirrorRoomError("attempt exceeds adversarial policy")
        progress = (actual - 1) / (self.attempts_required - 1)
        shaped = progress ** self.standard_escalation_exponent
        return self.minimum_strict_metric_gain + (
            self.final_minimum_strict_metric_gain
            - self.minimum_strict_metric_gain
        ) * shaped

    @property
    def digest(self) -> str:
        return _digest(
            {
                "attempts_required": self.attempts_required,
                "challenges_per_attempt": self.challenges_per_attempt,
                "minimum_accepted_upgrades": (
                    self.minimum_accepted_upgrades
                ),
                "minimum_weighted_gain": self.minimum_weighted_gain,
                "minimum_strict_metric_gain": (
                    self.minimum_strict_metric_gain
                ),
                "minimum_strictly_improved_metrics": (
                    self.minimum_strictly_improved_metrics
                ),
                "strict_no_regression": self.strict_no_regression,
                "final_minimum_weighted_gain": (
                    self.final_minimum_weighted_gain
                ),
                "final_minimum_strict_metric_gain": (
                    self.final_minimum_strict_metric_gain
                ),
                "standard_escalation_exponent": (
                    self.standard_escalation_exponent
                ),
                "cumulative_retention_required": True,
                "delivery_blocked_before_attempt": (
                    ADVERSARIAL_ATTEMPTS_REQUIRED
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class AdversarialChallengeContext:
    """TRAIN-only context exposed to an independent adversary."""

    attempt: int
    baseline: MirrorCandidate
    candidate: MirrorCandidate
    training_scenarios: tuple[MirrorScenario, ...]
    hard_examples: tuple[HardExample, ...]
    prior_attempt_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attempt",
            _positive_int("attempt", self.attempt),
        )
        if not isinstance(self.baseline, MirrorCandidate):
            raise MirrorRoomError("baseline must be MirrorCandidate")
        if not isinstance(self.candidate, MirrorCandidate):
            raise MirrorRoomError("candidate must be MirrorCandidate")
        if (
            self.candidate.parent_candidate_id
            != self.baseline.candidate_id
        ):
            raise MirrorRoomError(
                "adversarial candidate must descend from current baseline"
            )
        if any(
            not isinstance(item, MirrorScenario)
            or item.split is not ScenarioSplit.TRAIN
            for item in self.training_scenarios
        ):
            raise MirrorRoomError(
                "adversary context can expose only TRAIN scenarios"
            )
        if any(
            not isinstance(item, HardExample)
            for item in self.hard_examples
        ):
            raise MirrorRoomError(
                "adversary hard_examples must contain HardExample"
            )
        if self.prior_attempt_digest is not None:
            object.__setattr__(
                self,
                "prior_attempt_digest",
                _sha256(
                    "prior_attempt_digest",
                    self.prior_attempt_digest,
                ),
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "attempt": self.attempt,
                "baseline_digest": self.baseline.digest,
                "candidate_digest": self.candidate.digest,
                "training_scenarios": [
                    item.digest for item in self.training_scenarios
                ],
                "hard_examples": [
                    {
                        "scenario_id": item.scenario_id,
                        "scenario_digest": item.scenario_digest,
                        "difficulty": item.difficulty,
                        "metric_deltas": dict(item.metric_deltas),
                    }
                    for item in self.hard_examples
                ],
                "prior_attempt_digest": self.prior_attempt_digest,
                "contains_validation": False,
                "contains_holdout": False,
            }
        )


@runtime_checkable
class AdversarialScenarioGenerator(Protocol):
    """Generate fresh TRAIN-only attacks against a proposed candidate."""

    adversary_id: str

    def challenge(
        self,
        context: AdversarialChallengeContext,
        *,
        limit: int,
    ) -> Sequence[MirrorScenario]: ...


@dataclass(frozen=True, slots=True)
class FixedAdversarialSuite:
    """Deterministic adversary backed by a pre-built unique challenge corpus."""

    adversary_id: str
    challenges: tuple[MirrorScenario, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "adversary_id",
            _token("adversary_id", self.adversary_id),
        )
        challenges = tuple(self.challenges)
        if not challenges:
            raise MirrorRoomError(
                "fixed adversarial suite requires challenges"
            )
        if any(
            not isinstance(item, MirrorScenario)
            or item.split is not ScenarioSplit.TRAIN
            for item in challenges
        ):
            raise MirrorRoomError(
                "fixed adversarial suite must contain TRAIN scenarios"
            )
        ids = [item.scenario_id for item in challenges]
        if len(ids) != len(set(ids)):
            raise MirrorRoomError(
                "fixed adversarial challenge IDs must be unique"
            )
        payloads = [item.payload_digest for item in challenges]
        if len(payloads) != len(set(payloads)):
            raise MirrorRoomError(
                "fixed adversarial challenge payloads must be unique"
            )
        object.__setattr__(self, "challenges", challenges)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "adversary_id": self.adversary_id,
                "challenges": [
                    item.digest for item in self.challenges
                ],
            }
        )

    def challenge(
        self,
        context: AdversarialChallengeContext,
        *,
        limit: int,
    ) -> Sequence[MirrorScenario]:
        actual_limit = _positive_int("challenge limit", limit)
        start = (context.attempt - 1) * actual_limit
        result = self.challenges[start : start + actual_limit]
        if len(result) != actual_limit:
            raise MirrorRoomError(
                "fixed adversarial suite exhausted before attempt 100"
            )
        return result


@dataclass(frozen=True, slots=True)
class AdversarialStandard:
    """Monotonic validation standard after one ratchet attempt."""

    attempt: int
    accepted_upgrades: int
    baseline_candidate_id: str
    baseline_candidate_digest: str
    metric_floors: Mapping[str, float]
    predecessor_digest: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attempt",
            _non_negative_int("attempt", self.attempt),
        )
        object.__setattr__(
            self,
            "accepted_upgrades",
            _non_negative_int(
                "accepted_upgrades",
                self.accepted_upgrades,
            ),
        )
        object.__setattr__(
            self,
            "baseline_candidate_id",
            _token(
                "baseline_candidate_id",
                self.baseline_candidate_id,
            ),
        )
        object.__setattr__(
            self,
            "baseline_candidate_digest",
            _sha256(
                "baseline_candidate_digest",
                self.baseline_candidate_digest,
            ),
        )
        if not isinstance(self.metric_floors, Mapping):
            raise MirrorRoomError("metric_floors must be a mapping")
        floors: dict[str, float] = {}
        for key, value in self.metric_floors.items():
            metric_id = _token("metric_id", key)
            number = float(value)
            if not math.isfinite(number):
                raise MirrorRoomError("metric floor must be finite")
            floors[metric_id] = number
        if not floors:
            raise MirrorRoomError("metric_floors must be non-empty")
        object.__setattr__(
            self,
            "metric_floors",
            MappingProxyType(dict(sorted(floors.items()))),
        )
        if self.predecessor_digest is not None:
            object.__setattr__(
                self,
                "predecessor_digest",
                _sha256(
                    "predecessor_digest",
                    self.predecessor_digest,
                ),
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "attempt": self.attempt,
                "accepted_upgrades": self.accepted_upgrades,
                "baseline_candidate_id": self.baseline_candidate_id,
                "baseline_candidate_digest": (
                    self.baseline_candidate_digest
                ),
                "metric_floors": dict(self.metric_floors),
                "predecessor_digest": self.predecessor_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class AdversarialAttemptReceipt:
    """Auditable evidence for one attack -> evaluate -> ratchet transition."""

    attempt: int
    adversary_id: str
    baseline_before: MirrorCandidate
    candidate: MirrorCandidate
    challenge_ids: tuple[str, ...]
    challenge_digests: tuple[str, ...]
    retention_scenario_digests: tuple[str, ...]
    required_weighted_gain: float
    required_strict_metric_gain: float
    challenge_report: ComparisonReport
    validation_report: ComparisonReport
    accepted: bool
    rejection_reasons: tuple[str, ...]
    baseline_after: MirrorCandidate
    standard_before_digest: str
    standard_after: AdversarialStandard
    production_authority: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attempt",
            _positive_int("attempt", self.attempt),
        )
        object.__setattr__(
            self,
            "adversary_id",
            _token("adversary_id", self.adversary_id),
        )
        if not isinstance(self.baseline_before, MirrorCandidate):
            raise MirrorRoomError(
                "baseline_before must be MirrorCandidate"
            )
        if not isinstance(self.candidate, MirrorCandidate):
            raise MirrorRoomError("candidate must be MirrorCandidate")
        if not isinstance(self.baseline_after, MirrorCandidate):
            raise MirrorRoomError(
                "baseline_after must be MirrorCandidate"
            )
        if (
            self.candidate.parent_candidate_id
            != self.baseline_before.candidate_id
        ):
            raise MirrorRoomError(
                "attempt candidate lineage does not match ratchet baseline"
            )
        challenge_ids = _tokens(
            "challenge_id",
            self.challenge_ids,
            allow_empty=False,
        )
        object.__setattr__(self, "challenge_ids", challenge_ids)
        challenge_digests = tuple(
            _sha256("challenge_digest", item)
            for item in self.challenge_digests
        )
        if len(challenge_digests) != len(challenge_ids):
            raise MirrorRoomError(
                "challenge IDs and digests must have equal cardinality"
            )
        object.__setattr__(
            self,
            "challenge_digests",
            challenge_digests,
        )
        retention = tuple(
            sorted(
                {
                    _sha256("retention_scenario_digest", item)
                    for item in self.retention_scenario_digests
                }
            )
        )
        if not retention:
            raise MirrorRoomError(
                "adversarial attempt requires cumulative retention evidence"
            )
        if not set(challenge_digests).issubset(set(retention)):
            raise MirrorRoomError(
                "fresh adversarial challenges are missing from retention suite"
            )
        object.__setattr__(
            self,
            "retention_scenario_digests",
            retention,
        )
        weighted = float(self.required_weighted_gain)
        strict = float(self.required_strict_metric_gain)
        if not math.isfinite(weighted) or weighted < 0.0:
            raise MirrorRoomError(
                "required_weighted_gain must be finite and non-negative"
            )
        if not math.isfinite(strict) or strict <= 0.0:
            raise MirrorRoomError(
                "required_strict_metric_gain must be finite and positive"
            )
        object.__setattr__(self, "required_weighted_gain", weighted)
        object.__setattr__(self, "required_strict_metric_gain", strict)
        if self.challenge_report.split is not ScenarioSplit.TRAIN:
            raise MirrorRoomError(
                "adversarial challenge report must be TRAIN evidence"
            )
        if self.validation_report.split is not ScenarioSplit.VALIDATION:
            raise MirrorRoomError(
                "ratchet validation report must be VALIDATION evidence"
            )
        observed_retention = tuple(
            sorted(
                item.scenario_digest
                for item in self.challenge_report.scenario_comparisons
            )
        )
        if observed_retention != self.retention_scenario_digests:
            raise MirrorRoomError(
                "retention suite does not match adversarial challenge report"
            )
        for report in (
            self.challenge_report,
            self.validation_report,
        ):
            if (
                report.baseline_candidate_digest
                != self.baseline_before.digest
            ):
                raise MirrorRoomError(
                    "attempt report baseline does not match ratchet baseline"
                )
            if report.candidate_digest != self.candidate.digest:
                raise MirrorRoomError(
                    "attempt report candidate does not match proposal"
                )
        if not isinstance(self.accepted, bool):
            raise MirrorRoomError("accepted must be boolean")
        reasons = _tokens(
            "rejection_reason",
            self.rejection_reasons,
        )
        object.__setattr__(self, "rejection_reasons", reasons)
        if self.accepted:
            if reasons:
                raise MirrorRoomError(
                    "accepted attempt cannot carry rejection reasons"
                )
            if not self.challenge_report.passed:
                raise MirrorRoomError(
                    "accepted attempt must pass adversarial challenges"
                )
            if not self.validation_report.passed:
                raise MirrorRoomError(
                    "accepted attempt must pass validation"
                )
            if self.baseline_after.digest != self.candidate.digest:
                raise MirrorRoomError(
                    "accepted upgrade must become next baseline"
                )
            for label, report in (
                ("adversarial", self.challenge_report),
                ("validation", self.validation_report),
            ):
                if (
                    report.weighted_utility_delta
                    <= self.required_weighted_gain
                ):
                    raise MirrorRoomError(
                        f"accepted attempt misses progressive {label} gain bar"
                    )
                improved = sum(
                    int(
                        metric.oriented_delta
                        >= self.required_strict_metric_gain - _EPSILON
                    )
                    for metric in report.metric_comparisons
                )
                if improved <= 0:
                    raise MirrorRoomError(
                        f"accepted attempt misses progressive {label} strict bar"
                    )
        else:
            if not reasons:
                raise MirrorRoomError(
                    "rejected attempt requires rejection reasons"
                )
            if (
                self.baseline_after.digest
                != self.baseline_before.digest
            ):
                raise MirrorRoomError(
                    "rejected attempt cannot mutate ratchet baseline"
                )
        object.__setattr__(
            self,
            "standard_before_digest",
            _sha256(
                "standard_before_digest",
                self.standard_before_digest,
            ),
        )
        if not isinstance(self.standard_after, AdversarialStandard):
            raise MirrorRoomError(
                "standard_after must be AdversarialStandard"
            )
        if self.standard_after.attempt != self.attempt:
            raise MirrorRoomError(
                "standard attempt does not match receipt"
            )
        if (
            self.standard_after.predecessor_digest
            != self.standard_before_digest
        ):
            raise MirrorRoomError(
                "adversarial standard hash chain is broken"
            )
        if (
            self.standard_after.baseline_candidate_digest
            != self.baseline_after.digest
        ):
            raise MirrorRoomError(
                "standard baseline does not match ratchet baseline"
            )
        if self.production_authority is not False:
            raise MirrorRoomError(
                "adversarial attempt cannot have production authority"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "attempt": self.attempt,
                "adversary_id": self.adversary_id,
                "baseline_before": self.baseline_before.digest,
                "candidate": self.candidate.digest,
                "challenge_ids": list(self.challenge_ids),
                "challenge_digests": list(self.challenge_digests),
                "retention_scenario_digests": list(
                    self.retention_scenario_digests
                ),
                "required_weighted_gain": self.required_weighted_gain,
                "required_strict_metric_gain": (
                    self.required_strict_metric_gain
                ),
                "challenge_report": self.challenge_report.digest,
                "validation_report": self.validation_report.digest,
                "accepted": self.accepted,
                "rejection_reasons": list(self.rejection_reasons),
                "baseline_after": self.baseline_after.digest,
                "standard_before_digest": (
                    self.standard_before_digest
                ),
                "standard_after": self.standard_after.digest,
                "production_authority": False,
            }
        )


@dataclass(frozen=True, slots=True)
class AdversarialCampaignReceipt:
    """Result of a partial or complete 100-attempt ratchet campaign."""

    run_id: str
    spec_digest: str
    manifest_digest: str
    policy: AdversarialRatchetPolicy
    generator_id: str
    executor_id: str
    adversary_id: str
    original_baseline: MirrorCandidate
    final_baseline: MirrorCandidate
    attempts: tuple[AdversarialAttemptReceipt, ...]
    gauntlet_report: ComparisonReport | None
    holdout_report: ComparisonReport | None
    sealed_holdout_digest: str
    usage: SandboxUsage
    delivery_ready: bool
    production_authority: bool = False
    direct_self_modify: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.policy, AdversarialRatchetPolicy):
            raise MirrorRoomError(
                "policy must be AdversarialRatchetPolicy"
            )
        for field in (
            "generator_id",
            "executor_id",
            "adversary_id",
        ):
            object.__setattr__(
                self,
                field,
                _token(field, getattr(self, field)),
            )
        if len(
            {
                self.generator_id,
                self.executor_id,
                self.adversary_id,
            }
        ) != 3:
            raise MirrorRoomError(
                "generator, evaluator, and adversary must be independent"
            )
        if not isinstance(self.original_baseline, MirrorCandidate):
            raise MirrorRoomError(
                "original_baseline must be MirrorCandidate"
            )
        if not isinstance(self.final_baseline, MirrorCandidate):
            raise MirrorRoomError(
                "final_baseline must be MirrorCandidate"
            )
        attempts = tuple(self.attempts)
        if len(attempts) > self.policy.attempts_required:
            raise MirrorRoomError(
                "campaign exceeds 100-attempt delivery policy"
            )
        if any(
            not isinstance(item, AdversarialAttemptReceipt)
            for item in attempts
        ):
            raise MirrorRoomError(
                "attempts must contain AdversarialAttemptReceipt"
            )
        object.__setattr__(self, "attempts", attempts)

        current = self.original_baseline
        accepted = 0
        prior_retention: set[str] = set()
        prior_weighted_bar = -1.0
        prior_strict_bar = -1.0
        for index, item in enumerate(attempts, start=1):
            if item.attempt != index:
                raise MirrorRoomError(
                    "adversarial attempts must be contiguous"
                )
            if item.baseline_before.digest != current.digest:
                raise MirrorRoomError(
                    "adversarial baseline ratchet chain is broken"
                )
            accepted += int(item.accepted)
            if item.standard_after.accepted_upgrades != accepted:
                raise MirrorRoomError(
                    "accepted upgrade counter drifted"
                )
            expected_weighted = self.policy.weighted_gain_threshold(index)
            expected_strict = self.policy.strict_metric_gain_threshold(index)
            if abs(item.required_weighted_gain - expected_weighted) > _EPSILON:
                raise MirrorRoomError(
                    "attempt weighted gain bar drifted from policy"
                )
            if (
                abs(item.required_strict_metric_gain - expected_strict)
                > _EPSILON
            ):
                raise MirrorRoomError(
                    "attempt strict metric bar drifted from policy"
                )
            if item.required_weighted_gain + _EPSILON < prior_weighted_bar:
                raise MirrorRoomError(
                    "adversarial weighted standard decreased over time"
                )
            if item.required_strict_metric_gain + _EPSILON < prior_strict_bar:
                raise MirrorRoomError(
                    "adversarial strict standard decreased over time"
                )
            retention = set(item.retention_scenario_digests)
            if prior_retention:
                if not prior_retention.issubset(retention):
                    raise MirrorRoomError(
                        "adversarial retention suite forgot prior attacks"
                    )
                newly_retained = retention - prior_retention
                if newly_retained != set(item.challenge_digests):
                    raise MirrorRoomError(
                        "retention suite must add exactly the fresh challenges"
                    )
            elif not set(item.challenge_digests).issubset(retention):
                raise MirrorRoomError(
                    "initial retention suite omits fresh challenges"
                )
            prior_retention = retention
            prior_weighted_bar = item.required_weighted_gain
            prior_strict_bar = item.required_strict_metric_gain
            current = item.baseline_after
        if current.digest != self.final_baseline.digest:
            raise MirrorRoomError(
                "final baseline does not match ratchet chain"
            )

        complete = len(attempts) == self.policy.attempts_required
        if not complete and self.gauntlet_report is not None:
            raise MirrorRoomError(
                "cumulative gauntlet cannot run before attempt 100"
            )
        if not complete and self.holdout_report is not None:
            raise MirrorRoomError(
                "sealed holdout cannot be opened before attempt 100"
            )
        if self.gauntlet_report is not None:
            if self.gauntlet_report.split is not ScenarioSplit.TRAIN:
                raise MirrorRoomError(
                    "cumulative gauntlet must use TRAIN evidence"
                )
            if (
                self.gauntlet_report.baseline_candidate_digest
                != self.original_baseline.digest
            ):
                raise MirrorRoomError(
                    "cumulative gauntlet must use original baseline"
                )
            if (
                self.gauntlet_report.candidate_digest
                != self.final_baseline.digest
            ):
                raise MirrorRoomError(
                    "cumulative gauntlet must test final ratchet baseline"
                )
        if self.holdout_report is not None:
            if self.holdout_report.split is not ScenarioSplit.HOLDOUT:
                raise MirrorRoomError(
                    "campaign holdout report must use HOLDOUT split"
                )
            if (
                self.holdout_report.baseline_candidate_digest
                != self.original_baseline.digest
            ):
                raise MirrorRoomError(
                    "delivery holdout must use original baseline"
                )
            if (
                self.holdout_report.candidate_digest
                != self.final_baseline.digest
            ):
                raise MirrorRoomError(
                    "delivery holdout must test final ratchet baseline"
                )

        expected_delivery = (
            complete
            and accepted >= self.policy.minimum_accepted_upgrades
            and self.final_baseline.digest
            != self.original_baseline.digest
            and self.gauntlet_report is not None
            and self.gauntlet_report.passed
            and self.holdout_report is not None
            and self.holdout_report.passed
        )
        if self.delivery_ready != expected_delivery:
            raise MirrorRoomError(
                "delivery_ready does not match 100-attempt evidence"
            )
        if self.production_authority is not False:
            raise MirrorRoomError(
                "adversarial campaign cannot have production authority"
            )
        if self.direct_self_modify is not False:
            raise MirrorRoomError(
                "adversarial campaign cannot directly self-modify"
            )

    @property
    def completed_attempts(self) -> int:
        return len(self.attempts)

    @property
    def accepted_upgrades(self) -> int:
        return sum(int(item.accepted) for item in self.attempts)

    @property
    def final_standard(self) -> AdversarialStandard | None:
        if not self.attempts:
            return None
        return self.attempts[-1].standard_after

    @property
    def digest(self) -> str:
        return _digest(
            {
                "run_id": self.run_id,
                "spec_digest": self.spec_digest,
                "manifest_digest": self.manifest_digest,
                "policy_digest": self.policy.digest,
                "generator_id": self.generator_id,
                "executor_id": self.executor_id,
                "adversary_id": self.adversary_id,
                "original_baseline": self.original_baseline.digest,
                "final_baseline": self.final_baseline.digest,
                "attempts": [item.digest for item in self.attempts],
                "gauntlet_report": (
                    None
                    if self.gauntlet_report is None
                    else self.gauntlet_report.digest
                ),
                "holdout_report": (
                    None
                    if self.holdout_report is None
                    else self.holdout_report.digest
                ),
                "sealed_holdout_digest": self.sealed_holdout_digest,
                "usage": {
                    "episodes": self.usage.episodes,
                    "steps": self.usage.steps,
                    "tokens": self.usage.tokens,
                    "cost_units": self.usage.cost_units,
                },
                "delivery_ready": self.delivery_ready,
                "production_authority": False,
                "direct_self_modify": False,
            }
        )


@dataclass(frozen=True, slots=True)
class AdversarialDeliveryEvidence:
    """Evidence-only handoff after the complete 100-attempt campaign."""

    campaign_digest: str
    original_baseline_digest: str
    final_candidate_id: str
    final_candidate_digest: str
    final_candidate_version: str
    attempts_completed: int
    accepted_upgrades: int
    final_standard_digest: str
    gauntlet_report_digest: str
    holdout_report_digest: str
    verifier_id: str
    evaluation_refs: tuple[str, ...]
    verified_at: int
    rollback_candidate_id: str
    rollback_candidate_digest: str
    production_authority: bool = False
    direct_self_modify: bool = False

    def __post_init__(self) -> None:
        for field in (
            "campaign_digest",
            "original_baseline_digest",
            "final_candidate_digest",
            "final_standard_digest",
            "gauntlet_report_digest",
            "holdout_report_digest",
            "rollback_candidate_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(field, getattr(self, field)),
            )
        for field in (
            "final_candidate_id",
            "final_candidate_version",
            "verifier_id",
            "rollback_candidate_id",
        ):
            object.__setattr__(
                self,
                field,
                _token(field, getattr(self, field)),
            )
        attempts = _positive_int(
            "attempts_completed",
            self.attempts_completed,
        )
        if attempts != ADVERSARIAL_ATTEMPTS_REQUIRED:
            raise MirrorRoomError(
                "delivery evidence requires all 100 attempts"
            )
        object.__setattr__(self, "attempts_completed", attempts)
        object.__setattr__(
            self,
            "accepted_upgrades",
            _positive_int(
                "accepted_upgrades",
                self.accepted_upgrades,
            ),
        )
        refs = _tokens(
            "evaluation_ref",
            self.evaluation_refs,
            allow_empty=False,
        )
        if len(refs) < 2:
            raise MirrorRoomError(
                "adversarial delivery requires two evaluation channels"
            )
        object.__setattr__(self, "evaluation_refs", refs)
        object.__setattr__(
            self,
            "verified_at",
            _non_negative_int("verified_at", self.verified_at),
        )
        if self.production_authority is not False:
            raise MirrorRoomError(
                "delivery evidence cannot grant production authority"
            )
        if self.direct_self_modify is not False:
            raise MirrorRoomError(
                "delivery evidence cannot directly self-modify"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "campaign_digest": self.campaign_digest,
                "original_baseline_digest": (
                    self.original_baseline_digest
                ),
                "final_candidate_id": self.final_candidate_id,
                "final_candidate_digest": self.final_candidate_digest,
                "final_candidate_version": self.final_candidate_version,
                "attempts_completed": self.attempts_completed,
                "accepted_upgrades": self.accepted_upgrades,
                "final_standard_digest": self.final_standard_digest,
                "gauntlet_report_digest": self.gauntlet_report_digest,
                "holdout_report_digest": self.holdout_report_digest,
                "verifier_id": self.verifier_id,
                "evaluation_refs": list(self.evaluation_refs),
                "verified_at": self.verified_at,
                "rollback_candidate_id": self.rollback_candidate_id,
                "rollback_candidate_digest": (
                    self.rollback_candidate_digest
                ),
                "production_authority": False,
                "direct_self_modify": False,
            }
        )

    def evidence_ref(self) -> EvidenceRef:
        return EvidenceRef(
            source=(
                "mirror-room:adversarial-delivery:"
                f"{self.final_candidate_id}"
            ),
            digest=self.digest,
            category="mirror_room_adversarial_delivery",
        )


def _report_metric_floors(
    report: ComparisonReport,
    *,
    candidate: bool,
) -> dict[str, float]:
    return {
        item.metric_id: (
            item.candidate_mean if candidate else item.baseline_mean
        )
        for item in report.metric_comparisons
    }


def _no_regression_reasons(
    report: ComparisonReport,
    *,
    label: str,
) -> list[str]:
    reasons: list[str] = []
    for metric in report.metric_comparisons:
        if metric.oriented_delta < -_EPSILON:
            reasons.append(
                f"{label}-regression:{metric.metric_id}"
            )
    return reasons


def _strict_improvement_reasons(
    report: ComparisonReport,
    *,
    minimum_gain: float,
    minimum_count: int,
    label: str,
) -> list[str]:
    improved = sum(
        int(
            metric.oriented_delta
            >= minimum_gain - _EPSILON
        )
        for metric in report.metric_comparisons
    )
    if improved < minimum_count:
        return [
            f"{label}-insufficient-strict-metric-lift:"
            f"{improved}/{minimum_count}"
        ]
    return []


def _assert_standard_continuity(
    standard: AdversarialStandard,
    report: ComparisonReport,
) -> None:
    observed = _report_metric_floors(report, candidate=False)
    if set(observed) != set(standard.metric_floors):
        raise MirrorRoomError(
            "validation metric set drifted between ratchet attempts"
        )
    for metric_id, expected in standard.metric_floors.items():
        if abs(observed[metric_id] - expected) > _EPSILON:
            raise MirrorRoomError(
                "validation baseline drifted from ratcheted standard"
            )


def _assert_floor_monotonicity(
    standard: AdversarialStandard,
    report: ComparisonReport,
) -> None:
    for metric in report.metric_comparisons:
        prior = standard.metric_floors[metric.metric_id]
        current = metric.candidate_mean
        if metric.direction is MetricDirection.MAXIMIZE:
            if current + _EPSILON < prior:
                raise MirrorRoomError(
                    "accepted validation standard regressed"
                )
        elif current - _EPSILON > prior:
            raise MirrorRoomError(
                "accepted validation standard regressed"
            )


class AdversarialMirrorRoom:
    """Execute the fixed 100-attempt adversarial baseline ratchet."""

    def __init__(
        self,
        spec: MirrorRoomSpec,
        executor: SandboxExecutor,
        adversary: AdversarialScenarioGenerator,
        *,
        policy: AdversarialRatchetPolicy | None = None,
        observatory: MirrorRoomObservatory | None = None,
    ) -> None:
        if not isinstance(spec, MirrorRoomSpec):
            raise TypeError("spec must be MirrorRoomSpec")
        if not isinstance(executor, SandboxExecutor):
            raise TypeError("executor must satisfy SandboxExecutor")
        if not isinstance(adversary, AdversarialScenarioGenerator):
            raise TypeError(
                "adversary must satisfy AdversarialScenarioGenerator"
            )
        adversary_id = getattr(adversary, "adversary_id", None)
        if not isinstance(adversary_id, str) or not adversary_id.strip():
            raise MirrorRoomError(
                "adversary requires stable adversary_id"
            )
        self.spec = spec
        self.executor = executor
        self.adversary = adversary
        self.policy = policy or AdversarialRatchetPolicy()
        self.observatory = observatory or get_default_observatory()
        if (
            self.spec.budget.max_generations
            < self.policy.attempts_required
        ):
            raise MirrorRoomError(
                "Mirror Room generation budget cannot reach 100 attempts"
            )

    def _observe(
        self,
        event: str,
        *args: object,
        **kwargs: object,
    ) -> None:
        """Publish read-only evidence without granting observer authority.

        Observatory failures are intentionally isolated from learning. A broken
        dashboard, API projection, or custom observer cannot reject, accept,
        mutate, or abort a valid adversarial campaign.
        """

        try:
            callback = getattr(self.observatory, event)
            callback(*args, **kwargs)
        except Exception:
            return

    def _validate_full_campaign_capacity(
        self,
        *,
        train_count: int,
        validation_count: int,
        holdout_count: int,
    ) -> None:
        attempts = self.policy.attempts_required
        cumulative_attempt_scenarios = (
            attempts * (train_count + validation_count)
            + (
                self.policy.challenges_per_attempt
                * attempts
                * (attempts + 1)
                // 2
            )
        )
        cumulative_gauntlet = 2 * (
            train_count
            + (
                attempts
                * self.policy.challenges_per_attempt
            )
        )
        episode_slots = (
            2 * cumulative_attempt_scenarios
            + cumulative_gauntlet
            + (2 * holdout_count)
        )
        budget = self.spec.budget
        policy = self.spec.sandbox_policy
        if budget.max_episodes < episode_slots:
            raise MirrorRoomError(
                "Mirror Room episode budget cannot complete 100 attempts"
            )
        if (
            budget.max_total_steps
            < episode_slots * policy.max_steps_per_episode
        ):
            raise MirrorRoomError(
                "Mirror Room step budget cannot guarantee 100 attempts"
            )
        if (
            budget.max_total_tokens
            < episode_slots * policy.max_tokens_per_episode
        ):
            raise MirrorRoomError(
                "Mirror Room token budget cannot guarantee 100 attempts"
            )
        if (
            budget.max_total_cost_units + _EPSILON
            < episode_slots * policy.max_cost_units_per_episode
        ):
            raise MirrorRoomError(
                "Mirror Room cost budget cannot guarantee 100 attempts"
            )

    def _validate_challenges(
        self,
        challenges: Sequence[MirrorScenario],
        *,
        seen_ids: set[str],
        seen_payloads: set[str],
    ) -> tuple[MirrorScenario, ...]:
        result = tuple(challenges)
        if len(result) != self.policy.challenges_per_attempt:
            raise MirrorRoomError(
                "adversary must return exact challenges_per_attempt"
            )
        allowed = set(
            self.spec.manifest.eligibility.allowed_data_classes
        )
        local_ids: set[str] = set()
        local_payloads: set[str] = set()
        for item in result:
            if not isinstance(item, MirrorScenario):
                raise MirrorRoomError(
                    "adversary returned invalid challenge"
                )
            if item.split is not ScenarioSplit.TRAIN:
                raise MirrorRoomError(
                    "adversary may emit only TRAIN challenges"
                )
            if item.data_class not in allowed:
                raise MirrorRoomError(
                    "adversarial challenge exceeds data eligibility"
                )
            if item.scenario_id in seen_ids or item.scenario_id in local_ids:
                raise MirrorRoomError(
                    "adversarial challenge identity was reused"
                )
            if (
                item.payload_digest in seen_payloads
                or item.payload_digest in local_payloads
            ):
                raise MirrorRoomError(
                    "adversarial challenge payload was reused"
                )
            local_ids.add(item.scenario_id)
            local_payloads.add(item.payload_digest)
        return result

    def run(
        self,
        *,
        run_id: str,
        generator: CandidateGenerator,
        scenarios: Sequence[MirrorScenario],
        attempts: int | None = None,
    ) -> AdversarialCampaignReceipt:
        if not isinstance(run_id, str) or not run_id.strip():
            raise MirrorRoomError("run_id must be non-empty")
        target = (
            self.policy.attempts_required
            if attempts is None
            else attempts
        )
        if (
            isinstance(target, bool)
            or not isinstance(target, int)
            or target <= 0
            or target > self.policy.attempts_required
        ):
            raise MirrorRoomError(
                "attempts must be within 1..100"
            )

        generator_id = MirrorRoom._generator_identity(generator)
        executor_id = self.executor.executor_id
        adversary_id = self.adversary.adversary_id
        if len({generator_id, executor_id, adversary_id}) != 3:
            raise MirrorRoomError(
                "generator, evaluator, and adversary must be independent"
            )

        base_room = MirrorRoom(self.spec, self.executor)
        train, validation, holdout = base_room._partition(scenarios)
        self._validate_full_campaign_capacity(
            train_count=len(train),
            validation_count=len(validation),
            holdout_count=len(holdout),
        )

        sandbox = MirrorSandbox(self.spec, self.executor)
        evaluator = PairedEvaluator(self.spec, sandbox)
        original_baseline = self.spec.production_baseline
        baseline = original_baseline
        self._observe(
            "begin",
            run_id=run_id,
            baseline=original_baseline,
        )
        seen_candidate_ids = {baseline.candidate_id}
        seen_candidate_digests = {baseline.digest}
        seen_behavior_digests = {baseline.behavior_digest}
        seen_challenge_ids = {
            item.scenario_id
            for item in (*train, *validation, *holdout)
        }
        seen_challenge_payloads = {
            item.payload_digest
            for item in (*train, *validation, *holdout)
        }
        hard_examples: tuple[HardExample, ...] = ()
        prior_candidate_id: str | None = None
        prior_attempt_digest: str | None = None
        standard: AdversarialStandard | None = None
        accepted_upgrades = 0
        receipts: list[AdversarialAttemptReceipt] = []
        adversarial_corpus: list[MirrorScenario] = []

        for attempt in range(1, target + 1):
            required_weighted_gain = (
                self.policy.weighted_gain_threshold(attempt)
            )
            required_strict_metric_gain = (
                self.policy.strict_metric_gain_threshold(attempt)
            )
            feedback = LearningFeedback(
                generation=attempt,
                champion=baseline,
                training_scenarios=train,
                hard_examples=hard_examples,
                prior_candidate_id=prior_candidate_id,
            )
            proposed = generator.propose(feedback, limit=1)
            candidates = MirrorRoom._validate_candidates(
                proposed,
                generator_id=generator_id,
                champion=baseline,
                seen_ids=seen_candidate_ids,
                seen_digests=seen_candidate_digests,
                seen_behavior_digests=seen_behavior_digests,
                limit=1,
            )
            if len(candidates) != 1:
                raise MirrorRoomError(
                    "each adversarial attempt requires one candidate"
                )
            candidate = candidates[0]
            seen_candidate_ids.add(candidate.candidate_id)
            seen_candidate_digests.add(candidate.digest)
            seen_behavior_digests.add(candidate.behavior_digest)

            context = AdversarialChallengeContext(
                attempt=attempt,
                baseline=baseline,
                candidate=candidate,
                training_scenarios=train,
                hard_examples=hard_examples,
                prior_attempt_digest=prior_attempt_digest,
            )
            fresh = self._validate_challenges(
                self.adversary.challenge(
                    context,
                    limit=self.policy.challenges_per_attempt,
                ),
                seen_ids=seen_challenge_ids,
                seen_payloads=seen_challenge_payloads,
            )
            for item in fresh:
                seen_challenge_ids.add(item.scenario_id)
                seen_challenge_payloads.add(item.payload_digest)
                adversarial_corpus.append(item)

            challenge_report = evaluator.compare(
                run_id=f"{run_id}:attack:{attempt}",
                baseline=baseline,
                candidate=candidate,
                scenarios=(
                    *train,
                    *tuple(adversarial_corpus),
                ),
                split=ScenarioSplit.TRAIN,
                enforce_gate=True,
                comparison_family_size=self.policy.attempts_required,
            )
            validation_report = evaluator.compare(
                run_id=f"{run_id}:ratchet-validation",
                baseline=baseline,
                candidate=candidate,
                scenarios=validation,
                split=ScenarioSplit.VALIDATION,
                enforce_gate=True,
                comparison_family_size=self.policy.attempts_required,
            )

            if standard is None:
                standard = AdversarialStandard(
                    attempt=0,
                    accepted_upgrades=0,
                    baseline_candidate_id=baseline.candidate_id,
                    baseline_candidate_digest=baseline.digest,
                    metric_floors=_report_metric_floors(
                        validation_report,
                        candidate=False,
                    ),
                    predecessor_digest=None,
                )
            else:
                _assert_standard_continuity(
                    standard,
                    validation_report,
                )

            rejection_reasons: list[str] = []
            if not challenge_report.passed:
                rejection_reasons.append("adversarial-challenge-gate")
            if not validation_report.passed:
                rejection_reasons.append("validation-gate")
            if (
                challenge_report.weighted_utility_delta
                <= required_weighted_gain
            ):
                rejection_reasons.append(
                    "adversarial-weighted-gain"
                )
            if (
                validation_report.weighted_utility_delta
                <= required_weighted_gain
            ):
                rejection_reasons.append(
                    "validation-weighted-gain"
                )
            rejection_reasons.extend(
                _strict_improvement_reasons(
                    challenge_report,
                    minimum_gain=required_strict_metric_gain,
                    minimum_count=(
                        self.policy.minimum_strictly_improved_metrics
                    ),
                    label="adversarial",
                )
            )
            rejection_reasons.extend(
                _strict_improvement_reasons(
                    validation_report,
                    minimum_gain=required_strict_metric_gain,
                    minimum_count=(
                        self.policy.minimum_strictly_improved_metrics
                    ),
                    label="validation",
                )
            )
            if self.policy.strict_no_regression:
                rejection_reasons.extend(
                    _no_regression_reasons(
                        challenge_report,
                        label="adversarial",
                    )
                )
                rejection_reasons.extend(
                    _no_regression_reasons(
                        validation_report,
                        label="validation",
                    )
                )

            accepted = not rejection_reasons
            standard_before = standard
            if accepted:
                _assert_floor_monotonicity(
                    standard_before,
                    validation_report,
                )
                baseline_after = candidate
                accepted_upgrades += 1
                next_floors = _report_metric_floors(
                    validation_report,
                    candidate=True,
                )
            else:
                baseline_after = baseline
                next_floors = dict(
                    standard_before.metric_floors
                )

            standard_after = AdversarialStandard(
                attempt=attempt,
                accepted_upgrades=accepted_upgrades,
                baseline_candidate_id=baseline_after.candidate_id,
                baseline_candidate_digest=baseline_after.digest,
                metric_floors=next_floors,
                predecessor_digest=standard_before.digest,
            )
            receipt = AdversarialAttemptReceipt(
                attempt=attempt,
                adversary_id=adversary_id,
                baseline_before=baseline,
                candidate=candidate,
                challenge_ids=tuple(
                    item.scenario_id for item in fresh
                ),
                challenge_digests=tuple(
                    item.digest for item in fresh
                ),
                retention_scenario_digests=tuple(
                    sorted(
                        item.scenario_digest
                        for item in challenge_report.scenario_comparisons
                    )
                ),
                required_weighted_gain=required_weighted_gain,
                required_strict_metric_gain=(
                    required_strict_metric_gain
                ),
                challenge_report=challenge_report,
                validation_report=validation_report,
                accepted=accepted,
                rejection_reasons=tuple(
                    sorted(set(rejection_reasons))
                ),
                baseline_after=baseline_after,
                standard_before_digest=standard_before.digest,
                standard_after=standard_after,
            )
            receipts.append(receipt)
            self._observe("record_attempt", receipt)

            new_hard = challenge_report.hard_examples(
                limit=self.spec.hard_example_limit
            )
            hard_examples = _merge_hard_examples(
                hard_examples,
                new_hard,
                limit=self.spec.hard_example_limit,
            )
            prior_candidate_id = candidate.candidate_id
            prior_attempt_digest = receipt.digest
            standard = standard_after
            baseline = baseline_after

        gauntlet_report: ComparisonReport | None = None
        holdout_report: ComparisonReport | None = None
        complete = target == self.policy.attempts_required
        if complete and baseline.digest != original_baseline.digest:
            gauntlet_report = evaluator.compare(
                run_id=f"{run_id}:delivery-gauntlet",
                baseline=original_baseline,
                candidate=baseline,
                scenarios=(
                    *train,
                    *tuple(adversarial_corpus),
                ),
                split=ScenarioSplit.TRAIN,
                enforce_gate=True,
                comparison_family_size=1,
            )
            holdout_report = evaluator.compare(
                run_id=f"{run_id}:delivery-holdout",
                baseline=original_baseline,
                candidate=baseline,
                scenarios=holdout,
                split=ScenarioSplit.HOLDOUT,
                enforce_gate=True,
            )

        delivery_ready = (
            complete
            and accepted_upgrades
            >= self.policy.minimum_accepted_upgrades
            and baseline.digest != original_baseline.digest
            and gauntlet_report is not None
            and gauntlet_report.passed
            and holdout_report is not None
            and holdout_report.passed
        )
        campaign = AdversarialCampaignReceipt(
            run_id=run_id,
            spec_digest=self.spec.digest,
            manifest_digest=self.spec.manifest.manifest_digest,
            policy=self.policy,
            generator_id=generator_id,
            executor_id=executor_id,
            adversary_id=adversary_id,
            original_baseline=original_baseline,
            final_baseline=baseline,
            attempts=tuple(receipts),
            gauntlet_report=gauntlet_report,
            holdout_report=holdout_report,
            sealed_holdout_digest=_sealed_split_digest(holdout),
            usage=sandbox.usage,
            delivery_ready=delivery_ready,
        )
        self._observe("finish", campaign)
        return campaign


def qualify_adversarial_delivery(
    campaign: AdversarialCampaignReceipt,
    *,
    verifier_id: str,
    evaluation_refs: tuple[str, ...],
    verified_at: int,
) -> AdversarialDeliveryEvidence:
    """Create delivery evidence only after the complete 100-attempt ratchet."""

    if not isinstance(campaign, AdversarialCampaignReceipt):
        raise TypeError(
            "campaign must be AdversarialCampaignReceipt"
        )
    if not campaign.delivery_ready:
        raise MirrorRoomError(
            "adversarial campaign is not ready for delivery"
        )
    if (
        campaign.completed_attempts
        != ADVERSARIAL_ATTEMPTS_REQUIRED
    ):
        raise MirrorRoomError(
            "delivery is blocked until all 100 attempts complete"
        )
    if campaign.gauntlet_report is None:
        raise MirrorRoomError(
            "delivery requires cumulative adversarial gauntlet evidence"
        )
    if not campaign.gauntlet_report.passed:
        raise MirrorRoomError(
            "delivery cumulative adversarial gauntlet failed"
        )
    if campaign.holdout_report is None:
        raise MirrorRoomError(
            "delivery requires sealed holdout evidence"
        )
    standard = campaign.final_standard
    if standard is None:
        raise MirrorRoomError(
            "delivery requires a final ratcheted standard"
        )
    verifier = _token("verifier_id", verifier_id)
    forbidden = {
        campaign.generator_id,
        campaign.executor_id,
        campaign.adversary_id,
        campaign.final_baseline.producer_id,
    }
    if verifier in forbidden:
        raise MirrorRoomError(
            "delivery verifier must be independent of learning campaign"
        )

    refs = _tokens(
        "evaluation_ref",
        evaluation_refs,
        allow_empty=False,
    )
    if len(refs) < 2:
        raise MirrorRoomError(
            "adversarial delivery requires two evaluation channels"
        )
    baseline = campaign.original_baseline
    final = campaign.final_baseline
    return AdversarialDeliveryEvidence(
        campaign_digest=campaign.digest,
        original_baseline_digest=baseline.digest,
        final_candidate_id=final.candidate_id,
        final_candidate_digest=final.digest,
        final_candidate_version=final.version,
        attempts_completed=campaign.completed_attempts,
        accepted_upgrades=campaign.accepted_upgrades,
        final_standard_digest=standard.digest,
        gauntlet_report_digest=campaign.gauntlet_report.digest,
        holdout_report_digest=campaign.holdout_report.digest,
        verifier_id=verifier,
        evaluation_refs=refs,
        verified_at=verified_at,
        rollback_candidate_id=baseline.candidate_id,
        rollback_candidate_digest=baseline.digest,
    )


__all__ = [
    "ADVERSARIAL_ATTEMPTS_REQUIRED",
    "AdversarialAttemptReceipt",
    "AdversarialCampaignReceipt",
    "AdversarialChallengeContext",
    "AdversarialDeliveryEvidence",
    "AdversarialMirrorRoom",
    "AdversarialRatchetPolicy",
    "AdversarialScenarioGenerator",
    "AdversarialStandard",
    "FixedAdversarialSuite",
    "qualify_adversarial_delivery",
]
