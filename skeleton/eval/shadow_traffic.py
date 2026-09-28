"""P1 shadow-traffic isolation and non-interference qualification.

Shadow evaluation is observation-only. It may copy an eligible production input
to a registered challenger and emit evaluation evidence, but it may not commit
persistent writes, emit external side effects, mutate champion/challenger
registry state, replace the production response, or acquire production
authority.

The contract joins LEARN-01 experiment eligibility, LEARN-03 immutable
champion/challenger identity, and accepted AUTO-05 blast-radius evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Iterable

from skeleton.agents.blast_radius import BlastRadiusDecision, ImpactClass
from skeleton.contracts.canonical import EvidenceRef, evidence_ref_identity
from skeleton.eval.champion_registry import CandidateArtifact, ChampionRegistry
from skeleton.eval.experiment_registry import ExperimentManifest, TrafficMode


SHADOW_TRAFFIC_SCHEMA_VERSION = 1
SHADOW_TRAFFIC_TASK_ID = "P1-LEARN-04"
SHADOW_TRAFFIC_ACCOUNTABILITY_ID = "ACC-P1-LEARN-04"
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+-]{0,255}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ShadowTrafficError(ValueError):
    """Shadow-traffic evidence violates isolation policy."""


def _token(value: object, field: str, *, maximum: int = 256) -> str:
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


def _bounded_fraction(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ShadowTrafficError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 < result <= 1.0:
        raise ShadowTrafficError(f"{field} must be within (0, 1]")
    return result


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ShadowTrafficError(f"{field} must be a non-negative integer")
    return value


def _canonical_digest(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ShadowTrafficError(
            "shadow traffic payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _refs(
    values: Iterable[EvidenceRef],
    field: str,
) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise ShadowTrafficError(f"{field} must contain EvidenceRef")
    by_identity: dict[str, EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise ShadowTrafficError(f"{field} must contain EvidenceRef")
        if not item.source.strip():
            raise ShadowTrafficError(f"{field}.source must be non-empty")
        _sha256(item.digest, f"{field}.digest")
        _token(item.category, f"{field}.category", maximum=128)
        by_identity[evidence_ref_identity(item)] = item
    if not by_identity:
        raise ShadowTrafficError(f"{field} requires materialized evidence")
    return tuple(by_identity[key] for key in sorted(by_identity))


def _refs_payload(values: tuple[EvidenceRef, ...]) -> list[dict[str, str]]:
    return [
        {
            "source": item.source,
            "digest": item.digest,
            "category": item.category,
        }
        for item in values
    ]


@dataclass(frozen=True, slots=True)
class ShadowTrafficObservation:
    operation_id: str
    execution_id: str
    agent_id: str
    tenant_id: str
    data_class: str
    request_digest: str
    experiment_manifest_digest: str
    challenger_digest: str
    champion_digest_before: str
    champion_digest_after: str
    registry_digest_before: str
    registry_digest_after: str
    production_response_before_digest: str
    production_response_after_digest: str
    shadow_response_digest: str
    sampled_fraction: float
    persistent_write_count: int
    external_side_effect_count: int
    shadow_selected_for_production: bool
    evaluator_id: str
    evaluator_digest: str
    independent: bool
    evidence_refs: tuple[EvidenceRef, ...]
    schema_version: int = SHADOW_TRAFFIC_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field in (
            "operation_id",
            "execution_id",
            "agent_id",
            "tenant_id",
            "data_class",
            "evaluator_id",
        ):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field),
            )
        for field in (
            "request_digest",
            "experiment_manifest_digest",
            "challenger_digest",
            "champion_digest_before",
            "champion_digest_after",
            "registry_digest_before",
            "registry_digest_after",
            "production_response_before_digest",
            "production_response_after_digest",
            "shadow_response_digest",
            "evaluator_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "sampled_fraction",
            _bounded_fraction(self.sampled_fraction, "sampled_fraction"),
        )
        for field in (
            "persistent_write_count",
            "external_side_effect_count",
        ):
            object.__setattr__(
                self,
                field,
                _nonnegative_int(getattr(self, field), field),
            )
        for field in ("shadow_selected_for_production", "independent"):
            if not isinstance(getattr(self, field), bool):
                raise ShadowTrafficError(f"{field} must be boolean")
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs, "shadow evidence"),
        )
        if self.schema_version != SHADOW_TRAFFIC_SCHEMA_VERSION:
            raise ShadowTrafficError(
                "unsupported shadow observation schema"
            )

    def action_payload(self) -> dict[str, Any]:
        """Identity of the exact shadow action qualified by AUTO-05."""

        return {
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "tenant_id": self.tenant_id,
            "data_class": self.data_class,
            "request_digest": self.request_digest,
            "experiment_manifest_digest": self.experiment_manifest_digest,
            "challenger_digest": self.challenger_digest,
        }

    @property
    def shadow_action_digest(self) -> str:
        return _canonical_digest(self.action_payload())

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            **self.action_payload(),
            "champion_digest_before": self.champion_digest_before,
            "champion_digest_after": self.champion_digest_after,
            "registry_digest_before": self.registry_digest_before,
            "registry_digest_after": self.registry_digest_after,
            "production_response_before_digest": (
                self.production_response_before_digest
            ),
            "production_response_after_digest": (
                self.production_response_after_digest
            ),
            "shadow_response_digest": self.shadow_response_digest,
            "sampled_fraction": self.sampled_fraction,
            "persistent_write_count": self.persistent_write_count,
            "external_side_effect_count": self.external_side_effect_count,
            "shadow_selected_for_production": self.shadow_selected_for_production,
            "evaluator_id": self.evaluator_id,
            "evaluator_digest": self.evaluator_digest,
            "independent": self.independent,
            "evidence_refs": _refs_payload(self.evidence_refs),
            "production_authority": False,
        }

    @property
    def observation_digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class ShadowTrafficDecision:
    accepted: bool
    reasons: tuple[str, ...]
    experiment_manifest_digest: str
    registry_digest: str
    champion_digest: str
    challenger_digest: str
    observation_digest: str
    shadow_action_digest: str
    blast_radius_digest: str
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
            "registry_digest",
            "champion_digest",
            "challenger_digest",
            "observation_digest",
            "shadow_action_digest",
            "blast_radius_digest",
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
            raise ShadowTrafficError("unsupported shadow decision schema")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "experiment_manifest_digest": self.experiment_manifest_digest,
            "registry_digest": self.registry_digest,
            "champion_digest": self.champion_digest,
            "challenger_digest": self.challenger_digest,
            "observation_digest": self.observation_digest,
            "shadow_action_digest": self.shadow_action_digest,
            "blast_radius_digest": self.blast_radius_digest,
            "production_authority": False,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:learn-04:shadow-isolation",
    ) -> EvidenceRef:
        if not self.accepted:
            raise ShadowTrafficError(
                "rejected shadow observation cannot become promotion evidence"
            )
        return EvidenceRef(
            source=source,
            digest=self.decision_digest,
            category="shadow_traffic_isolation",
        )


def _find_candidate(
    registry: ChampionRegistry,
    candidate_ref: str,
) -> CandidateArtifact | None:
    return next(
        (
            item
            for item in registry.candidates
            if item.candidate_ref == candidate_ref
        ),
        None,
    )


def qualify_shadow_traffic(
    *,
    experiment: ExperimentManifest,
    registry: ChampionRegistry,
    challenger: CandidateArtifact,
    observation: ShadowTrafficObservation,
    blast_radius: BlastRadiusDecision,
) -> ShadowTrafficDecision:
    """Qualify one shadow observation without applying any mutation."""

    if not isinstance(experiment, ExperimentManifest):
        raise TypeError("experiment must be ExperimentManifest")
    if not isinstance(registry, ChampionRegistry):
        raise TypeError("registry must be ChampionRegistry")
    if not isinstance(challenger, CandidateArtifact):
        raise TypeError("challenger must be CandidateArtifact")
    if not isinstance(observation, ShadowTrafficObservation):
        raise TypeError("observation must be ShadowTrafficObservation")
    if not isinstance(blast_radius, BlastRadiusDecision):
        raise TypeError("blast_radius must be BlastRadiusDecision")

    reasons: list[str] = []

    if experiment.eligibility.traffic_mode is not TrafficMode.SHADOW:
        reasons.append("experiment-not-shadow-mode")
    if experiment.eligibility.external_side_effects_allowed:
        reasons.append("experiment-allows-external-side-effects")
    if observation.experiment_manifest_digest != experiment.manifest_digest:
        reasons.append("experiment-manifest-digest-mismatch")
    if observation.sampled_fraction > experiment.eligibility.max_traffic_fraction:
        reasons.append("shadow-traffic-fraction-exceeded")
    if observation.data_class not in experiment.eligibility.allowed_data_classes:
        reasons.append("shadow-data-class-not-allowed")
    if (
        experiment.eligibility.tenant_ids
        and observation.tenant_id not in experiment.eligibility.tenant_ids
    ):
        reasons.append("shadow-tenant-not-eligible")

    registered = _find_candidate(registry, experiment.candidate_ref)
    if registered is None:
        reasons.append("experiment-candidate-not-registered")
    elif registered.candidate_digest != challenger.candidate_digest:
        reasons.append("challenger-substitution")
    if challenger.candidate_ref != experiment.candidate_ref:
        reasons.append("challenger-ref-mismatch")
    if observation.challenger_digest != challenger.candidate_digest:
        reasons.append("observation-challenger-digest-mismatch")
    if challenger.candidate_digest == registry.current_champion_digest:
        reasons.append("shadow-candidate-is-current-champion")

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

    if observation.persistent_write_count:
        reasons.append("shadow-persistent-write-detected")
    if observation.external_side_effect_count:
        reasons.append("shadow-external-side-effect-detected")
    if observation.shadow_selected_for_production:
        reasons.append("shadow-output-selected-for-production")
    if (
        observation.production_response_before_digest
        != observation.production_response_after_digest
    ):
        reasons.append("production-response-mutated")
    if not observation.independent:
        reasons.append("shadow-evaluator-not-independent")
    if observation.evaluator_id == observation.agent_id:
        reasons.append("shadow-evaluator-is-agent")

    if not blast_radius.accepted:
        reasons.append("blast-radius-rejected")
    if blast_radius.action_digest != observation.shadow_action_digest:
        reasons.append("blast-action-digest-mismatch")
    if blast_radius.operation_id != observation.operation_id:
        reasons.append("blast-operation-mismatch")
    if blast_radius.execution_id != observation.execution_id:
        reasons.append("blast-execution-mismatch")
    if blast_radius.agent_id != observation.agent_id:
        reasons.append("blast-agent-mismatch")
    if blast_radius.impact not in {ImpactClass.LOW, ImpactClass.MODERATE}:
        reasons.append("shadow-blast-radius-too-high")

    normalized = tuple(sorted(set(reasons)))
    return ShadowTrafficDecision(
        accepted=not normalized,
        reasons=normalized,
        experiment_manifest_digest=experiment.manifest_digest,
        registry_digest=registry.registry_digest,
        champion_digest=registry.current_champion_digest,
        challenger_digest=challenger.candidate_digest,
        observation_digest=observation.observation_digest,
        shadow_action_digest=observation.shadow_action_digest,
        blast_radius_digest=blast_radius.decision_digest,
    )


__all__ = [
    "SHADOW_TRAFFIC_ACCOUNTABILITY_ID",
    "SHADOW_TRAFFIC_SCHEMA_VERSION",
    "SHADOW_TRAFFIC_TASK_ID",
    "ShadowTrafficDecision",
    "ShadowTrafficError",
    "ShadowTrafficObservation",
    "qualify_shadow_traffic",
]
