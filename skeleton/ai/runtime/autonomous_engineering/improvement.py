"""P3 controlled self-improvement with independent promotion and rollback."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Iterable


class ImprovementError(RuntimeError):
    pass


def _id(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be text")
    text = value.strip()
    if not text or len(text) > maximum:
        raise ValueError(f"{field} must be non-empty bounded text")
    return text


def _sha(value: object, field: str) -> str:
    text = _id(value, field, maximum=64)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{field} must be lowercase sha256")
    return text


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise TypeError(f"{field} must be numeric")
    try:
        amount=Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be finite decimal") from exc
    if not amount.is_finite():
        raise ValueError(f"{field} must be finite decimal")
    return amount.quantize(Decimal("0.000001"))


def _ratio(value: object, field: str) -> Decimal:
    amount=_decimal(value, field)
    if amount < 0 or amount > 1:
        raise ValueError(f"{field} must be in [0,1]")
    return amount


def _refs(values: Iterable[str], field: str, *, required: bool=True) -> tuple[str,...]:
    normalized=tuple(sorted({_id(item, field) for item in values}))
    if required and not normalized:
        raise ValueError(f"{field} requires evidence")
    return normalized


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class ImprovementCandidate:
    candidate_id: str
    author_id: str
    champion_model_digest: str
    challenger_model_digest: str
    experiment_scope: str
    experiment_isolated: bool
    change_digest: str
    evidence_refs: tuple[str,...]

    def __post_init__(self) -> None:
        for field in ("candidate_id","author_id","experiment_scope"):
            object.__setattr__(self,field,_id(getattr(self,field),field))
        for field in ("champion_model_digest","challenger_model_digest","change_digest"):
            object.__setattr__(self,field,_sha(getattr(self,field),field))
        if self.champion_model_digest == self.challenger_model_digest:
            raise ValueError("challenger must differ from champion")
        if self.experiment_isolated is not True:
            raise ImprovementError("self-improvement candidate must remain isolated")
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs,"candidate_evidence_ref"),
        )


@dataclass(frozen=True, slots=True)
class EvaluationVector:
    model_digest: str
    evaluation_suite_digest: str
    sample_count: int
    quality: Decimal
    safety: Decimal
    robustness: Decimal
    cost: Decimal
    evidence_refs: tuple[str,...]

    def __post_init__(self) -> None:
        object.__setattr__(self,"model_digest",_sha(self.model_digest,"model_digest"))
        object.__setattr__(
            self,
            "evaluation_suite_digest",
            _sha(self.evaluation_suite_digest,"evaluation_suite_digest"),
        )
        if isinstance(self.sample_count,bool) or not isinstance(self.sample_count,int) or self.sample_count < 1:
            raise ValueError("sample_count must be positive integer")
        for field in ("quality","safety","robustness"):
            object.__setattr__(self,field,_ratio(getattr(self,field),field))
        cost=_decimal(self.cost,"cost")
        if cost < 0:
            raise ValueError("cost must be non-negative")
        object.__setattr__(self,"cost",cost)
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs,"evaluation_evidence_ref"),
        )


@dataclass(frozen=True, slots=True)
class PromotionPolicy:
    policy_id: str
    min_samples: int
    min_quality_delta: Decimal
    min_safety: Decimal
    min_robustness: Decimal
    max_cost_ratio: Decimal
    max_canary_fraction: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self,"policy_id",_id(self.policy_id,"policy_id"))
        if isinstance(self.min_samples,bool) or not isinstance(self.min_samples,int) or self.min_samples < 1:
            raise ValueError("min_samples must be positive integer")
        object.__setattr__(self,"min_quality_delta",_decimal(self.min_quality_delta,"min_quality_delta"))
        object.__setattr__(self,"min_safety",_ratio(self.min_safety,"min_safety"))
        object.__setattr__(self,"min_robustness",_ratio(self.min_robustness,"min_robustness"))
        ratio=_decimal(self.max_cost_ratio,"max_cost_ratio")
        if ratio <= 0:
            raise ValueError("max_cost_ratio must be >0")
        object.__setattr__(self,"max_cost_ratio",ratio)
        canary=_ratio(self.max_canary_fraction,"max_canary_fraction")
        if canary <= 0 or canary >= 1:
            raise ValueError("max_canary_fraction must be in (0,1)")
        object.__setattr__(self,"max_canary_fraction",canary)


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    candidate_id: str
    promoter_id: str
    policy_id: str
    approved_for_canary: bool
    reason_codes: tuple[str,...]
    champion_model_digest: str
    challenger_model_digest: str
    evaluation_suite_digest: str
    canary_fraction: Decimal
    rollback_ref: str
    evidence_refs: tuple[str,...]
    decision_digest: str


def evaluate_improvement(
    candidate: ImprovementCandidate,
    *,
    champion: EvaluationVector,
    challenger: EvaluationVector,
    policy: PromotionPolicy,
    promoter_id: str,
    canary_fraction: object,
    rollback_ref: str,
    promotion_evidence_refs: Iterable[str],
) -> PromotionDecision:
    """Return independent canary eligibility; never directly replaces champion."""

    promoter=_id(promoter_id,"promoter_id")
    if promoter == candidate.author_id:
        raise ImprovementError("candidate author cannot independently promote itself")
    rollback=_id(rollback_ref,"rollback_ref")
    refs=_refs(promotion_evidence_refs,"promotion_evidence_ref")
    if champion.model_digest != candidate.champion_model_digest:
        raise ImprovementError("champion evaluation identity does not match candidate")
    if challenger.model_digest != candidate.challenger_model_digest:
        raise ImprovementError("challenger evaluation identity does not match candidate")
    if champion.evaluation_suite_digest != challenger.evaluation_suite_digest:
        raise ImprovementError("champion/challenger must use identical predeclared evaluation suite")
    if champion.sample_count != challenger.sample_count:
        raise ImprovementError("champion/challenger sample population must match")
    fraction=_ratio(canary_fraction,"canary_fraction")
    if fraction <= 0 or fraction > policy.max_canary_fraction:
        raise ImprovementError("canary fraction exceeds declared policy")

    reasons: list[str]=[]
    if champion.sample_count < policy.min_samples:
        reasons.append("insufficient_samples")
    quality_delta=challenger.quality - champion.quality
    if quality_delta < policy.min_quality_delta:
        reasons.append("quality_delta_below_threshold")
    if challenger.safety < policy.min_safety:
        reasons.append("safety_below_threshold")
    if challenger.robustness < policy.min_robustness:
        reasons.append("robustness_below_threshold")
    if champion.cost == 0:
        if challenger.cost > 0:
            reasons.append("cost_ratio_exceeded")
    elif challenger.cost / champion.cost > policy.max_cost_ratio:
        reasons.append("cost_ratio_exceeded")
    # A challenger cannot trade away a major safety dimension merely because
    # aggregate quality improves.
    if challenger.safety < champion.safety:
        reasons.append("safety_regression")
    if challenger.robustness < champion.robustness:
        reasons.append("robustness_regression")

    reason_codes=tuple(sorted(set(reasons))) or ("all_predeclared_gates_passed",)
    approved=not reasons
    material={
        "candidate_id":candidate.candidate_id,
        "promoter_id":promoter,
        "policy_id":policy.policy_id,
        "approved_for_canary":approved,
        "reason_codes":list(reason_codes),
        "champion_model_digest":candidate.champion_model_digest,
        "challenger_model_digest":candidate.challenger_model_digest,
        "evaluation_suite_digest":champion.evaluation_suite_digest,
        "sample_count":champion.sample_count,
        "quality_delta":str(quality_delta),
        "champion_safety":str(champion.safety),
        "challenger_safety":str(challenger.safety),
        "champion_robustness":str(champion.robustness),
        "challenger_robustness":str(challenger.robustness),
        "champion_cost":str(champion.cost),
        "challenger_cost":str(challenger.cost),
        "canary_fraction":str(fraction),
        "rollback_ref":rollback,
        "candidate_evidence_refs":list(candidate.evidence_refs),
        "champion_evidence_refs":list(champion.evidence_refs),
        "challenger_evidence_refs":list(challenger.evidence_refs),
        "promotion_evidence_refs":list(refs),
    }
    return PromotionDecision(
        candidate_id=candidate.candidate_id,
        promoter_id=promoter,
        policy_id=policy.policy_id,
        approved_for_canary=approved,
        reason_codes=reason_codes,
        champion_model_digest=candidate.champion_model_digest,
        challenger_model_digest=candidate.challenger_model_digest,
        evaluation_suite_digest=champion.evaluation_suite_digest,
        canary_fraction=fraction,
        rollback_ref=rollback,
        evidence_refs=refs,
        decision_digest=_digest(material),
    )


__all__=[
    "EvaluationVector",
    "ImprovementCandidate",
    "ImprovementError",
    "PromotionDecision",
    "PromotionPolicy",
    "evaluate_improvement",
]
