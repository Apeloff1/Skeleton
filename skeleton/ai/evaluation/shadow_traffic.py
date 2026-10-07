"""P1 shadow-traffic isolation and paired comparison evidence.

Shadow execution is measurement-only. It may observe a redacted digest-bound
copy of eligible production traffic, but it cannot write canonical state,
produce user-visible output, promote a candidate, or widen privacy boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Iterable

from skeleton.agents.blast_radius import (
    ActionRiskProfile,
    BlastRadiusDecision,
    ReversibilityClass,
)
from skeleton.contracts.canonical import EvidenceRef
from skeleton.eval.champion_registry import (
    CandidateArtifact,
    ChampionRegistry,
)
from skeleton.eval.experiment_registry import (
    ExperimentManifest,
    TrafficMode,
)


SHADOW_TRAFFIC_SCHEMA_VERSION = 1
SHADOW_TRAFFIC_TASK_ID = "P1-LEARN-04"
SHADOW_TRAFFIC_ACCOUNTABILITY_ID = "ACC-P1-LEARN-04"
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,191}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ShadowTrafficError(ValueError):
    """Shadow-traffic input violates isolation policy."""


def _token(value: object, field: str, *, maximum: int = 192) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or not _TOKEN_RE.fullmatch(value)
    ):
        raise ShadowTrafficError(f"{field} must be a canonical token")
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ShadowTrafficError(f"{field} must be lowercase sha256")
    return value


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ShadowTrafficError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ShadowTrafficError(f"{field} must be finite numeric")
    return result


def _canonical_digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ShadowTrafficError(
            "shadow payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _tokens(
    values: Iterable[str],
    field: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ShadowTrafficError(f"{field} must be an iterable")
    result = tuple(sorted({_token(item, field) for item in values}))
    if not allow_empty and not result:
        raise ShadowTrafficError(f"{field} must be non-empty")
    return result


@dataclass(frozen=True, slots=True)
class ShadowSourceAuthority:
    operation_id: str
    tenant_id: str
    operation_projection_digest: str
    projection_decision_digest: str
    operation_version: int
    cursor_sequence: int
    evidence: EvidenceRef

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "operation_id", _token(self.operation_id, "operation_id")
        )
        object.__setattr__(
            self, "tenant_id", _token(self.tenant_id, "tenant_id")
        )
        for field in (
            "operation_projection_digest",
            "projection_decision_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        for field in ("operation_version", "cursor_sequence"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ShadowTrafficError(f"{field} must be positive integer")
        if not isinstance(self.evidence, EvidenceRef):
            raise ShadowTrafficError("evidence must be EvidenceRef")
        if self.evidence.category != "streaming_projection_authority":
            raise ShadowTrafficError(
                "source evidence must be PROD-02 projection authority"
            )
        _sha256(self.evidence.digest, "evidence.digest")
        if self.evidence.digest != self.projection_decision_digest:
            raise ShadowTrafficError(
                "source evidence digest must equal projection decision digest"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "tenant_id": self.tenant_id,
            "operation_projection_digest": self.operation_projection_digest,
            "projection_decision_digest": self.projection_decision_digest,
            "operation_version": self.operation_version,
            "cursor_sequence": self.cursor_sequence,
            "evidence": {
                "source": self.evidence.source,
                "digest": self.evidence.digest,
                "category": self.evidence.category,
            },
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class ShadowInputReceipt:
    original_input_digest: str
    redacted_input_digest: str
    redaction_policy_digest: str
    data_class: str
    sensitive_input: bool
    removed_classes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field in (
            "original_input_digest",
            "redacted_input_digest",
            "redaction_policy_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "data_class",
            _token(self.data_class, "data_class", maximum=96),
        )
        if not isinstance(self.sensitive_input, bool):
            raise ShadowTrafficError("sensitive_input must be boolean")
        object.__setattr__(
            self,
            "removed_classes",
            _tokens(self.removed_classes, "removed_classes"),
        )
        if self.sensitive_input:
            if not self.removed_classes:
                raise ShadowTrafficError(
                    "sensitive input requires explicit removed classes"
                )
            if self.original_input_digest == self.redacted_input_digest:
                raise ShadowTrafficError(
                    "sensitive input must change under redaction"
                )
        elif self.removed_classes:
            raise ShadowTrafficError(
                "non-sensitive input cannot claim removed classes"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "original_input_digest": self.original_input_digest,
            "redacted_input_digest": self.redacted_input_digest,
            "redaction_policy_digest": self.redaction_policy_digest,
            "data_class": self.data_class,
            "sensitive_input": self.sensitive_input,
            "removed_classes": list(self.removed_classes),
            "raw_payload_present": False,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class ShadowPolicy:
    policy_id: str
    version: int
    max_traffic_fraction: float = 0.05
    allow_persistent_writes: bool = False
    allow_external_side_effects: bool = False
    allow_user_visible_output: bool = False
    allow_privileged_tools: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_id",
            _token(self.policy_id, "policy_id"),
        )
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ShadowTrafficError("version must be positive integer")
        fraction = _finite(self.max_traffic_fraction, "max_traffic_fraction")
        if fraction <= 0.0 or fraction > 0.25:
            raise ShadowTrafficError(
                "max_traffic_fraction must be within (0, 0.25]"
            )
        object.__setattr__(self, "max_traffic_fraction", fraction)
        for field in (
            "allow_persistent_writes",
            "allow_external_side_effects",
            "allow_user_visible_output",
            "allow_privileged_tools",
        ):
            if getattr(self, field) is not False:
                raise ShadowTrafficError(
                    f"{field} must remain false for P1 shadow traffic"
                )

    def payload(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "max_traffic_fraction": self.max_traffic_fraction,
            "allow_persistent_writes": self.allow_persistent_writes,
            "allow_external_side_effects": self.allow_external_side_effects,
            "allow_user_visible_output": self.allow_user_visible_output,
            "allow_privileged_tools": self.allow_privileged_tools,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class PairedShadowObservation:
    experiment_manifest_digest: str
    candidate_digest: str
    source_authority_digest: str
    shadow_input_digest: str
    champion_output_digest: str
    challenger_output_digest: str
    comparator_id: str
    comparator_digest: str
    champion_latency_ms: float
    challenger_latency_ms: float
    registry_digest_before: str
    registry_digest_after: str
    champion_digest_before: str
    champion_digest_after: str
    production_response_before_digest: str
    production_response_after_digest: str
    evaluator_id: str
    evaluator_digest: str
    independent: bool = True
    persistent_write_count: int = 0
    external_side_effect_count: int = 0
    shadow_selected_for_production: bool = False
    user_visible_output: bool = False
    canonical_write_count: int = 0

    def __post_init__(self) -> None:
        for field in (
            "experiment_manifest_digest",
            "candidate_digest",
            "source_authority_digest",
            "shadow_input_digest",
            "champion_output_digest",
            "challenger_output_digest",
            "comparator_digest",
            "registry_digest_before",
            "registry_digest_after",
            "champion_digest_before",
            "champion_digest_after",
            "production_response_before_digest",
            "production_response_after_digest",
            "evaluator_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "comparator_id",
            _token(self.comparator_id, "comparator_id"),
        )
        object.__setattr__(
            self,
            "evaluator_id",
            _token(self.evaluator_id, "evaluator_id"),
        )
        for field in ("champion_latency_ms", "challenger_latency_ms"):
            value = _finite(getattr(self, field), field)
            if value < 0:
                raise ShadowTrafficError(f"{field} must be non-negative")
            object.__setattr__(self, field, value)
        if not isinstance(self.independent, bool):
            raise ShadowTrafficError("independent must be boolean")
        for field in (
            "persistent_write_count",
            "external_side_effect_count",
        ):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ShadowTrafficError(
                    f"{field} must be a non-negative integer"
                )
        if not isinstance(self.shadow_selected_for_production, bool):
            raise ShadowTrafficError(
                "shadow_selected_for_production must be boolean"
            )
        if not isinstance(self.user_visible_output, bool):
            raise ShadowTrafficError("user_visible_output must be boolean")
        if (
            isinstance(self.canonical_write_count, bool)
            or not isinstance(self.canonical_write_count, int)
            or self.canonical_write_count != 0
        ):
            raise ShadowTrafficError(
                "shadow execution cannot write canonical state"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "candidate_digest": self.candidate_digest,
            "source_authority_digest": self.source_authority_digest,
            "shadow_input_digest": self.shadow_input_digest,
            "champion_output_digest": self.champion_output_digest,
            "challenger_output_digest": self.challenger_output_digest,
            "comparator_id": self.comparator_id,
            "comparator_digest": self.comparator_digest,
            "champion_latency_ms": self.champion_latency_ms,
            "challenger_latency_ms": self.challenger_latency_ms,
            "registry_digest_before": self.registry_digest_before,
            "registry_digest_after": self.registry_digest_after,
            "champion_digest_before": self.champion_digest_before,
            "champion_digest_after": self.champion_digest_after,
            "production_response_before_digest": (
                self.production_response_before_digest
            ),
            "production_response_after_digest": (
                self.production_response_after_digest
            ),
            "evaluator_id": self.evaluator_id,
            "evaluator_digest": self.evaluator_digest,
            "independent": self.independent,
            "persistent_write_count": self.persistent_write_count,
            "external_side_effect_count": self.external_side_effect_count,
            "shadow_selected_for_production": self.shadow_selected_for_production,
            "user_visible_output": self.user_visible_output,
            "canonical_write_count": self.canonical_write_count,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class ShadowQualificationDecision:
    accepted: bool
    reasons: tuple[str, ...]
    experiment_manifest_digest: str
    candidate_digest: str
    champion_registry_digest: str
    source_authority_digest: str
    input_receipt_digest: str
    blast_radius_digest: str
    observation_digest: str
    policy_digest: str
    task_id: str = SHADOW_TRAFFIC_TASK_ID
    accountability_id: str = SHADOW_TRAFFIC_ACCOUNTABILITY_ID
    schema_version: int = SHADOW_TRAFFIC_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise ShadowTrafficError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise ShadowTrafficError(
                "reasons must contain non-empty strings"
            )
        for field in (
            "experiment_manifest_digest",
            "candidate_digest",
            "champion_registry_digest",
            "source_authority_digest",
            "input_receipt_digest",
            "blast_radius_digest",
            "observation_digest",
            "policy_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        if self.task_id != SHADOW_TRAFFIC_TASK_ID:
            raise ShadowTrafficError("task_id drift")
        if self.accountability_id != SHADOW_TRAFFIC_ACCOUNTABILITY_ID:
            raise ShadowTrafficError("accountability_id drift")
        if self.schema_version != SHADOW_TRAFFIC_SCHEMA_VERSION:
            raise ShadowTrafficError("unsupported decision schema")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "experiment_manifest_digest": self.experiment_manifest_digest,
            "candidate_digest": self.candidate_digest,
            "champion_registry_digest": self.champion_registry_digest,
            "source_authority_digest": self.source_authority_digest,
            "input_receipt_digest": self.input_receipt_digest,
            "blast_radius_digest": self.blast_radius_digest,
            "observation_digest": self.observation_digest,
            "policy_digest": self.policy_digest,
            "production_authority": False,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(self) -> EvidenceRef:
        if not self.accepted:
            raise ShadowTrafficError(
                "rejected shadow run cannot become promotion evidence"
            )
        return EvidenceRef(
            source=f"p1:learn-04:shadow:{self.candidate_digest}",
            digest=self.decision_digest,
            category="shadow_traffic_qualification",
        )


def qualify_shadow_traffic(
    *,
    experiment: ExperimentManifest,
    registry: ChampionRegistry,
    candidate: CandidateArtifact,
    source: ShadowSourceAuthority,
    shadow_input: ShadowInputReceipt,
    action_profile: ActionRiskProfile,
    blast_radius: BlastRadiusDecision,
    observation: PairedShadowObservation,
    policy: ShadowPolicy,
    requested_fraction: float,
) -> ShadowQualificationDecision:
    if not isinstance(experiment, ExperimentManifest):
        raise TypeError("experiment must be ExperimentManifest")
    if not isinstance(registry, ChampionRegistry):
        raise TypeError("registry must be ChampionRegistry")
    if not isinstance(candidate, CandidateArtifact):
        raise TypeError("candidate must be CandidateArtifact")
    if not isinstance(source, ShadowSourceAuthority):
        raise TypeError("source must be ShadowSourceAuthority")
    if not isinstance(shadow_input, ShadowInputReceipt):
        raise TypeError("shadow_input must be ShadowInputReceipt")
    if not isinstance(action_profile, ActionRiskProfile):
        raise TypeError("action_profile must be ActionRiskProfile")
    if not isinstance(blast_radius, BlastRadiusDecision):
        raise TypeError("blast_radius must be BlastRadiusDecision")
    if not isinstance(observation, PairedShadowObservation):
        raise TypeError("observation must be PairedShadowObservation")
    if not isinstance(policy, ShadowPolicy):
        raise TypeError("policy must be ShadowPolicy")

    reasons: list[str] = []
    if experiment.eligibility.traffic_mode is not TrafficMode.SHADOW:
        reasons.append("experiment-not-shadow-mode")
    if experiment.eligibility.external_side_effects_allowed:
        reasons.append("experiment-allows-external-side-effects")
    if candidate.candidate_ref != experiment.candidate_ref:
        reasons.append("experiment-candidate-ref-mismatch")
    if candidate.experiment_manifest_digest != experiment.manifest_digest:
        reasons.append("candidate-experiment-digest-mismatch")
    if shadow_input.data_class not in experiment.eligibility.allowed_data_classes:
        reasons.append("shadow-data-class-not-eligible")
    if (
        experiment.eligibility.tenant_ids
        and source.tenant_id not in experiment.eligibility.tenant_ids
    ):
        reasons.append("shadow-tenant-not-eligible")

    registered = {
        item.candidate_digest for item in registry.candidates
    }
    if candidate.candidate_digest not in registered:
        reasons.append("candidate-not-registered")
    if candidate.candidate_digest == registry.current_champion_digest:
        reasons.append("shadow-candidate-is-current-champion")

    fraction = _finite(requested_fraction, "requested_fraction")
    if fraction <= 0.0 or fraction > policy.max_traffic_fraction:
        reasons.append("shadow-fraction-out-of-policy")
    if fraction > experiment.eligibility.max_traffic_fraction:
        reasons.append("shadow-fraction-exceeds-experiment")

    if action_profile.operation_id != source.operation_id:
        reasons.append("action-operation-mismatch")
    if action_profile.writes_persistent_state:
        reasons.append("persistent-write-requested")
    if action_profile.externally_observable:
        reasons.append("external-side-effect-requested")
    if action_profile.privileged:
        reasons.append("privileged-action-requested")
    if action_profile.destructive:
        reasons.append("destructive-action-requested")
    if action_profile.sensitive_data:
        reasons.append("sensitive-data-action-requested")
    if action_profile.reversibility is not ReversibilityClass.REVERSIBLE:
        reasons.append("shadow-action-not-reversible")

    if not blast_radius.accepted:
        reasons.append("blast-radius-rejected")
    if blast_radius.operation_id != action_profile.operation_id:
        reasons.append("blast-operation-mismatch")
    if blast_radius.action_digest != action_profile.action_digest:
        reasons.append("blast-action-digest-mismatch")
    if blast_radius.authority_digest != action_profile.authority_digest:
        reasons.append("blast-authority-digest-mismatch")

    if observation.experiment_manifest_digest != experiment.manifest_digest:
        reasons.append("observation-experiment-digest-mismatch")
    if observation.candidate_digest != candidate.candidate_digest:
        reasons.append("observation-candidate-mismatch")
    if observation.source_authority_digest != source.digest:
        reasons.append("observation-source-mismatch")
    if observation.shadow_input_digest != shadow_input.digest:
        reasons.append("observation-input-mismatch")
    if observation.registry_digest_before != registry.registry_digest:
        reasons.append("registry-before-digest-mismatch")
    if observation.registry_digest_after != registry.registry_digest:
        reasons.append("registry-after-digest-mismatch")
    if observation.registry_digest_before != observation.registry_digest_after:
        reasons.append("shadow-mutated-registry")
    if observation.champion_digest_before != registry.current_champion_digest:
        reasons.append("champion-before-digest-mismatch")
    if observation.champion_digest_after != registry.current_champion_digest:
        reasons.append("champion-after-digest-mismatch")
    if observation.champion_digest_before != observation.champion_digest_after:
        reasons.append("shadow-mutated-champion")
    if (
        observation.production_response_before_digest
        != observation.production_response_after_digest
    ):
        reasons.append("production-response-mutated")
    if observation.persistent_write_count:
        reasons.append("shadow-persistent-write-detected")
    if observation.external_side_effect_count:
        reasons.append("shadow-external-side-effect-detected")
    if observation.shadow_selected_for_production:
        reasons.append("shadow-output-selected-for-production")
    if observation.user_visible_output:
        reasons.append("shadow-output-user-visible")
    if observation.canonical_write_count:
        reasons.append("shadow-canonical-write-detected")
    if not observation.independent:
        reasons.append("shadow-evaluator-not-independent")
    if observation.evaluator_id == action_profile.agent_id:
        reasons.append("shadow-evaluator-is-agent")

    normalized = tuple(sorted(set(reasons)))
    return ShadowQualificationDecision(
        accepted=not normalized,
        reasons=normalized,
        experiment_manifest_digest=experiment.manifest_digest,
        candidate_digest=candidate.candidate_digest,
        champion_registry_digest=registry.registry_digest,
        source_authority_digest=source.digest,
        input_receipt_digest=shadow_input.digest,
        blast_radius_digest=blast_radius.decision_digest,
        observation_digest=observation.digest,
        policy_digest=policy.digest,
    )


__all__ = [
    "SHADOW_TRAFFIC_ACCOUNTABILITY_ID",
    "SHADOW_TRAFFIC_SCHEMA_VERSION",
    "SHADOW_TRAFFIC_TASK_ID",
    "PairedShadowObservation",
    "ShadowInputReceipt",
    "ShadowPolicy",
    "ShadowQualificationDecision",
    "ShadowSourceAuthority",
    "ShadowTrafficError",
    "qualify_shadow_traffic",
]
