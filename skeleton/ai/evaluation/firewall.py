"""Promotion-evaluation firewall with blind-holdout exhaustion controls.

Development and regression evaluation may be iterated on. Promotion holdouts may
not be treated as an unlimited optimization oracle. This module keeps the
separation executable and records immutable evaluator/set identities for every
promotion-relevant query.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from types import MappingProxyType
from typing import Mapping


class EvaluationFirewallError(RuntimeError):
    """Evaluation isolation or promotion evidence is invalid."""


EVAL_CLASSES = {
    "development",
    "regression",
    "promotion_holdout",
    "production_observation",
}


def _stable_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EvaluationFirewallError("evaluation value is not deterministic JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _text(name: str, value: object, *, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationFirewallError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise EvaluationFirewallError(f"{name} exceeds {maximum} characters")
    return result


def _sha(name: str, value: object) -> str:
    result = _text(name, value, maximum=64).lower()
    if len(result) != 64 or any(ch not in "0123456789abcdef" for ch in result):
        raise EvaluationFirewallError(f"{name} must be lowercase sha256")
    return result


@dataclass(frozen=True, slots=True)
class EvaluationSet:
    set_id: str
    eval_class: str
    content_digest: str
    population_id: str
    query_budget: int | None
    training_excluded: bool
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "set_id", _text("set_id", self.set_id))
        if self.eval_class not in EVAL_CLASSES:
            raise EvaluationFirewallError("unsupported evaluation class")
        object.__setattr__(
            self, "content_digest", _sha("content_digest", self.content_digest)
        )
        object.__setattr__(
            self, "population_id", _text("population_id", self.population_id)
        )
        if self.query_budget is not None:
            if (
                isinstance(self.query_budget, bool)
                or not isinstance(self.query_budget, int)
                or self.query_budget <= 0
            ):
                raise EvaluationFirewallError("query_budget must be a positive integer")
        if self.eval_class == "promotion_holdout":
            if self.query_budget is None:
                raise EvaluationFirewallError("promotion holdout requires a query budget")
            if self.training_excluded is not True:
                raise EvaluationFirewallError(
                    "promotion holdout must be excluded from training"
                )
        if not isinstance(self.training_excluded, bool):
            raise TypeError("training_excluded must be boolean")
        frozen = dict(self.metadata)
        _stable_json(frozen)
        object.__setattr__(self, "metadata", MappingProxyType(frozen))

    @property
    def identity(self) -> str:
        return "evalset:" + _digest(
            {
                "schema_version": "skeleton.eval_set.v1",
                "set_id": self.set_id,
                "eval_class": self.eval_class,
                "content_digest": self.content_digest,
                "population_id": self.population_id,
                "query_budget": self.query_budget,
                "training_excluded": self.training_excluded,
                "metadata": dict(self.metadata),
            }
        )


@dataclass(frozen=True, slots=True)
class EvaluatorIdentity:
    evaluator_id: str
    implementation_digest: str
    policy_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "evaluator_id", _text("evaluator_id", self.evaluator_id)
        )
        object.__setattr__(
            self,
            "implementation_digest",
            _sha("implementation_digest", self.implementation_digest),
        )
        object.__setattr__(
            self, "policy_digest", _sha("policy_digest", self.policy_digest)
        )

    @property
    def identity(self) -> str:
        return "evaluator:" + _digest(
            {
                "evaluator_id": self.evaluator_id,
                "implementation_digest": self.implementation_digest,
                "policy_digest": self.policy_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class EvaluationQueryReceipt:
    candidate_id: str
    set_identity: str
    evaluator_identity: str
    query_index: int
    purpose: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_id",
            _text("candidate_id", self.candidate_id),
        )
        object.__setattr__(
            self,
            "set_identity",
            _text("set_identity", self.set_identity, maximum=2048),
        )
        object.__setattr__(
            self,
            "evaluator_identity",
            _text("evaluator_identity", self.evaluator_identity, maximum=2048),
        )
        if (
            isinstance(self.query_index, bool)
            or not isinstance(self.query_index, int)
            or self.query_index < 1
        ):
            raise EvaluationFirewallError(
                "query_index must be a positive integer"
            )
        object.__setattr__(
            self,
            "purpose",
            _text("purpose", self.purpose),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema_version": "skeleton.eval_query_receipt.v1",
                "candidate_id": self.candidate_id,
                "set_identity": self.set_identity,
                "evaluator_identity": self.evaluator_identity,
                "query_index": self.query_index,
                "purpose": self.purpose,
            }
        )


@dataclass(frozen=True, slots=True)
class PromotionEvidence:
    candidate_id: str
    holdout_set_identity: str
    evaluator_identity: str
    query_receipt_digests: tuple[str, ...]
    holdout_queries_used: int
    holdout_query_budget: int
    production_authority: bool = False
    direct_self_modify: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_id",
            _text("candidate_id", self.candidate_id),
        )
        object.__setattr__(
            self,
            "holdout_set_identity",
            _text(
                "holdout_set_identity",
                self.holdout_set_identity,
                maximum=2048,
            ),
        )
        object.__setattr__(
            self,
            "evaluator_identity",
            _text(
                "evaluator_identity",
                self.evaluator_identity,
                maximum=2048,
            ),
        )
        receipts = tuple(
            _sha("query_receipt_digest", item)
            for item in self.query_receipt_digests
        )
        if not receipts:
            raise EvaluationFirewallError(
                "promotion evidence requires query receipts"
            )
        if len(receipts) != len(set(receipts)):
            raise EvaluationFirewallError(
                "promotion query receipt digests must be unique"
            )
        object.__setattr__(self, "query_receipt_digests", receipts)
        for name in ("holdout_queries_used", "holdout_query_budget"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1
            ):
                raise EvaluationFirewallError(
                    f"{name} must be a positive integer"
                )
        if self.holdout_queries_used != len(receipts):
            raise EvaluationFirewallError(
                "holdout query count must match receipt lineage"
            )
        if self.holdout_queries_used > self.holdout_query_budget:
            raise EvaluationFirewallError(
                "holdout query use exceeds budget"
            )
        if self.production_authority is not False:
            raise EvaluationFirewallError(
                "promotion evidence cannot grant production authority"
            )
        if self.direct_self_modify is not False:
            raise EvaluationFirewallError(
                "promotion evidence cannot grant direct self-modification"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema_version": "skeleton.promotion_evaluation.v1",
                "candidate_id": self.candidate_id,
                "holdout_set_identity": self.holdout_set_identity,
                "evaluator_identity": self.evaluator_identity,
                "query_receipt_digests": list(self.query_receipt_digests),
                "holdout_queries_used": self.holdout_queries_used,
                "holdout_query_budget": self.holdout_query_budget,
                "production_authority": False,
                "direct_self_modify": False,
            }
        )


class EvaluationFirewall:
    def __init__(self) -> None:
        self._sets: dict[str, EvaluationSet] = {}
        self._evaluators: dict[str, EvaluatorIdentity] = {}
        self._queries: dict[tuple[str, str], list[EvaluationQueryReceipt]] = {}
        self._contaminated: dict[str, str] = {}

    def register_set(self, evaluation_set: EvaluationSet) -> EvaluationSet:
        if not isinstance(evaluation_set, EvaluationSet):
            raise TypeError("evaluation_set must be EvaluationSet")
        prior = self._sets.get(evaluation_set.set_id)
        if prior is not None and prior != evaluation_set:
            raise EvaluationFirewallError("evaluation set identity conflict")
        self._sets[evaluation_set.set_id] = evaluation_set
        return evaluation_set

    def register_evaluator(self, evaluator: EvaluatorIdentity) -> EvaluatorIdentity:
        if not isinstance(evaluator, EvaluatorIdentity):
            raise TypeError("evaluator must be EvaluatorIdentity")
        prior = self._evaluators.get(evaluator.evaluator_id)
        if prior is not None and prior != evaluator:
            raise EvaluationFirewallError("evaluator identity conflict")
        self._evaluators[evaluator.evaluator_id] = evaluator
        return evaluator

    def mark_contaminated(self, set_id: str, *, reason: str) -> None:
        set_key = _text("set_id", set_id)
        if set_key not in self._sets:
            raise EvaluationFirewallError("unknown evaluation set")
        self._contaminated[set_key] = _text("contamination reason", reason)

    def assert_training_exclusion(self, training_refs: tuple[str, ...]) -> None:
        refs = {_text("training_ref", item) for item in training_refs}
        for evaluation_set in self._sets.values():
            if evaluation_set.eval_class != "promotion_holdout":
                continue
            forbidden = {
                evaluation_set.set_id,
                evaluation_set.identity,
                evaluation_set.content_digest,
            }
            if refs & forbidden:
                raise EvaluationFirewallError(
                    "promotion holdout leaked into training references"
                )

    def query(
        self,
        *,
        candidate_id: str,
        set_id: str,
        evaluator_id: str,
        purpose: str,
    ) -> EvaluationQueryReceipt:
        candidate = _text("candidate_id", candidate_id)
        evaluation_set = self._sets.get(_text("set_id", set_id))
        if evaluation_set is None:
            raise EvaluationFirewallError("unknown evaluation set")
        evaluator = self._evaluators.get(_text("evaluator_id", evaluator_id))
        if evaluator is None:
            raise EvaluationFirewallError("unknown evaluator")
        if evaluation_set.set_id in self._contaminated:
            raise EvaluationFirewallError("contaminated evaluation set cannot be queried")

        key = (candidate, evaluation_set.set_id)
        receipts = self._queries.setdefault(key, [])
        next_index = len(receipts) + 1
        if (
            evaluation_set.eval_class == "promotion_holdout"
            and evaluation_set.query_budget is not None
            and next_index > evaluation_set.query_budget
        ):
            raise EvaluationFirewallError("promotion holdout query budget exhausted")

        receipt = EvaluationQueryReceipt(
            candidate_id=candidate,
            set_identity=evaluation_set.identity,
            evaluator_identity=evaluator.identity,
            query_index=next_index,
            purpose=_text("purpose", purpose),
        )
        receipts.append(receipt)
        return receipt

    def promotion_evidence(
        self,
        *,
        candidate_id: str,
        holdout_set_id: str,
        evaluator_id: str,
    ) -> PromotionEvidence:
        candidate = _text("candidate_id", candidate_id)
        evaluation_set = self._sets.get(_text("holdout_set_id", holdout_set_id))
        if evaluation_set is None:
            raise EvaluationFirewallError("unknown promotion holdout")
        if evaluation_set.eval_class != "promotion_holdout":
            raise EvaluationFirewallError("promotion requires promotion_holdout class")
        if evaluation_set.set_id in self._contaminated:
            raise EvaluationFirewallError("contaminated holdout cannot justify promotion")
        evaluator = self._evaluators.get(_text("evaluator_id", evaluator_id))
        if evaluator is None:
            raise EvaluationFirewallError("unknown evaluator")
        receipts = tuple(self._queries.get((candidate, evaluation_set.set_id), ()))
        if not receipts:
            raise EvaluationFirewallError("promotion requires holdout query evidence")
        if any(item.evaluator_identity != evaluator.identity for item in receipts):
            raise EvaluationFirewallError("promotion evaluator identity drift")
        assert evaluation_set.query_budget is not None
        if len(receipts) > evaluation_set.query_budget:
            raise EvaluationFirewallError("holdout query budget exceeded")

        return PromotionEvidence(
            candidate_id=candidate,
            holdout_set_identity=evaluation_set.identity,
            evaluator_identity=evaluator.identity,
            query_receipt_digests=tuple(item.digest for item in receipts),
            holdout_queries_used=len(receipts),
            holdout_query_budget=evaluation_set.query_budget,
        )


__all__ = [
    "EVAL_CLASSES",
    "EvaluationFirewall",
    "EvaluationFirewallError",
    "EvaluationQueryReceipt",
    "EvaluationSet",
    "EvaluatorIdentity",
    "PromotionEvidence",
]
