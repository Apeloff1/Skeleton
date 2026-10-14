"""Provenance-bound explanation runtime for VOL-085.

The explanation plane is deliberately read-only with respect to execution
authority. It can expose recorded decision inputs, rules, receipts, model
outputs, derived summaries and uncertainty, but it cannot manufacture evidence
or promote a post-hoc narrative into provenance fact.

Safety properties:
- every factor is bound to one canonical operation id and a source digest;
- causal/provenance relationships are typed separately from post-hoc summary;
- unsafe/private/internal factors are withheld rather than serialized;
- sensitivity taints downstream derived factors;
- model-output factors require an explicit uncertainty disclosure;
- explanation records bind the exact operation snapshot, policy and factor set;
- content-bearing records are immutable and deterministically ordered;
- public serialization omits internal source references and raw hidden content.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import math
import re
from typing import Iterable, Mapping, Sequence
from uuid import UUID

from skeleton.contracts.operation import OperationEnvelope, OperationState
from skeleton.observability.redaction import REDACTED, redact_text
from skeleton.observability.resilient_telemetry import ReconstructionReceipt

EXPLANATION_SCHEMA = "skeleton.observability.explanation.v1"
_MAX_FACTORS = 2048
_MAX_VISIBLE_FACTORS = 512
_MAX_DEPENDENCY_DEPTH = 64
_MAX_SUMMARY = 4096
_MAX_SOURCE_REF = 1024
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_HIDDEN_SOURCE_MARKERS = (
    "chain_of_thought",
    "chain-of-thought",
    "private_reasoning",
    "private-reasoning",
    "hidden_reasoning",
    "hidden-reasoning",
    "system_prompt",
    "system-prompt",
    "developer_prompt",
    "developer-prompt",
    "raw_secret",
    "raw-secret",
)


class ExplanationError(ValueError):
    """Explanation input or provenance violates the governed contract."""


class DecisionFactorKind(str, Enum):
    OBSERVED_INPUT = "observed_input"
    RULE = "rule"
    TOOL_RECEIPT = "tool_receipt"
    EVIDENCE_RECEIPT = "evidence_receipt"
    MODEL_OUTPUT = "model_output"
    OPERATION_STATE = "operation_state"
    DERIVED_SUMMARY = "derived_summary"
    UNCERTAINTY = "uncertainty"


class FactorRelation(str, Enum):
    DECISION_INPUT = "decision_input"
    SUPPORTING_EVIDENCE = "supporting_evidence"
    POST_HOC_SUMMARY = "post_hoc_summary"
    UNCERTAINTY_DISCLOSURE = "uncertainty_disclosure"


class FactorSensitivity(str, Enum):
    SAFE = "safe"
    PRIVATE = "private"
    SECRET = "secret"
    INTERNAL = "internal"


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise ExplanationError(f"{field} must be a canonical token")
    return value


def _text(
    value: object,
    field: str,
    *,
    maximum: int = _MAX_SUMMARY,
) -> str:
    if not isinstance(value, str):
        raise ExplanationError(f"{field} must be text")
    normalized = value.strip()
    if not normalized or normalized != value or len(normalized) > maximum:
        raise ExplanationError(f"{field} must be normalized bounded text")
    if any(ord(char) < 32 and char not in "\t\n\r" for char in normalized):
        raise ExplanationError(f"{field} contains control characters")
    return normalized


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ExplanationError(f"{field} must be lowercase canonical sha256")
    return value


def _unit(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExplanationError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ExplanationError(f"{field} must be finite within [0, 1]")
    return result


def _positive_int(value: object, field: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExplanationError(f"{field} must be an integer")
    if not 1 <= value <= maximum:
        raise ExplanationError(f"{field} must be within [1, {maximum}]")
    return value


def _canonical_json(value: object, field: str = "payload") -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ExplanationError(f"{field} must be deterministic JSON") from exc


def _digest(value: object, field: str = "payload") -> str:
    return sha256(_canonical_json(value, field)).hexdigest()


def _utc(value: str, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ExplanationError(f"{field} must be RFC3339 UTC")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ExplanationError(f"{field} must be RFC3339 UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExplanationError(f"{field} must be timezone-aware")
    parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _operation_uuid(value: str) -> str:
    try:
        parsed = UUID(value)
    except (ValueError, TypeError) as exc:
        raise ExplanationError("operation_id must be a canonical UUID") from exc
    if str(parsed) != value:
        raise ExplanationError("operation_id must be a canonical UUID")
    return value


def _withheld_label(sensitivity: FactorSensitivity) -> str:
    return f"[WITHHELD:{sensitivity.value.upper()}]"


@dataclass(frozen=True, slots=True)
class OperationProvenance:
    """Exact operation snapshot to which an explanation is bound."""

    operation_id: str
    trace_id: str
    operation_identity_digest: str
    operation_snapshot_digest: str
    state: str
    created_at: str
    deadline: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operation_id",
            _operation_uuid(self.operation_id),
        )
        object.__setattr__(self, "trace_id", _text(self.trace_id, "trace_id", maximum=256))
        object.__setattr__(
            self,
            "operation_identity_digest",
            _sha(self.operation_identity_digest, "operation_identity_digest"),
        )
        object.__setattr__(
            self,
            "operation_snapshot_digest",
            _sha(self.operation_snapshot_digest, "operation_snapshot_digest"),
        )
        try:
            OperationState(self.state)
        except ValueError as exc:
            raise ExplanationError("state is not a canonical operation state") from exc
        object.__setattr__(self, "created_at", _utc(self.created_at, "created_at"))
        object.__setattr__(self, "deadline", _utc(self.deadline, "deadline"))

    @classmethod
    def from_operation(cls, operation: OperationEnvelope) -> "OperationProvenance":
        if not isinstance(operation, OperationEnvelope):
            raise TypeError("operation must be OperationEnvelope")
        payload = operation.as_dict()
        return cls(
            operation_id=operation.operation_id,
            trace_id=operation.trace_id,
            operation_identity_digest=operation.identity_digest,
            operation_snapshot_digest=_digest(payload, "operation snapshot"),
            state=OperationState(operation.state).value,
            created_at=operation.created_at.astimezone(timezone.utc).isoformat(),
            deadline=operation.deadline.astimezone(timezone.utc).isoformat(),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": EXPLANATION_SCHEMA,
                "kind": "operation-provenance",
                "operation_id": self.operation_id,
                "trace_id": self.trace_id,
                "operation_identity_digest": self.operation_identity_digest,
                "operation_snapshot_digest": self.operation_snapshot_digest,
                "state": self.state,
                "created_at": self.created_at,
                "deadline": self.deadline,
            }
        )


@dataclass(frozen=True, slots=True)
class DecisionFactor:
    """One typed contribution or disclosure in an explanation.

    The stored summary is always sanitized. Unsafe factors retain only a
    classification placeholder plus a source digest; raw private/internal
    content is never retained by this contract.
    """

    factor_id: str
    operation_id: str
    kind: DecisionFactorKind
    relation: FactorRelation
    summary: str
    source_ref: str
    source_digest: str
    observed_at: str
    sensitivity: FactorSensitivity = FactorSensitivity.SAFE
    depends_on: tuple[str, ...] = ()
    uncertainty: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "factor_id", _token(self.factor_id, "factor_id"))
        object.__setattr__(
            self,
            "operation_id",
            _operation_uuid(self.operation_id),
        )
        if not isinstance(self.kind, DecisionFactorKind):
            raise ExplanationError("kind must be DecisionFactorKind")
        if not isinstance(self.relation, FactorRelation):
            raise ExplanationError("relation must be FactorRelation")
        if not isinstance(self.sensitivity, FactorSensitivity):
            raise ExplanationError("sensitivity must be FactorSensitivity")

        source_ref = _text(self.source_ref, "source_ref", maximum=_MAX_SOURCE_REF)
        lower_ref = source_ref.casefold()
        lower_id = self.factor_id.casefold()
        sensitivity = self.sensitivity
        if sensitivity is FactorSensitivity.SAFE and any(
            marker in lower_ref or marker in lower_id
            for marker in _HIDDEN_SOURCE_MARKERS
        ):
            sensitivity = FactorSensitivity.INTERNAL
            object.__setattr__(self, "sensitivity", sensitivity)

        raw_summary = _text(self.summary, "summary")
        if sensitivity is FactorSensitivity.SAFE:
            safe_summary = redact_text(raw_summary)
            safe_source_ref = redact_text(source_ref)
        else:
            safe_summary = _withheld_label(sensitivity)
            safe_source_ref = f"withheld:{self.kind.value}"
        object.__setattr__(self, "summary", safe_summary)
        object.__setattr__(self, "source_ref", safe_source_ref)
        object.__setattr__(
            self,
            "source_digest",
            _sha(self.source_digest, "source_digest"),
        )
        object.__setattr__(
            self,
            "observed_at",
            _utc(self.observed_at, "observed_at"),
        )

        if not isinstance(self.depends_on, tuple):
            raise ExplanationError("depends_on must be a tuple")
        normalized_dependencies: list[str] = []
        for dependency in self.depends_on:
            token = _token(dependency, "depends_on")
            if token == self.factor_id:
                raise ExplanationError("factor cannot depend on itself")
            if token in normalized_dependencies:
                raise ExplanationError("duplicate factor dependency")
            normalized_dependencies.append(token)
        object.__setattr__(
            self,
            "depends_on",
            tuple(sorted(normalized_dependencies)),
        )

        if self.relation is FactorRelation.POST_HOC_SUMMARY:
            if self.kind is not DecisionFactorKind.DERIVED_SUMMARY:
                raise ExplanationError(
                    "post_hoc_summary relation requires derived_summary kind"
                )
            if not self.depends_on:
                raise ExplanationError(
                    "post-hoc summary requires explicit factor dependencies"
                )

        if self.kind is DecisionFactorKind.DERIVED_SUMMARY and not self.depends_on:
            raise ExplanationError(
                "derived summary requires explicit factor dependencies"
            )

        if self.kind is DecisionFactorKind.UNCERTAINTY:
            if self.relation is not FactorRelation.UNCERTAINTY_DISCLOSURE:
                raise ExplanationError(
                    "uncertainty kind requires uncertainty_disclosure relation"
                )
            if not self.depends_on:
                raise ExplanationError(
                    "uncertainty disclosure requires factor dependencies"
                )
            if self.uncertainty is None:
                raise ExplanationError(
                    "uncertainty disclosure requires uncertainty value"
                )
            object.__setattr__(
                self,
                "uncertainty",
                _unit(self.uncertainty, "uncertainty"),
            )
        elif self.uncertainty is not None:
            raise ExplanationError(
                "uncertainty value is reserved for uncertainty factors"
            )

        if (
            self.relation is FactorRelation.DECISION_INPUT
            and self.kind
            in {
                DecisionFactorKind.DERIVED_SUMMARY,
                DecisionFactorKind.UNCERTAINTY,
            }
        ):
            raise ExplanationError(
                "derived summary/uncertainty cannot masquerade as decision input"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": EXPLANATION_SCHEMA,
                "kind": "decision-factor",
                "factor_id": self.factor_id,
                "operation_id": self.operation_id,
                "factor_kind": self.kind.value,
                "relation": self.relation.value,
                "summary": self.summary,
                "source_ref": self.source_ref,
                "source_digest": self.source_digest,
                "observed_at": self.observed_at,
                "sensitivity": self.sensitivity.value,
                "depends_on": list(self.depends_on),
                "uncertainty": self.uncertainty,
            }
        )

    def public_dict(self) -> dict[str, object]:
        if self.sensitivity is not FactorSensitivity.SAFE:
            raise ExplanationError("unsafe factor cannot be serialized publicly")
        return {
            "factor_id": self.factor_id,
            "kind": self.kind.value,
            "relation": self.relation.value,
            "summary": self.summary,
            "source_digest": self.source_digest,
            "observed_at": self.observed_at,
            "depends_on": list(self.depends_on),
            "uncertainty": self.uncertainty,
        }

    def audit_dict(self) -> dict[str, object]:
        if self.sensitivity is not FactorSensitivity.SAFE:
            raise ExplanationError("unsafe factor cannot be serialized to audit surface")
        payload = self.public_dict()
        payload["source_ref"] = self.source_ref
        return payload


@dataclass(frozen=True, slots=True)
class ExplanationPolicy:
    policy_id: str
    max_factors: int = 256
    max_visible_factors: int = 128
    max_dependency_depth: int = 32
    require_decision_input: bool = True
    require_uncertainty_for_model_output: bool = True
    allow_post_hoc: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _token(self.policy_id, "policy_id"))
        object.__setattr__(
            self,
            "max_factors",
            _positive_int(self.max_factors, "max_factors", _MAX_FACTORS),
        )
        object.__setattr__(
            self,
            "max_visible_factors",
            _positive_int(
                self.max_visible_factors,
                "max_visible_factors",
                _MAX_VISIBLE_FACTORS,
            ),
        )
        if self.max_visible_factors > self.max_factors:
            raise ExplanationError(
                "max_visible_factors cannot exceed max_factors"
            )
        object.__setattr__(
            self,
            "max_dependency_depth",
            _positive_int(
                self.max_dependency_depth,
                "max_dependency_depth",
                _MAX_DEPENDENCY_DEPTH,
            ),
        )
        for field in (
            "require_decision_input",
            "require_uncertainty_for_model_output",
            "allow_post_hoc",
        ):
            if not isinstance(getattr(self, field), bool):
                raise ExplanationError(f"{field} must be boolean")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": EXPLANATION_SCHEMA,
                "kind": "explanation-policy",
                "policy_id": self.policy_id,
                "max_factors": self.max_factors,
                "max_visible_factors": self.max_visible_factors,
                "max_dependency_depth": self.max_dependency_depth,
                "require_decision_input": self.require_decision_input,
                "require_uncertainty_for_model_output": (
                    self.require_uncertainty_for_model_output
                ),
                "allow_post_hoc": self.allow_post_hoc,
            }
        )


@dataclass(frozen=True, slots=True)
class ExplanationRecord:
    explanation_id: str
    decision_id: str
    provenance: OperationProvenance
    policy_id: str
    policy_digest: str
    generated_at: str
    outcome_summary: str
    factors: tuple[DecisionFactor, ...]
    withheld_factor_digests: tuple[str, ...]
    factor_set_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "explanation_id",
            _token(self.explanation_id, "explanation_id"),
        )
        object.__setattr__(self, "decision_id", _token(self.decision_id, "decision_id"))
        if not isinstance(self.provenance, OperationProvenance):
            raise ExplanationError("provenance must be OperationProvenance")
        object.__setattr__(self, "policy_id", _token(self.policy_id, "policy_id"))
        object.__setattr__(
            self,
            "policy_digest",
            _sha(self.policy_digest, "policy_digest"),
        )
        object.__setattr__(
            self,
            "generated_at",
            _utc(self.generated_at, "generated_at"),
        )
        summary = redact_text(_text(self.outcome_summary, "outcome_summary"))
        object.__setattr__(self, "outcome_summary", summary)

        if not isinstance(self.factors, tuple):
            raise ExplanationError("factors must be a tuple")
        ids: set[str] = set()
        previous_id = ""
        for factor in self.factors:
            if not isinstance(factor, DecisionFactor):
                raise ExplanationError("factors must contain DecisionFactor")
            if factor.sensitivity is not FactorSensitivity.SAFE:
                raise ExplanationError("visible factors must be safe")
            if factor.operation_id != self.provenance.operation_id:
                raise ExplanationError("factor operation identity mismatch")
            if factor.factor_id in ids:
                raise ExplanationError("duplicate visible factor identity")
            if previous_id and factor.factor_id < previous_id:
                raise ExplanationError("visible factors must be canonically ordered")
            previous_id = factor.factor_id
            ids.add(factor.factor_id)

        if not isinstance(self.withheld_factor_digests, tuple):
            raise ExplanationError("withheld_factor_digests must be a tuple")
        normalized_withheld: list[str] = []
        for digest in self.withheld_factor_digests:
            normalized_withheld.append(_sha(digest, "withheld_factor_digest"))
        if len(normalized_withheld) != len(set(normalized_withheld)):
            raise ExplanationError("duplicate withheld factor digest")
        if tuple(sorted(normalized_withheld)) != self.withheld_factor_digests:
            raise ExplanationError(
                "withheld_factor_digests must be canonically ordered"
            )

        object.__setattr__(
            self,
            "factor_set_digest",
            _sha(self.factor_set_digest, "factor_set_digest"),
        )
        expected_factor_set = _digest(
            {
                "visible": [factor.digest for factor in self.factors],
                "withheld": list(self.withheld_factor_digests),
            },
            "factor set",
        )
        if expected_factor_set != self.factor_set_digest:
            raise ExplanationError(
                "factor_set_digest does not bind visible and withheld factors"
            )
        expected_explanation_id = "explanation-" + _digest(
            {
                "schema": EXPLANATION_SCHEMA,
                "operation_snapshot_digest": (
                    self.provenance.operation_snapshot_digest
                ),
                "decision_id": self.decision_id,
                "policy_digest": self.policy_digest,
                "generated_at": self.generated_at,
                "outcome_summary": self.outcome_summary,
                "factor_set_digest": self.factor_set_digest,
            },
            "explanation identity",
        )[:32]
        if self.explanation_id != expected_explanation_id:
            raise ExplanationError(
                "explanation_id does not bind record content"
            )

    @property
    def withheld_factor_count(self) -> int:
        return len(self.withheld_factor_digests)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": EXPLANATION_SCHEMA,
                "kind": "explanation-record",
                "explanation_id": self.explanation_id,
                "decision_id": self.decision_id,
                "provenance_digest": self.provenance.digest,
                "policy_id": self.policy_id,
                "policy_digest": self.policy_digest,
                "generated_at": self.generated_at,
                "outcome_summary": self.outcome_summary,
                "factor_set_digest": self.factor_set_digest,
            }
        )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "schema": EXPLANATION_SCHEMA,
            "explanation_id": self.explanation_id,
            "decision_id": self.decision_id,
            "operation_id": self.provenance.operation_id,
            "operation_state": self.provenance.state,
            "operation_snapshot_digest": self.provenance.operation_snapshot_digest,
            "policy_id": self.policy_id,
            "generated_at": self.generated_at,
            "outcome_summary": self.outcome_summary,
            "factors": [factor.public_dict() for factor in self.factors],
            "withheld_factor_count": self.withheld_factor_count,
            "factor_set_digest": self.factor_set_digest,
            "record_digest": self.digest,
        }

    def to_audit_dict(self) -> dict[str, object]:
        payload = self.to_public_dict()
        payload["operation_identity_digest"] = (
            self.provenance.operation_identity_digest
        )
        payload["trace_id"] = self.provenance.trace_id
        payload["policy_digest"] = self.policy_digest
        payload["withheld_factor_digests"] = list(
            self.withheld_factor_digests
        )
        payload["factors"] = [factor.audit_dict() for factor in self.factors]
        return payload


class ExplanationBuilder:
    """Deterministic materializer for operation-bound explanations."""

    @staticmethod
    def _validate_graph(
        factors: Mapping[str, DecisionFactor],
        *,
        max_depth: int,
    ) -> None:
        state: dict[str, int] = {}
        depth_cache: dict[str, int] = {}

        def visit(factor_id: str) -> int:
            phase = state.get(factor_id, 0)
            if phase == 1:
                raise ExplanationError(
                    f"factor dependency cycle at {factor_id}"
                )
            if phase == 2:
                return depth_cache[factor_id]
            state[factor_id] = 1
            factor = factors[factor_id]
            depth = 1
            for dependency in factor.depends_on:
                if dependency not in factors:
                    raise ExplanationError(
                        f"{factor_id} references unknown dependency {dependency}"
                    )
                depth = max(depth, 1 + visit(dependency))
            if depth > max_depth:
                raise ExplanationError(
                    "factor dependency depth exceeds policy bound"
                )
            state[factor_id] = 2
            depth_cache[factor_id] = depth
            return depth

        for factor_id in sorted(factors):
            visit(factor_id)

    @staticmethod
    def _tainted_ids(
        factors: Mapping[str, DecisionFactor],
    ) -> frozenset[str]:
        tainted = {
            factor.factor_id
            for factor in factors.values()
            if factor.sensitivity is not FactorSensitivity.SAFE
        }
        changed = True
        while changed:
            changed = False
            for factor in factors.values():
                if factor.factor_id in tainted:
                    continue
                if any(dependency in tainted for dependency in factor.depends_on):
                    tainted.add(factor.factor_id)
                    changed = True
        return frozenset(tainted)

    @staticmethod
    def _require_model_uncertainty(
        factors: Mapping[str, DecisionFactor],
    ) -> None:
        uncertainty_factors = tuple(
            factor
            for factor in factors.values()
            if factor.kind is DecisionFactorKind.UNCERTAINTY
        )
        for model_factor in factors.values():
            if model_factor.kind is not DecisionFactorKind.MODEL_OUTPUT:
                continue
            if not any(
                model_factor.factor_id in disclosure.depends_on
                for disclosure in uncertainty_factors
            ):
                raise ExplanationError(
                    f"model output {model_factor.factor_id} lacks uncertainty disclosure"
                )

    def build(
        self,
        *,
        operation: OperationEnvelope,
        decision_id: str,
        outcome_summary: str,
        factors: Iterable[DecisionFactor],
        policy: ExplanationPolicy,
        generated_at: str,
    ) -> ExplanationRecord:
        if not isinstance(operation, OperationEnvelope):
            raise TypeError("operation must be OperationEnvelope")
        if not isinstance(policy, ExplanationPolicy):
            raise TypeError("policy must be ExplanationPolicy")
        decision_id = _token(decision_id, "decision_id")
        generated = _utc(generated_at, "generated_at")
        outcome = redact_text(_text(outcome_summary, "outcome_summary"))

        materialized = tuple(factors)
        if not materialized:
            raise ExplanationError("explanation requires at least one factor")
        if len(materialized) > policy.max_factors:
            raise ExplanationError("explanation factor count exceeds policy")

        by_id: dict[str, DecisionFactor] = {}
        for factor in materialized:
            if not isinstance(factor, DecisionFactor):
                raise TypeError("factors must contain DecisionFactor")
            if factor.operation_id != operation.operation_id:
                raise ExplanationError("factor belongs to another operation")
            if factor.observed_at > generated:
                raise ExplanationError(
                    "factor observation cannot occur after explanation generation"
                )
            if factor.factor_id in by_id:
                raise ExplanationError("duplicate factor identity")
            by_id[factor.factor_id] = factor

        self._validate_graph(
            by_id,
            max_depth=policy.max_dependency_depth,
        )

        if (
            not policy.allow_post_hoc
            and any(
                factor.relation is FactorRelation.POST_HOC_SUMMARY
                for factor in materialized
            )
        ):
            raise ExplanationError("policy forbids post-hoc summary factors")

        if policy.require_decision_input and not any(
            factor.relation is FactorRelation.DECISION_INPUT
            for factor in materialized
        ):
            raise ExplanationError(
                "policy requires at least one recorded decision input"
            )

        if policy.require_uncertainty_for_model_output:
            self._require_model_uncertainty(by_id)

        tainted = set(self._tainted_ids(by_id))
        if policy.require_uncertainty_for_model_output:
            changed = True
            while changed:
                changed = False
                for model_factor in by_id.values():
                    if (
                        model_factor.kind is not DecisionFactorKind.MODEL_OUTPUT
                        or model_factor.factor_id in tainted
                    ):
                        continue
                    disclosures = tuple(
                        disclosure
                        for disclosure in by_id.values()
                        if (
                            disclosure.kind is DecisionFactorKind.UNCERTAINTY
                            and model_factor.factor_id in disclosure.depends_on
                        )
                    )
                    if disclosures and all(
                        disclosure.factor_id in tainted
                        for disclosure in disclosures
                    ):
                        tainted.add(model_factor.factor_id)
                        changed = True
                for candidate in by_id.values():
                    if candidate.factor_id in tainted:
                        continue
                    if any(
                        dependency in tainted
                        for dependency in candidate.depends_on
                    ):
                        tainted.add(candidate.factor_id)
                        changed = True

        visible = tuple(
            sorted(
                (
                    factor
                    for factor in materialized
                    if factor.factor_id not in tainted
                ),
                key=lambda factor: factor.factor_id,
            )
        )
        if len(visible) > policy.max_visible_factors:
            raise ExplanationError(
                "visible factor count exceeds policy; refusing silent truncation"
            )

        visible_ids = {factor.factor_id for factor in visible}
        for factor in visible:
            hidden_dependencies = [
                dependency
                for dependency in factor.depends_on
                if dependency not in visible_ids
            ]
            if hidden_dependencies:
                raise ExplanationError(
                    "visible factor depends on withheld factor"
                )

        withheld = tuple(
            sorted(
                by_id[factor_id].digest
                for factor_id in tainted
            )
        )
        factor_set_digest = _digest(
            {
                "visible": [factor.digest for factor in visible],
                "withheld": list(withheld),
            },
            "factor set",
        )
        provenance = OperationProvenance.from_operation(operation)
        explanation_id = "explanation-" + _digest(
            {
                "schema": EXPLANATION_SCHEMA,
                "operation_snapshot_digest": (
                    provenance.operation_snapshot_digest
                ),
                "decision_id": decision_id,
                "policy_digest": policy.digest,
                "generated_at": generated,
                "outcome_summary": outcome,
                "factor_set_digest": factor_set_digest,
            },
            "explanation identity",
        )[:32]

        record = ExplanationRecord(
            explanation_id=explanation_id,
            decision_id=decision_id,
            provenance=provenance,
            policy_id=policy.policy_id,
            policy_digest=policy.digest,
            generated_at=generated,
            outcome_summary=outcome,
            factors=visible,
            withheld_factor_digests=withheld,
            factor_set_digest=factor_set_digest,
        )
        self.verify(
            record=record,
            operation=operation,
            policy=policy,
        )
        return record

    def verify(
        self,
        *,
        record: ExplanationRecord,
        operation: OperationEnvelope,
        policy: ExplanationPolicy,
    ) -> None:
        if not isinstance(record, ExplanationRecord):
            raise TypeError("record must be ExplanationRecord")
        if not isinstance(operation, OperationEnvelope):
            raise TypeError("operation must be OperationEnvelope")
        if not isinstance(policy, ExplanationPolicy):
            raise TypeError("policy must be ExplanationPolicy")

        expected_provenance = OperationProvenance.from_operation(operation)
        if record.provenance != expected_provenance:
            raise ExplanationError(
                "explanation no longer matches exact operation provenance"
            )
        if record.policy_id != policy.policy_id:
            raise ExplanationError("explanation policy identity mismatch")
        if record.policy_digest != policy.digest:
            raise ExplanationError("explanation policy digest mismatch")
        if len(record.factors) > policy.max_visible_factors:
            raise ExplanationError("record exceeds visible factor policy")
        if (
            not policy.allow_post_hoc
            and any(
                factor.relation is FactorRelation.POST_HOC_SUMMARY
                for factor in record.factors
            )
        ):
            raise ExplanationError("record contains policy-forbidden post-hoc factor")
        if policy.require_decision_input and not (
            any(
                factor.relation is FactorRelation.DECISION_INPUT
                for factor in record.factors
            )
            or record.withheld_factor_count > 0
        ):
            raise ExplanationError("record lacks decision-input evidence")
        if policy.require_uncertainty_for_model_output:
            visible_by_id = {
                factor.factor_id: factor
                for factor in record.factors
            }
            visible_model = any(
                factor.kind is DecisionFactorKind.MODEL_OUTPUT
                for factor in record.factors
            )
            if visible_model:
                self._require_model_uncertainty(visible_by_id)


class ExplanationLedger:
    """Bounded append-only explanation ledger keyed by content identity."""

    def __init__(self, *, max_records: int = 4096) -> None:
        self.max_records = _positive_int(
            max_records,
            "max_records",
            100_000,
        )
        self._records: dict[str, ExplanationRecord] = {}
        self._operation_index: dict[str, list[str]] = {}

    def append(self, record: ExplanationRecord) -> ExplanationRecord:
        if not isinstance(record, ExplanationRecord):
            raise TypeError("record must be ExplanationRecord")
        existing = self._records.get(record.explanation_id)
        if existing is not None:
            if existing == record:
                return existing
            raise ExplanationError("explanation identity collision")
        if len(self._records) >= self.max_records:
            raise ExplanationError("explanation ledger capacity reached")
        self._records[record.explanation_id] = record
        self._operation_index.setdefault(
            record.provenance.operation_id,
            [],
        ).append(record.explanation_id)
        return record

    def get(self, explanation_id: str) -> ExplanationRecord:
        normalized = _token(explanation_id, "explanation_id")
        try:
            return self._records[normalized]
        except KeyError as exc:
            raise ExplanationError(
                f"unknown explanation {normalized}"
            ) from exc

    def for_operation(
        self,
        operation_id: str,
    ) -> tuple[ExplanationRecord, ...]:
        normalized = _operation_uuid(operation_id)
        return tuple(
            self._records[record_id]
            for record_id in self._operation_index.get(normalized, ())
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": EXPLANATION_SCHEMA,
                "kind": "explanation-ledger",
                "records": [
                    self._records[key].digest
                    for key in sorted(self._records)
                ],
            }
        )


def factor_from_reconstruction_receipt(
    *,
    operation: OperationEnvelope,
    factor_id: str,
    receipt: ReconstructionReceipt,
    summary: str,
    observed_at: str,
    relation: FactorRelation = FactorRelation.SUPPORTING_EVIDENCE,
    sensitivity: FactorSensitivity = FactorSensitivity.SAFE,
) -> DecisionFactor:
    """Bind an explanation factor to an existing observability receipt."""

    if not isinstance(operation, OperationEnvelope):
        raise TypeError("operation must be OperationEnvelope")
    if not isinstance(receipt, ReconstructionReceipt):
        raise TypeError("receipt must be ReconstructionReceipt")
    return DecisionFactor(
        factor_id=factor_id,
        operation_id=operation.operation_id,
        kind=DecisionFactorKind.EVIDENCE_RECEIPT,
        relation=relation,
        summary=summary,
        source_ref=f"telemetry:{receipt.kind}:{receipt.sequence}",
        source_digest=receipt.event_digest,
        observed_at=observed_at,
        sensitivity=sensitivity,
    )


def source_digest(value: object) -> str:
    """Create a canonical digest for JSON-shaped source evidence.

    Callers should pass already-authorized evidence, not hidden prompts or raw
    private payloads. This helper exists to make source identity deterministic;
    it does not make the source safe for disclosure.
    """

    return _digest(value, "source evidence")


__all__ = [
    "EXPLANATION_SCHEMA",
    "DecisionFactor",
    "DecisionFactorKind",
    "ExplanationBuilder",
    "ExplanationError",
    "ExplanationLedger",
    "ExplanationPolicy",
    "ExplanationRecord",
    "FactorRelation",
    "FactorSensitivity",
    "OperationProvenance",
    "factor_from_reconstruction_receipt",
    "source_digest",
]
