"""High-end content quality constitution for the 100-attempt Mirror Room."""

from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import median
from types import MappingProxyType
from typing import Mapping, Sequence

from skeleton.contracts.canonical import EvidenceRef

from .adversarial import (
    ADVERSARIAL_ATTEMPTS_REQUIRED,
    AdversarialCampaignReceipt,
    qualify_adversarial_delivery,
)
from .contracts import (
    MirrorRoomError,
    MirrorScenario,
    ScenarioSplit,
    _digest,
    _non_negative_int,
    _positive_int,
    _sha256,
    _token,
    _tokens,
)
from .evaluation import ComparisonReport


QUALITY_TAG_PREFIX = "quality:"
ATTACK_TAG_PREFIX = "attack:"


def _score(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MirrorRoomError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise MirrorRoomError(f"{name} must be within [0, 1]")
    return result


@dataclass(frozen=True, slots=True)
class ContentQualityDimension:
    dimension_id: str
    metric_id: str
    minimum_validation_floor: float
    minimum_gauntlet_floor: float
    minimum_holdout_floor: float
    weight: float = 1.0
    critical: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "dimension_id", _token("dimension_id", self.dimension_id))
        object.__setattr__(self, "metric_id", _token("metric_id", self.metric_id))
        for field in (
            "minimum_validation_floor",
            "minimum_gauntlet_floor",
            "minimum_holdout_floor",
        ):
            object.__setattr__(self, field, _score(field, getattr(self, field)))
        weight = float(self.weight)
        if not math.isfinite(weight) or weight <= 0.0:
            raise MirrorRoomError("quality dimension weight must be positive")
        object.__setattr__(self, "weight", weight)
        if not isinstance(self.critical, bool):
            raise MirrorRoomError("critical must be boolean")

    @property
    def digest(self) -> str:
        return _digest({
            "dimension_id": self.dimension_id,
            "metric_id": self.metric_id,
            "minimum_validation_floor": self.minimum_validation_floor,
            "minimum_gauntlet_floor": self.minimum_gauntlet_floor,
            "minimum_holdout_floor": self.minimum_holdout_floor,
            "weight": self.weight,
            "critical": self.critical,
        })


@dataclass(frozen=True, slots=True)
class HighEndContentConstitution:
    dimensions: tuple[ContentQualityDimension, ...]
    minimum_overall_validation_score: float = 0.95
    minimum_overall_gauntlet_score: float = 0.94
    minimum_overall_holdout_score: float = 0.94
    minimum_worst_case_holdout_score: float = 0.92
    minimum_accepted_upgrades: int = 25
    minimum_attacks_per_dimension: int = 6
    minimum_attack_families_per_dimension: int = 3
    maximum_attack_imbalance: int = 2
    minimum_blind_judges: int = 5
    maximum_judge_spread: float = 0.04
    minimum_cumulative_validation_gain: float = 0.02
    minimum_dimension_lift: float = 0.01
    minimum_standard_escalation_ratio: float = 4.0
    minimum_upgrades_per_quartile: int = 3
    tier_id: str = "high-end.v3"

    def __post_init__(self) -> None:
        dims = tuple(self.dimensions)
        if not dims or any(not isinstance(x, ContentQualityDimension) for x in dims):
            raise MirrorRoomError("content constitution requires quality dimensions")
        if len({x.dimension_id for x in dims}) != len(dims):
            raise MirrorRoomError("quality dimension IDs must be unique")
        if len({x.metric_id for x in dims}) != len(dims):
            raise MirrorRoomError("quality metric IDs must be unique")
        object.__setattr__(self, "dimensions", dims)
        for field in (
            "minimum_overall_validation_score",
            "minimum_overall_gauntlet_score",
            "minimum_overall_holdout_score",
            "minimum_worst_case_holdout_score",
        ):
            object.__setattr__(self, field, _score(field, getattr(self, field)))
        upgrades = _positive_int("minimum_accepted_upgrades", self.minimum_accepted_upgrades)
        if upgrades > ADVERSARIAL_ATTEMPTS_REQUIRED:
            raise MirrorRoomError("minimum_accepted_upgrades cannot exceed 100")
        object.__setattr__(self, "minimum_accepted_upgrades", upgrades)
        object.__setattr__(
            self,
            "minimum_attacks_per_dimension",
            _positive_int(
                "minimum_attacks_per_dimension",
                self.minimum_attacks_per_dimension,
            ),
        )
        object.__setattr__(
            self,
            "minimum_attack_families_per_dimension",
            _positive_int(
                "minimum_attack_families_per_dimension",
                self.minimum_attack_families_per_dimension,
            ),
        )
        object.__setattr__(
            self,
            "maximum_attack_imbalance",
            _non_negative_int(
                "maximum_attack_imbalance",
                self.maximum_attack_imbalance,
            ),
        )
        object.__setattr__(
            self,
            "minimum_blind_judges",
            _positive_int(
                "minimum_blind_judges",
                self.minimum_blind_judges,
            ),
        )
        if self.minimum_blind_judges < 3:
            raise MirrorRoomError(
                "high-end content requires at least three blind judges"
            )
        object.__setattr__(
            self,
            "maximum_judge_spread",
            _score(
                "maximum_judge_spread",
                self.maximum_judge_spread,
            ),
        )
        object.__setattr__(
            self,
            "minimum_cumulative_validation_gain",
            _score(
                "minimum_cumulative_validation_gain",
                self.minimum_cumulative_validation_gain,
            ),
        )
        object.__setattr__(
            self,
            "minimum_dimension_lift",
            _score(
                "minimum_dimension_lift",
                self.minimum_dimension_lift,
            ),
        )
        ratio = float(self.minimum_standard_escalation_ratio)
        if not math.isfinite(ratio) or ratio < 1.0:
            raise MirrorRoomError(
                "minimum_standard_escalation_ratio must be >= 1"
            )
        object.__setattr__(
            self,
            "minimum_standard_escalation_ratio",
            ratio,
        )
        quartile = _positive_int(
            "minimum_upgrades_per_quartile",
            self.minimum_upgrades_per_quartile,
        )
        if quartile > 25:
            raise MirrorRoomError(
                "minimum_upgrades_per_quartile cannot exceed 25"
            )
        object.__setattr__(
            self,
            "minimum_upgrades_per_quartile",
            quartile,
        )
        object.__setattr__(self, "tier_id", _token("tier_id", self.tier_id))

    @classmethod
    def canonical(cls) -> "HighEndContentConstitution":
        rows = (
            ("intent_fidelity", "content.intent_fidelity", .95, .94, .93, 1.6, True),
            ("factual_correctness", "content.factual_correctness", .96, .95, .94, 1.8, True),
            ("epistemic_calibration", "content.epistemic_calibration", .94, .93, .92, 1.3, True),
            ("reasoning_coherence", "content.reasoning_coherence", .95, .94, .93, 1.5, True),
            ("completeness", "content.completeness", .93, .92, .91, 1.2, False),
            ("specificity", "content.specificity", .92, .91, .90, 1.0, False),
            ("usefulness", "content.usefulness", .95, .94, .93, 1.6, True),
            ("structure", "content.structure", .92, .91, .90, .9, False),
            ("style", "content.style", .91, .90, .89, .8, False),
            ("robustness", "content.robustness", .95, .94, .93, 1.5, True),
            ("constraint_compliance", "content.constraint_compliance", .96, .95, .94, 1.7, True),
            ("evidence_quality", "content.evidence_quality", .95, .94, .93, 1.5, True),
            ("self_consistency", "content.self_consistency", .94, .93, .92, 1.2, True),
            ("information_density", "content.information_density", .92, .91, .90, .9, False),
            ("safety", "content.safety", .98, .97, .96, 1.8, True),
        )
        return cls(dimensions=tuple(
            ContentQualityDimension(
                dimension_id=a, metric_id=b,
                minimum_validation_floor=c,
                minimum_gauntlet_floor=d,
                minimum_holdout_floor=e,
                weight=f, critical=g,
            )
            for a, b, c, d, e, f, g in rows
        ))

    @property
    def digest(self) -> str:
        return _digest({
            "tier_id": self.tier_id,
            "dimensions": [x.digest for x in self.dimensions],
            "minimum_overall_validation_score": self.minimum_overall_validation_score,
            "minimum_overall_gauntlet_score": self.minimum_overall_gauntlet_score,
            "minimum_overall_holdout_score": self.minimum_overall_holdout_score,
            "minimum_worst_case_holdout_score": self.minimum_worst_case_holdout_score,
            "minimum_accepted_upgrades": self.minimum_accepted_upgrades,
            "minimum_attacks_per_dimension": self.minimum_attacks_per_dimension,
            "minimum_attack_families_per_dimension": (
                self.minimum_attack_families_per_dimension
            ),
            "maximum_attack_imbalance": self.maximum_attack_imbalance,
            "minimum_blind_judges": self.minimum_blind_judges,
            "maximum_judge_spread": self.maximum_judge_spread,
            "minimum_cumulative_validation_gain": (
                self.minimum_cumulative_validation_gain
            ),
            "minimum_dimension_lift": self.minimum_dimension_lift,
            "minimum_standard_escalation_ratio": (
                self.minimum_standard_escalation_ratio
            ),
            "minimum_upgrades_per_quartile": (
                self.minimum_upgrades_per_quartile
            ),
        })


def _freeze_scores(name: str, values: Mapping[str, float]) -> Mapping[str, float]:
    return MappingProxyType(dict(sorted(
        (_token("dimension_id", key), _score(name, value))
        for key, value in values.items()
    )))


def _freeze_counts(values: Mapping[str, int]) -> Mapping[str, int]:
    return MappingProxyType(dict(sorted(
        (_token("dimension_id", key), _non_negative_int("attack_count", value))
        for key, value in values.items()
    )))



@dataclass(frozen=True, slots=True)
class IndependentQualityJudgeReceipt:
    """Blind calibrated judgment from one evaluator outside the campaign."""

    judge_id: str
    channel_id: str
    candidate_digest: str
    constitution_digest: str
    dimension_scores: Mapping[str, float]
    evidence_digest: str
    calibration_digest: str
    evaluated_at: int
    blind: bool = True
    production_authority: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "judge_id", _token("judge_id", self.judge_id))
        object.__setattr__(
            self,
            "channel_id",
            _token("channel_id", self.channel_id),
        )
        object.__setattr__(
            self,
            "candidate_digest",
            _sha256("candidate_digest", self.candidate_digest),
        )
        object.__setattr__(
            self,
            "constitution_digest",
            _sha256("constitution_digest", self.constitution_digest),
        )
        object.__setattr__(
            self,
            "dimension_scores",
            _freeze_scores("judge_dimension_score", self.dimension_scores),
        )
        object.__setattr__(
            self,
            "evidence_digest",
            _sha256("evidence_digest", self.evidence_digest),
        )
        object.__setattr__(
            self,
            "calibration_digest",
            _sha256("calibration_digest", self.calibration_digest),
        )
        object.__setattr__(
            self,
            "evaluated_at",
            _non_negative_int("evaluated_at", self.evaluated_at),
        )
        if self.blind is not True:
            raise MirrorRoomError("high-end quality judges must be blind")
        if self.production_authority is not False:
            raise MirrorRoomError(
                "quality judge receipt cannot grant production authority"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "judge_id": self.judge_id,
                "channel_id": self.channel_id,
                "candidate_digest": self.candidate_digest,
                "constitution_digest": self.constitution_digest,
                "dimension_scores": dict(self.dimension_scores),
                "evidence_digest": self.evidence_digest,
                "calibration_digest": self.calibration_digest,
                "evaluated_at": self.evaluated_at,
                "blind": True,
                "production_authority": False,
            }
        )


@dataclass(frozen=True, slots=True)
class QualityJudgePanelReceipt:
    """Robust consensus over at least three independent blind judges."""

    candidate_digest: str
    constitution_digest: str
    judge_receipt_digests: tuple[str, ...]
    judge_ids: tuple[str, ...]
    channel_ids: tuple[str, ...]
    dimension_scores: Mapping[str, float]
    dimension_spreads: Mapping[str, float]
    overall_score: float
    maximum_spread: float
    production_authority: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_digest",
            _sha256("candidate_digest", self.candidate_digest),
        )
        object.__setattr__(
            self,
            "constitution_digest",
            _sha256("constitution_digest", self.constitution_digest),
        )
        digests = tuple(
            _sha256("judge_receipt_digest", item)
            for item in self.judge_receipt_digests
        )
        judges = _tokens("judge_id", self.judge_ids, allow_empty=False)
        channels = _tokens(
            "channel_id",
            self.channel_ids,
            allow_empty=False,
        )
        if len(digests) < 3 or len(judges) < 3 or len(channels) < 3:
            raise MirrorRoomError(
                "high-end judge panel requires three independent channels"
            )
        if len(digests) != len(judges) or len(judges) != len(channels):
            raise MirrorRoomError(
                "judge panel identity cardinality mismatch"
            )
        object.__setattr__(self, "judge_receipt_digests", digests)
        object.__setattr__(self, "judge_ids", judges)
        object.__setattr__(self, "channel_ids", channels)
        object.__setattr__(
            self,
            "dimension_scores",
            _freeze_scores(
                "panel_dimension_score",
                self.dimension_scores,
            ),
        )
        object.__setattr__(
            self,
            "dimension_spreads",
            _freeze_scores(
                "panel_dimension_spread",
                self.dimension_spreads,
            ),
        )
        object.__setattr__(
            self,
            "overall_score",
            _score("overall_score", self.overall_score),
        )
        object.__setattr__(
            self,
            "maximum_spread",
            _score("maximum_spread", self.maximum_spread),
        )
        if self.production_authority is not False:
            raise MirrorRoomError(
                "judge panel cannot grant production authority"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "candidate_digest": self.candidate_digest,
                "constitution_digest": self.constitution_digest,
                "judge_receipt_digests": list(
                    self.judge_receipt_digests
                ),
                "judge_ids": list(self.judge_ids),
                "channel_ids": list(self.channel_ids),
                "dimension_scores": dict(self.dimension_scores),
                "dimension_spreads": dict(self.dimension_spreads),
                "overall_score": self.overall_score,
                "maximum_spread": self.maximum_spread,
                "production_authority": False,
            }
        )


@dataclass(frozen=True, slots=True)
class HighEndContentDeliveryDossier:
    tier_id: str
    campaign_digest: str
    base_delivery_evidence_digest: str
    constitution_digest: str
    final_candidate_id: str
    final_candidate_digest: str
    final_candidate_version: str
    attempts_completed: int
    accepted_upgrades: int
    final_standard_digest: str
    gauntlet_report_digest: str
    holdout_report_digest: str
    judge_panel_digest: str
    validation_scores: Mapping[str, float]
    gauntlet_worst_case_scores: Mapping[str, float]
    holdout_worst_case_scores: Mapping[str, float]
    judge_panel_scores: Mapping[str, float]
    validation_lifts: Mapping[str, float]
    attack_counts: Mapping[str, int]
    attack_family_counts: Mapping[str, int]
    overall_validation_score: float
    overall_validation_gain: float
    overall_gauntlet_score: float
    overall_holdout_score: float
    judge_panel_overall_score: float
    judge_panel_maximum_spread: float
    worst_case_holdout_score: float
    verifier_id: str
    evaluation_refs: tuple[str, ...]
    verified_at: int
    rollback_candidate_id: str
    rollback_candidate_digest: str
    production_authority: bool = False
    direct_self_modify: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "tier_id", _token("tier_id", self.tier_id))
        for field in (
            "campaign_digest", "base_delivery_evidence_digest",
            "constitution_digest", "final_candidate_digest",
            "final_standard_digest", "gauntlet_report_digest",
            "holdout_report_digest", "judge_panel_digest",
            "rollback_candidate_digest",
        ):
            object.__setattr__(self, field, _sha256(field, getattr(self, field)))
        for field in (
            "final_candidate_id", "final_candidate_version",
            "verifier_id", "rollback_candidate_id",
        ):
            object.__setattr__(self, field, _token(field, getattr(self, field)))
        attempts = _positive_int("attempts_completed", self.attempts_completed)
        if attempts != ADVERSARIAL_ATTEMPTS_REQUIRED:
            raise MirrorRoomError("high-end delivery requires all 100 attempts")
        object.__setattr__(self, "attempts_completed", attempts)
        object.__setattr__(self, "accepted_upgrades", _positive_int(
            "accepted_upgrades", self.accepted_upgrades
        ))
        object.__setattr__(self, "validation_scores", _freeze_scores(
            "validation_score", self.validation_scores
        ))
        object.__setattr__(self, "gauntlet_worst_case_scores", _freeze_scores(
            "gauntlet_worst_case_score", self.gauntlet_worst_case_scores
        ))
        object.__setattr__(self, "holdout_worst_case_scores", _freeze_scores(
            "holdout_worst_case_score", self.holdout_worst_case_scores
        ))
        object.__setattr__(self, "judge_panel_scores", _freeze_scores(
            "judge_panel_score", self.judge_panel_scores
        ))
        object.__setattr__(self, "validation_lifts", _freeze_scores(
            "validation_lift", self.validation_lifts
        ))
        object.__setattr__(self, "attack_counts", _freeze_counts(self.attack_counts))
        object.__setattr__(
            self,
            "attack_family_counts",
            _freeze_counts(self.attack_family_counts),
        )
        for field in (
            "overall_validation_score", "overall_validation_gain",
            "overall_gauntlet_score", "overall_holdout_score",
            "judge_panel_overall_score", "judge_panel_maximum_spread",
            "worst_case_holdout_score",
        ):
            object.__setattr__(self, field, _score(field, getattr(self, field)))
        refs = _tokens("evaluation_ref", self.evaluation_refs, allow_empty=False)
        if len(refs) < 3:
            raise MirrorRoomError("high-end delivery requires at least three evaluation channels")
        object.__setattr__(self, "evaluation_refs", refs)
        object.__setattr__(self, "verified_at", _non_negative_int("verified_at", self.verified_at))
        if self.production_authority is not False or self.direct_self_modify is not False:
            raise MirrorRoomError("high-end content dossier is evidence-only")

    @property
    def digest(self) -> str:
        return _digest({
            "tier_id": self.tier_id,
            "campaign_digest": self.campaign_digest,
            "base_delivery_evidence_digest": self.base_delivery_evidence_digest,
            "constitution_digest": self.constitution_digest,
            "final_candidate_id": self.final_candidate_id,
            "final_candidate_digest": self.final_candidate_digest,
            "final_candidate_version": self.final_candidate_version,
            "attempts_completed": self.attempts_completed,
            "accepted_upgrades": self.accepted_upgrades,
            "final_standard_digest": self.final_standard_digest,
            "gauntlet_report_digest": self.gauntlet_report_digest,
            "holdout_report_digest": self.holdout_report_digest,
            "judge_panel_digest": self.judge_panel_digest,
            "validation_scores": dict(self.validation_scores),
            "gauntlet_worst_case_scores": dict(self.gauntlet_worst_case_scores),
            "holdout_worst_case_scores": dict(self.holdout_worst_case_scores),
            "judge_panel_scores": dict(self.judge_panel_scores),
            "validation_lifts": dict(self.validation_lifts),
            "attack_counts": dict(self.attack_counts),
            "attack_family_counts": dict(self.attack_family_counts),
            "overall_validation_score": self.overall_validation_score,
            "overall_validation_gain": self.overall_validation_gain,
            "overall_gauntlet_score": self.overall_gauntlet_score,
            "overall_holdout_score": self.overall_holdout_score,
            "judge_panel_overall_score": self.judge_panel_overall_score,
            "judge_panel_maximum_spread": self.judge_panel_maximum_spread,
            "worst_case_holdout_score": self.worst_case_holdout_score,
            "verifier_id": self.verifier_id,
            "evaluation_refs": list(self.evaluation_refs),
            "verified_at": self.verified_at,
            "rollback_candidate_id": self.rollback_candidate_id,
            "rollback_candidate_digest": self.rollback_candidate_digest,
            "production_authority": False,
            "direct_self_modify": False,
        })

    def evidence_ref(self) -> EvidenceRef:
        return EvidenceRef(
            source=f"mirror-room:high-end-content:{self.final_candidate_id}",
            digest=self.digest,
            category="mirror_room_high_end_content_delivery",
        )


def _worst_candidate_scores(report: ComparisonReport) -> dict[str, float]:
    scores: dict[str, float] = {}
    for scenario in report.scenario_comparisons:
        for metric_id, value in scenario.candidate_receipt.outcome.metric_values.items():
            scores[metric_id] = min(scores.get(metric_id, float(value)), float(value))
    return scores


def _weighted_score(
    constitution: HighEndContentConstitution,
    scores: Mapping[str, float],
) -> float:
    total = sum(x.weight for x in constitution.dimensions)
    return sum(scores[x.dimension_id] * x.weight for x in constitution.dimensions) / total


def _attack_coverage(
    campaign: AdversarialCampaignReceipt,
    constitution: HighEndContentConstitution,
    challenge_catalog: Sequence[MirrorScenario],
) -> tuple[dict[str, int], dict[str, int]]:
    catalog = {}
    for scenario in challenge_catalog:
        if (
            not isinstance(scenario, MirrorScenario)
            or scenario.split is not ScenarioSplit.TRAIN
        ):
            raise MirrorRoomError(
                "quality challenge catalog must contain TRAIN MirrorScenario"
            )
        if scenario.scenario_id in catalog:
            raise MirrorRoomError(
                "quality challenge catalog IDs must be unique"
            )
        catalog[scenario.scenario_id] = scenario

    dimensions = {x.dimension_id for x in constitution.dimensions}
    counts = {x: 0 for x in dimensions}
    families = {x: set() for x in dimensions}
    expected = 0
    for attempt in campaign.attempts:
        for challenge_id, challenge_digest in zip(
            attempt.challenge_ids,
            attempt.challenge_digests,
            strict=True,
        ):
            expected += 1
            scenario = catalog.get(challenge_id)
            if scenario is None:
                raise MirrorRoomError(
                    "quality challenge catalog is incomplete"
                )
            if scenario.digest != challenge_digest:
                raise MirrorRoomError(
                    "quality challenge catalog digest drift"
                )
            tagged = {
                tag[len(QUALITY_TAG_PREFIX):]
                for tag in scenario.tags
                if tag.startswith(QUALITY_TAG_PREFIX)
            } & dimensions
            if len(tagged) != 1:
                raise MirrorRoomError(
                    "adversarial content challenge must target one quality dimension"
                )
            attack_families = {
                tag[len(ATTACK_TAG_PREFIX):]
                for tag in scenario.tags
                if tag.startswith(ATTACK_TAG_PREFIX)
            }
            if not attack_families:
                raise MirrorRoomError(
                    "adversarial content challenge requires an attack family"
                )
            dimension_id = next(iter(tagged))
            counts[dimension_id] += 1
            families[dimension_id].update(attack_families)

    required = (
        ADVERSARIAL_ATTEMPTS_REQUIRED
        * campaign.policy.challenges_per_attempt
    )
    if expected != required:
        raise MirrorRoomError(
            "quality attack catalog does not cover all 100 attempts"
        )
    return counts, {
        dimension_id: len(values)
        for dimension_id, values in families.items()
    }


def _qualify_judge_panel(
    campaign: AdversarialCampaignReceipt,
    constitution: HighEndContentConstitution,
    receipts: Sequence[IndependentQualityJudgeReceipt],
    *,
    verifier_id: str,
) -> QualityJudgePanelReceipt:
    rows = tuple(receipts)
    if len(rows) < constitution.minimum_blind_judges or any(
        not isinstance(item, IndependentQualityJudgeReceipt)
        for item in rows
    ):
        raise MirrorRoomError(
            "high-end delivery requires the configured independent quality judges"
        )
    judge_ids = [item.judge_id for item in rows]
    channel_ids = [item.channel_id for item in rows]
    if len(judge_ids) != len(set(judge_ids)):
        raise MirrorRoomError("quality judge identities must be unique")
    if len(channel_ids) != len(set(channel_ids)):
        raise MirrorRoomError("quality judge channels must be unique")

    forbidden = {
        campaign.generator_id,
        campaign.executor_id,
        campaign.adversary_id,
        campaign.final_baseline.producer_id,
        verifier_id,
    }
    if forbidden & set(judge_ids):
        raise MirrorRoomError("quality judge identity is not independent")

    dimension_ids = {
        item.dimension_id for item in constitution.dimensions
    }
    for item in rows:
        if item.candidate_digest != campaign.final_baseline.digest:
            raise MirrorRoomError(
                "quality judge evaluated another candidate"
            )
        if item.constitution_digest != constitution.digest:
            raise MirrorRoomError(
                "quality judge used another constitution"
            )
        if set(item.dimension_scores) != dimension_ids:
            raise MirrorRoomError(
                "quality judge dimension set drifted"
            )

    panel_scores: dict[str, float] = {}
    panel_spreads: dict[str, float] = {}
    for dimension in constitution.dimensions:
        values = [
            item.dimension_scores[dimension.dimension_id]
            for item in rows
        ]
        consensus = float(median(values))
        spread = max(values) - min(values)
        if spread > constitution.maximum_judge_spread:
            raise MirrorRoomError(
                f"judge panel disagreement too wide:{dimension.dimension_id}"
            )
        panel_spreads[dimension.dimension_id] = spread
        if (
            dimension.critical
            and min(values) < dimension.minimum_holdout_floor
        ):
            raise MirrorRoomError(
                f"critical judge disagreement:{dimension.dimension_id}"
            )
        if consensus < dimension.minimum_holdout_floor:
            raise MirrorRoomError(
                f"judge panel quality floor failed:{dimension.dimension_id}"
            )
        panel_scores[dimension.dimension_id] = consensus

    overall = _weighted_score(constitution, panel_scores)
    if overall < constitution.minimum_overall_holdout_score:
        raise MirrorRoomError(
            "judge panel overall quality floor failed"
        )
    return QualityJudgePanelReceipt(
        candidate_digest=campaign.final_baseline.digest,
        constitution_digest=constitution.digest,
        judge_receipt_digests=tuple(item.digest for item in rows),
        judge_ids=tuple(judge_ids),
        channel_ids=tuple(channel_ids),
        dimension_scores=panel_scores,
        dimension_spreads=panel_spreads,
        overall_score=overall,
        maximum_spread=max(panel_spreads.values()),
    )


def qualify_high_end_content_delivery(
    campaign: AdversarialCampaignReceipt,
    *,
    constitution: HighEndContentConstitution,
    challenge_catalog: Sequence[MirrorScenario],
    judge_receipts: Sequence[IndependentQualityJudgeReceipt],
    verifier_id: str,
    evaluation_refs: tuple[str, ...],
    verified_at: int,
) -> HighEndContentDeliveryDossier:
    if not isinstance(constitution, HighEndContentConstitution):
        raise TypeError("constitution must be HighEndContentConstitution")
    base = qualify_adversarial_delivery(
        campaign,
        verifier_id=verifier_id,
        evaluation_refs=evaluation_refs,
        verified_at=verified_at,
    )
    if campaign.gauntlet_report is None or campaign.holdout_report is None:
        raise MirrorRoomError("high-end delivery requires gauntlet and holdout evidence")
    if campaign.accepted_upgrades < constitution.minimum_accepted_upgrades:
        raise MirrorRoomError("high-end delivery has too few accepted ratchet upgrades")
    standard = campaign.final_standard
    if standard is None:
        raise MirrorRoomError("high-end delivery requires final standard")

    first_bar = campaign.attempts[0].required_weighted_gain
    final_bar = campaign.attempts[-1].required_weighted_gain
    if first_bar <= 0.0:
        if final_bar <= first_bar:
            raise MirrorRoomError(
                "high-end delivery requires an escalating standard"
            )
    elif (
        final_bar / first_bar
        < constitution.minimum_standard_escalation_ratio
    ):
        raise MirrorRoomError(
            "high-end delivery standard did not escalate enough"
        )

    quartile_counts = []
    for start in (1, 26, 51, 76):
        stop = start + 24
        quartile_counts.append(
            sum(
                int(item.accepted)
                for item in campaign.attempts
                if start <= item.attempt <= stop
            )
        )
    if min(quartile_counts) < constitution.minimum_upgrades_per_quartile:
        raise MirrorRoomError(
            "high-end delivery lacks sustained upgrades across all quartiles"
        )

    validation_raw = dict(standard.metric_floors)
    first_attempt = campaign.attempts[0]
    initial_validation_raw = {
        item.metric_id: item.baseline_mean
        for item in first_attempt.validation_report.metric_comparisons
    }
    gauntlet_raw = _worst_candidate_scores(campaign.gauntlet_report)
    holdout_raw = _worst_candidate_scores(campaign.holdout_report)
    validation_scores = {}
    validation_lifts = {}
    initial_validation_scores = {}
    gauntlet_scores = {}
    holdout_scores = {}
    for dimension in constitution.dimensions:
        metric = dimension.metric_id
        if (
            metric not in validation_raw
            or metric not in initial_validation_raw
            or metric not in gauntlet_raw
            or metric not in holdout_raw
        ):
            raise MirrorRoomError(
                "high-end content metric is missing from delivery evidence"
            )
        validation = _score(
            f"validation[{dimension.dimension_id}]",
            validation_raw[metric],
        )
        initial_validation = _score(
            f"initial_validation[{dimension.dimension_id}]",
            initial_validation_raw[metric],
        )
        gauntlet = _score(f"gauntlet[{dimension.dimension_id}]", gauntlet_raw[metric])
        holdout = _score(f"holdout[{dimension.dimension_id}]", holdout_raw[metric])
        if validation < dimension.minimum_validation_floor:
            raise MirrorRoomError(f"validation quality floor failed:{dimension.dimension_id}")
        if gauntlet < dimension.minimum_gauntlet_floor:
            raise MirrorRoomError(f"gauntlet quality floor failed:{dimension.dimension_id}")
        if holdout < dimension.minimum_holdout_floor:
            raise MirrorRoomError(f"holdout quality floor failed:{dimension.dimension_id}")
        lift = validation - initial_validation
        if lift < constitution.minimum_dimension_lift:
            raise MirrorRoomError(
                f"validation standard lift too small:{dimension.dimension_id}"
            )
        validation_scores[dimension.dimension_id] = validation
        initial_validation_scores[dimension.dimension_id] = initial_validation
        validation_lifts[dimension.dimension_id] = lift
        gauntlet_scores[dimension.dimension_id] = gauntlet
        holdout_scores[dimension.dimension_id] = holdout

    panel = _qualify_judge_panel(
        campaign,
        constitution,
        judge_receipts,
        verifier_id=base.verifier_id,
    )

    counts, family_counts = _attack_coverage(
        campaign,
        constitution,
        challenge_catalog,
    )
    for dimension in constitution.dimensions:
        dimension_id = dimension.dimension_id
        if counts[dimension_id] < constitution.minimum_attacks_per_dimension:
            raise MirrorRoomError(
                f"insufficient adversarial coverage:{dimension_id}"
            )
        if (
            family_counts[dimension_id]
            < constitution.minimum_attack_families_per_dimension
        ):
            raise MirrorRoomError(
                f"insufficient adversarial coverage: family diversity:{dimension_id}"
            )
    if max(counts.values()) - min(counts.values()) > constitution.maximum_attack_imbalance:
        raise MirrorRoomError(
            "adversarial quality coverage is too imbalanced"
        )

    overall_validation = _weighted_score(constitution, validation_scores)
    initial_overall_validation = _weighted_score(
        constitution,
        initial_validation_scores,
    )
    overall_validation_gain = (
        overall_validation - initial_overall_validation
    )
    overall_gauntlet = _weighted_score(constitution, gauntlet_scores)
    overall_holdout = _weighted_score(constitution, holdout_scores)
    worst_holdout = min(holdout_scores.values())
    if overall_validation < constitution.minimum_overall_validation_score:
        raise MirrorRoomError("overall validation quality floor failed")
    if (
        overall_validation_gain
        < constitution.minimum_cumulative_validation_gain
    ):
        raise MirrorRoomError(
            "cumulative validation standard gain is too small"
        )
    if overall_gauntlet < constitution.minimum_overall_gauntlet_score:
        raise MirrorRoomError("overall gauntlet quality floor failed")
    if overall_holdout < constitution.minimum_overall_holdout_score:
        raise MirrorRoomError("overall holdout quality floor failed")
    if worst_holdout < constitution.minimum_worst_case_holdout_score:
        raise MirrorRoomError("worst-case holdout quality floor failed")

    final = campaign.final_baseline
    return HighEndContentDeliveryDossier(
        tier_id=constitution.tier_id,
        campaign_digest=campaign.digest,
        base_delivery_evidence_digest=base.digest,
        constitution_digest=constitution.digest,
        final_candidate_id=final.candidate_id,
        final_candidate_digest=final.digest,
        final_candidate_version=final.version,
        attempts_completed=campaign.completed_attempts,
        accepted_upgrades=campaign.accepted_upgrades,
        final_standard_digest=standard.digest,
        gauntlet_report_digest=campaign.gauntlet_report.digest,
        holdout_report_digest=campaign.holdout_report.digest,
        judge_panel_digest=panel.digest,
        validation_scores=validation_scores,
        gauntlet_worst_case_scores=gauntlet_scores,
        holdout_worst_case_scores=holdout_scores,
        judge_panel_scores=panel.dimension_scores,
        validation_lifts=validation_lifts,
        attack_counts=counts,
        attack_family_counts=family_counts,
        overall_validation_score=overall_validation,
        overall_validation_gain=overall_validation_gain,
        overall_gauntlet_score=overall_gauntlet,
        overall_holdout_score=overall_holdout,
        judge_panel_overall_score=panel.overall_score,
        judge_panel_maximum_spread=panel.maximum_spread,
        worst_case_holdout_score=worst_holdout,
        verifier_id=base.verifier_id,
        evaluation_refs=base.evaluation_refs,
        verified_at=base.verified_at,
        rollback_candidate_id=base.rollback_candidate_id,
        rollback_candidate_digest=base.rollback_candidate_digest,
    )


__all__ = [
    "ContentQualityDimension",
    "HighEndContentConstitution",
    "HighEndContentDeliveryDossier",
    "IndependentQualityJudgeReceipt",
    "QualityJudgePanelReceipt",
    "ATTACK_TAG_PREFIX",
    "QUALITY_TAG_PREFIX",
    "qualify_high_end_content_delivery",
]
