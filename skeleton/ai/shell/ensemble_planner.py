"""Provider-diverse ensemble planning with deterministic safe adjudication."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from skeleton.shells.ai.candidates import CandidateSelection, CandidateSelector
from skeleton.shells.ai.model_circuit import ModelCircuitOpen, ModelCircuitRegistry
from skeleton.shells.ai.planner import AIPlanner, PlanningResult
from skeleton.shells.ai.provider_health import ProviderHealth, ProviderHealthRegistry
from skeleton.shells.ai.rate_limit import AIModelRateLimiter
from skeleton.shells.ai.robust_consensus import (
    ConsensusPolicy,
    RobustConsensusReport,
    RobustProposalConsensus,
)
from skeleton.shells.ai.consensus import proposal_shape_digest
from skeleton.shells.ai.types import AIIntent


@dataclass(frozen=True)
class EnsembleMember:
    planner: AIPlanner
    provider_id: str

    def __post_init__(self) -> None:
        if not self.provider_id or len(self.provider_id) > 256:
            raise ValueError("invalid ensemble provider_id")

    @property
    def model_id(self) -> str:
        return self.planner.model.model_id

    @property
    def health_key(self) -> str:
        return f"{self.provider_id}:{self.model_id}"


@dataclass(frozen=True)
class EnsemblePolicy:
    max_members: int = 8
    min_successes: int = 2
    require_catalog_match: bool = True
    require_policy_match: bool = True

    def __post_init__(self) -> None:
        if self.max_members <= 0:
            raise ValueError("ensemble max_members must be positive")
        if self.min_successes <= 0:
            raise ValueError("ensemble min_successes must be positive")
        if self.min_successes > self.max_members:
            raise ValueError("ensemble min_successes exceeds max_members")


@dataclass(frozen=True)
class EnsembleAttempt:
    provider_id: str
    model_id: str
    status: str
    latency_ms: float
    error_type: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "error_type": self.error_type,
        }


@dataclass(frozen=True)
class EnsemblePlanningResult:
    selected: PlanningResult
    results: tuple[PlanningResult, ...]
    attempts: tuple[EnsembleAttempt, ...]
    consensus: RobustConsensusReport
    selection: CandidateSelection

    def to_dict(self) -> dict[str, object]:
        return {
            "selected": self.selected.to_dict(),
            "results": [item.to_dict() for item in self.results],
            "attempts": [item.to_dict() for item in self.attempts],
            "consensus": self.consensus.to_dict(),
            "selection": self.selection.to_dict(),
        }


class EnsembleAIPlanner:
    """Collect independent proposals; deterministic controls choose one.

    Consensus and candidate utility remain advisory planning controls. The
    selected proposal still enters the normal AIPlanCritic/AIShellService path.
    """

    def __init__(
        self,
        members: tuple[EnsembleMember, ...],
        selector: CandidateSelector,
        *,
        policy: EnsemblePolicy | None = None,
        consensus: RobustProposalConsensus | None = None,
        health: ProviderHealthRegistry | None = None,
        circuits: ModelCircuitRegistry | None = None,
        rate_limiter: AIModelRateLimiter | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not members:
            raise ValueError("ensemble requires at least one member")
        self.members = tuple(members)
        self.selector = selector
        self.policy = policy or EnsemblePolicy()
        self.consensus = consensus or RobustProposalConsensus(
            ConsensusPolicy(min_unique_models=self.policy.min_successes)
        )
        self.health = health or ProviderHealthRegistry(clock=clock)
        self.circuits = circuits or ModelCircuitRegistry(clock=clock)
        self.rate_limiter = rate_limiter or AIModelRateLimiter(clock=clock)
        self._clock = clock
        self._validate_members()

    def _validate_members(self) -> None:
        identities = [
            (member.provider_id, member.model_id)
            for member in self.members
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate ensemble provider/model member")
        if len(self.members) < self.policy.min_successes:
            raise ValueError("ensemble has fewer members than min_successes")
        base = self.members[0].planner
        for member in self.members[1:]:
            planner = member.planner
            if (
                self.policy.require_catalog_match
                and planner.catalog.digest != base.catalog.digest
            ):
                raise ValueError("ensemble tool catalog mismatch")
            if (
                self.policy.require_policy_match
                and planner.policy_fingerprint != base.policy_fingerprint
            ):
                raise ValueError("ensemble policy fingerprint mismatch")

    def _ordered_members(self) -> tuple[EnsembleMember, ...]:
        ranked = []
        order = {
            ProviderHealth.HEALTHY: 0,
            ProviderHealth.UNKNOWN: 1,
            ProviderHealth.DEGRADED: 2,
            ProviderHealth.UNHEALTHY: 3,
            ProviderHealth.QUARANTINED: 4,
        }
        for index, member in enumerate(self.members):
            snapshot = self.health.snapshot(member.health_key)
            ranked.append(
                (
                    order[snapshot.state],
                    snapshot.avg_latency_ms,
                    member.provider_id,
                    member.model_id,
                    index,
                    member,
                )
            )
        ranked.sort(key=lambda item: item[:-1])
        return tuple(item[-1] for item in ranked)

    def propose(
        self,
        intent: AIIntent,
        *,
        prior_observations: tuple[dict[str, object], ...] = (),
    ) -> EnsemblePlanningResult:
        results = []
        attempts = []
        provider_by_model = {}
        considered = 0
        for member in self._ordered_members():
            if considered >= self.policy.max_members:
                break
            considered += 1
            key = member.health_key
            health = self.health.snapshot(key)
            if health.state is ProviderHealth.QUARANTINED:
                attempts.append(
                    EnsembleAttempt(
                        member.provider_id,
                        member.model_id,
                        "quarantined",
                        0.0,
                    )
                )
                continue
            try:
                self.circuits.allow(key)
            except ModelCircuitOpen as exc:
                attempts.append(
                    EnsembleAttempt(
                        member.provider_id,
                        member.model_id,
                        "circuit_open",
                        0.0,
                        type(exc).__name__,
                    )
                )
                continue
            decision = self.rate_limiter.inspect(key, consume=False)
            if not decision.allowed:
                attempts.append(
                    EnsembleAttempt(
                        member.provider_id,
                        member.model_id,
                        "rate_limited",
                        0.0,
                    )
                )
                continue
            self.rate_limiter.require(key)
            started = self._clock()
            try:
                result = member.planner.propose(
                    intent,
                    prior_observations=prior_observations,
                )
            except BaseException as exc:
                latency = max(0.0, (self._clock() - started) * 1000.0)
                self.health.record_failure(
                    key,
                    latency_ms=latency,
                    error_type=type(exc).__name__,
                )
                self.circuits.failure(key)
                attempts.append(
                    EnsembleAttempt(
                        member.provider_id,
                        member.model_id,
                        "failed",
                        latency,
                        type(exc).__name__,
                    )
                )
                continue
            latency = max(0.0, (self._clock() - started) * 1000.0)
            self.health.record_success(key, latency_ms=latency)
            self.circuits.success(key)
            results.append(result)
            provider_by_model.setdefault(
                result.response.proposal.model_id or member.model_id,
                member.provider_id,
            )
            attempts.append(
                EnsembleAttempt(
                    member.provider_id,
                    member.model_id,
                    "succeeded",
                    latency,
                )
            )

        if len(results) < self.policy.min_successes:
            raise RuntimeError("ensemble did not obtain enough successful proposals")
        proposals = tuple(item.response.proposal for item in results)
        consensus = self.consensus.evaluate(
            proposals,
            provider_by_model=provider_by_model,
        )
        if not consensus.reached:
            raise RuntimeError("ensemble proposal consensus was not reached")
        winning = tuple(
            proposal
            for proposal in proposals
            if proposal_shape_digest(proposal) == consensus.winning_shape
        )
        selection = self.selector.evaluate(intent, winning)
        if selection.selected is None:
            raise RuntimeError("ensemble consensus has no executable candidate")
        selected_fingerprint = selection.selected.proposal.fingerprint
        matching = [
            result
            for result in results
            if result.response.proposal.fingerprint == selected_fingerprint
        ]
        if not matching:
            raise RuntimeError("ensemble selected candidate has no planning result")
        matching.sort(
            key=lambda item: (
                item.response.proposal.model_id,
                item.response.proposal.proposal_id,
                item.request.request_id,
            )
        )
        return EnsemblePlanningResult(
            matching[0],
            tuple(results),
            tuple(attempts),
            consensus,
            selection,
        )
