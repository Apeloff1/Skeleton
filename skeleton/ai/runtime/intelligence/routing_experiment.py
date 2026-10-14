"""Evaluation-only champion/challenger boundary for learned model routing.

This module deliberately cannot mutate ModelRouter or execute providers. It binds
an offline routing-policy artifact to the immutable champion registry so learned
routing can be evaluated without gaining production authority.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping

from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.eval.champion_registry import ChampionRegistry

ROUTING_EXPERIMENT_SCHEMA_VERSION = 1
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class RoutingExperimentError(ValueError):
    """Learned-routing experiment state violates the evaluation boundary."""


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise RoutingExperimentError(f"{field} must be lowercase sha256")
    return value


@dataclass(frozen=True, slots=True)
class RoutingPolicyArtifact:
    """Content-addressed routing policy; data only, never executable authority."""

    policy_id: str
    policy: Mapping[str, Any]
    training_evidence_digest: str
    schema_version: int = ROUTING_EXPERIMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or not self.policy_id or self.policy_id.strip() != self.policy_id:
            raise RoutingExperimentError("policy_id must be normalized")
        if not isinstance(self.policy, Mapping):
            raise RoutingExperimentError("policy must be a mapping")
        object.__setattr__(self, "policy", dict(self.policy))
        object.__setattr__(
            self,
            "training_evidence_digest",
            _sha256(self.training_evidence_digest, "training_evidence_digest"),
        )
        if self.schema_version != ROUTING_EXPERIMENT_SCHEMA_VERSION:
            raise RoutingExperimentError("unsupported routing experiment schema")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "policy": dict(self.policy),
            "training_evidence_digest": self.training_evidence_digest,
            "production_authority": False,
        }

    @property
    def artifact_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class RoutingChallengeDecision:
    accepted_for_offline_evaluation: bool
    reasons: tuple[str, ...]
    registry_digest: str
    champion_digest: str
    challenger_digest: str
    policy_artifact_digest: str
    production_authority: bool = False

    def __post_init__(self) -> None:
        if self.production_authority is not False:
            raise RoutingExperimentError("routing challenge cannot grant production authority")
        for field in ("registry_digest", "champion_digest", "challenger_digest", "policy_artifact_digest"):
            object.__setattr__(self, field, _sha256(getattr(self, field), field))
        if self.accepted_for_offline_evaluation != (not self.reasons):
            raise RoutingExperimentError("acceptance must be derived from reasons")

    @property
    def decision_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": ROUTING_EXPERIMENT_SCHEMA_VERSION,
            "accepted_for_offline_evaluation": self.accepted_for_offline_evaluation,
            "reasons": list(self.reasons),
            "registry_digest": self.registry_digest,
            "champion_digest": self.champion_digest,
            "challenger_digest": self.challenger_digest,
            "policy_artifact_digest": self.policy_artifact_digest,
            "production_authority": False,
        }


def qualify_routing_challenger(
    *,
    registry: ChampionRegistry,
    challenger_digest: str,
    policy_artifact: RoutingPolicyArtifact,
) -> RoutingChallengeDecision:
    """Admit only a registered non-champion artifact to offline evaluation."""
    if not isinstance(registry, ChampionRegistry):
        raise TypeError("registry must be ChampionRegistry")
    if not isinstance(policy_artifact, RoutingPolicyArtifact):
        raise TypeError("policy_artifact must be RoutingPolicyArtifact")
    challenger_digest = _sha256(challenger_digest, "challenger_digest")
    registered = {item.candidate_digest: item for item in registry.candidates}
    reasons: list[str] = []
    challenger = registered.get(challenger_digest)
    if challenger is None:
        reasons.append("challenger-not-registered")
    if challenger_digest == registry.current_champion_digest:
        reasons.append("challenger-is-current-champion")
    if challenger is not None and challenger.artifact_digest != policy_artifact.artifact_digest:
        reasons.append("policy-artifact-digest-mismatch")
    normalized = tuple(sorted(set(reasons)))
    return RoutingChallengeDecision(
        accepted_for_offline_evaluation=not normalized,
        reasons=normalized,
        registry_digest=registry.registry_digest,
        champion_digest=registry.current_champion_digest,
        challenger_digest=challenger_digest,
        policy_artifact_digest=policy_artifact.artifact_digest,
    )


__all__ = [
    "ROUTING_EXPERIMENT_SCHEMA_VERSION",
    "RoutingChallengeDecision",
    "RoutingExperimentError",
    "RoutingPolicyArtifact",
    "qualify_routing_challenger",
]
