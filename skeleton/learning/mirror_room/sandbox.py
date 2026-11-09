"""Hermetic execution boundary for Mirror Room episodes."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import math
from typing import Protocol, runtime_checkable

from .contracts import (
    EpisodeOutcome,
    MirrorCandidate,
    MirrorRoomError,
    MirrorRoomSpec,
    MirrorScenario,
    SandboxPolicy,
    ScenarioSplit,
    _sha256,
    _text,
    _token,
)


@runtime_checkable
class SandboxExecutor(Protocol):
    """Adapter contract for one isolated candidate/scenario execution.

    Implementations must obey the provided policy.  The Mirror Room verifies
    returned capability and resource claims and fails closed on drift.
    """

    executor_id: str

    def execute(
        self,
        *,
        candidate: MirrorCandidate,
        scenario: MirrorScenario,
        seed: int,
        policy: SandboxPolicy,
    ) -> EpisodeOutcome: ...


@dataclass(frozen=True, slots=True)
class SandboxUsage:
    episodes: int = 0
    steps: int = 0
    tokens: int = 0
    cost_units: float = 0.0

    def add(self, outcome: EpisodeOutcome) -> "SandboxUsage":
        return SandboxUsage(
            episodes=self.episodes + 1,
            steps=self.steps + outcome.steps,
            tokens=self.tokens + outcome.tokens,
            cost_units=self.cost_units + outcome.cost_units,
        )


@dataclass(frozen=True, slots=True)
class EpisodeReceipt:
    """Replayable evidence for one sandbox execution."""

    run_id: str
    executor_id: str
    candidate_id: str
    candidate_digest: str
    scenario_id: str
    scenario_digest: str
    split: str
    seed: int
    spec_digest: str
    policy: SandboxPolicy
    outcome: EpisodeOutcome

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _text("run_id", self.run_id))
        object.__setattr__(
            self,
            "executor_id",
            _text("executor_id", self.executor_id),
        )
        object.__setattr__(
            self,
            "candidate_id",
            _token("candidate_id", self.candidate_id),
        )
        object.__setattr__(
            self,
            "candidate_digest",
            _sha256("candidate_digest", self.candidate_digest),
        )
        object.__setattr__(
            self,
            "scenario_id",
            _token("scenario_id", self.scenario_id),
        )
        object.__setattr__(
            self,
            "scenario_digest",
            _sha256("scenario_digest", self.scenario_digest),
        )
        try:
            split = ScenarioSplit(self.split)
        except (TypeError, ValueError) as exc:
            raise MirrorRoomError("episode split must be a Mirror Room split") from exc
        object.__setattr__(self, "split", split.value)
        object.__setattr__(
            self,
            "spec_digest",
            _sha256("spec_digest", self.spec_digest),
        )
        if not isinstance(self.seed, int) or isinstance(self.seed, bool) or self.seed < 0:
            raise MirrorRoomError("seed must be a non-negative integer")
        if not isinstance(self.policy, SandboxPolicy):
            raise MirrorRoomError("policy must be SandboxPolicy")
        if not isinstance(self.outcome, EpisodeOutcome):
            raise MirrorRoomError("outcome must be EpisodeOutcome")

    @property
    def digest(self) -> str:
        from .contracts import _digest  # package-private canonical primitive

        return _digest(
            {
                "run_id": self.run_id,
                "executor_id": self.executor_id,
                "candidate_id": self.candidate_id,
                "candidate_digest": self.candidate_digest,
                "scenario_id": self.scenario_id,
                "scenario_digest": self.scenario_digest,
                "split": self.split,
                "seed": self.seed,
                "spec_digest": self.spec_digest,
                "policy_digest": self.policy.digest,
                "outcome_digest": self.outcome.digest,
            }
        )


class MirrorSandbox:
    """Run-scoped, fail-closed sandbox facade with strict resource accounting."""

    def __init__(self, spec: MirrorRoomSpec, executor: SandboxExecutor) -> None:
        if not isinstance(spec, MirrorRoomSpec):
            raise TypeError("spec must be MirrorRoomSpec")
        if not isinstance(executor, SandboxExecutor):
            raise TypeError("executor must satisfy SandboxExecutor")
        executor_id = getattr(executor, "executor_id", None)
        if not isinstance(executor_id, str) or not executor_id.strip():
            raise MirrorRoomError("sandbox executor requires stable executor_id")
        self.spec = spec
        self.executor = executor
        self._usage = SandboxUsage()

    @property
    def usage(self) -> SandboxUsage:
        return self._usage

    def seed_for(self, *, run_id: str, scenario: MirrorScenario) -> int:
        """Return a candidate-independent seed for paired comparison."""

        if not isinstance(run_id, str) or not run_id.strip():
            raise MirrorRoomError("run_id must be non-empty")
        raw = (
            self.spec.digest
            + ":"
            + self.spec.seed_salt
            + ":"
            + run_id
            + ":"
            + scenario.split.value
            + ":"
            + scenario.scenario_id
        ).encode("utf-8")
        return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")

    def _effective_policy(self) -> SandboxPolicy:
        budget = self.spec.budget
        policy = self.spec.sandbox_policy
        if self._usage.episodes >= budget.max_episodes:
            raise MirrorRoomError("Mirror Room episode budget exhausted")

        remaining_steps = budget.max_total_steps - self._usage.steps
        remaining_tokens = budget.max_total_tokens - self._usage.tokens
        remaining_cost = budget.max_total_cost_units - self._usage.cost_units
        if remaining_steps <= 0:
            raise MirrorRoomError("Mirror Room step budget exhausted")
        if remaining_tokens <= 0:
            raise MirrorRoomError("Mirror Room token budget exhausted")
        if remaining_cost <= 0.0 or not math.isfinite(remaining_cost):
            raise MirrorRoomError("Mirror Room cost budget exhausted")

        return replace(
            policy,
            max_steps_per_episode=min(policy.max_steps_per_episode, remaining_steps),
            max_tokens_per_episode=min(policy.max_tokens_per_episode, remaining_tokens),
            max_cost_units_per_episode=min(policy.max_cost_units_per_episode, remaining_cost),
        )

    def _validate_outcome(
        self,
        outcome: EpisodeOutcome,
        *,
        policy: SandboxPolicy,
    ) -> None:
        expected_metrics = {metric.metric_id for metric in self.spec.metrics}
        if set(outcome.metric_values) != expected_metrics:
            raise MirrorRoomError(
                "sandbox outcome metric set does not match Mirror Room experiment"
            )
        used = set(outcome.capabilities_used)
        allowed = set(policy.allowed_capabilities)
        forbidden = sorted(used - allowed)
        if forbidden:
            raise MirrorRoomError(
                "sandbox executor reported forbidden capabilities: " + ",".join(forbidden)
            )
        if outcome.steps > policy.max_steps_per_episode:
            raise MirrorRoomError("sandbox episode exceeded step budget")
        if outcome.tokens > policy.max_tokens_per_episode:
            raise MirrorRoomError("sandbox episode exceeded token budget")
        if outcome.cost_units > policy.max_cost_units_per_episode + 1e-12:
            raise MirrorRoomError("sandbox episode exceeded cost budget")

    def run_episode(
        self,
        *,
        run_id: str,
        candidate: MirrorCandidate,
        scenario: MirrorScenario,
        seed: int | None = None,
    ) -> EpisodeReceipt:
        if not isinstance(candidate, MirrorCandidate):
            raise TypeError("candidate must be MirrorCandidate")
        if not isinstance(scenario, MirrorScenario):
            raise TypeError("scenario must be MirrorScenario")
        policy = self._effective_policy()
        actual_seed = self.seed_for(run_id=run_id, scenario=scenario) if seed is None else seed
        if not isinstance(actual_seed, int) or isinstance(actual_seed, bool) or actual_seed < 0:
            raise MirrorRoomError("seed must be a non-negative integer")

        try:
            outcome = self.executor.execute(
                candidate=candidate,
                scenario=scenario,
                seed=actual_seed,
                policy=policy,
            )
        except MirrorRoomError:
            raise
        except Exception as exc:
            raise MirrorRoomError(
                f"sandbox executor failed closed: {type(exc).__name__}"
            ) from exc
        if not isinstance(outcome, EpisodeOutcome):
            raise MirrorRoomError("sandbox executor returned invalid outcome type")
        self._validate_outcome(outcome, policy=policy)

        next_usage = self._usage.add(outcome)
        budget = self.spec.budget
        if (
            next_usage.episodes > budget.max_episodes
            or next_usage.steps > budget.max_total_steps
            or next_usage.tokens > budget.max_total_tokens
            or next_usage.cost_units > budget.max_total_cost_units + 1e-12
        ):
            raise MirrorRoomError("sandbox run exceeded declared resource budget")
        self._usage = next_usage

        return EpisodeReceipt(
            run_id=run_id,
            executor_id=self.executor.executor_id,
            candidate_id=candidate.candidate_id,
            candidate_digest=candidate.digest,
            scenario_id=scenario.scenario_id,
            scenario_digest=scenario.digest,
            split=scenario.split.value,
            seed=actual_seed,
            spec_digest=self.spec.digest,
            policy=policy,
            outcome=outcome,
        )

    def verify_replay(
        self,
        receipt: EpisodeReceipt,
        *,
        candidate: MirrorCandidate,
        scenario: MirrorScenario,
    ) -> EpisodeReceipt:
        """Re-execute an episode and require byte-stable evidence identity."""

        if receipt.spec_digest != self.spec.digest:
            raise MirrorRoomError("replay receipt belongs to another Mirror Room spec")
        if receipt.executor_id != self.executor.executor_id:
            raise MirrorRoomError("replay executor identity changed")
        if (
            receipt.candidate_id != candidate.candidate_id
            or receipt.candidate_digest != candidate.digest
        ):
            raise MirrorRoomError("replay candidate identity changed")
        if (
            receipt.scenario_id != scenario.scenario_id
            or receipt.scenario_digest != scenario.digest
        ):
            raise MirrorRoomError("replay scenario identity changed")
        if receipt.split != scenario.split.value:
            raise MirrorRoomError("replay scenario split changed")

        current = self._effective_policy()
        policy = receipt.policy
        if (
            policy.max_steps_per_episode > current.max_steps_per_episode
            or policy.max_tokens_per_episode > current.max_tokens_per_episode
            or policy.max_cost_units_per_episode > current.max_cost_units_per_episode
        ):
            raise MirrorRoomError("insufficient remaining budget for exact replay")

        try:
            outcome = self.executor.execute(
                candidate=candidate,
                scenario=scenario,
                seed=receipt.seed,
                policy=policy,
            )
        except Exception as exc:
            raise MirrorRoomError(
                f"sandbox replay failed closed: {type(exc).__name__}"
            ) from exc
        if not isinstance(outcome, EpisodeOutcome):
            raise MirrorRoomError("sandbox replay returned invalid outcome type")
        self._validate_outcome(outcome, policy=policy)
        if (
            self.spec.sandbox_policy.deterministic_replay_required
            and outcome.digest != receipt.outcome.digest
        ):
            raise MirrorRoomError("deterministic sandbox replay diverged")

        self._usage = self._usage.add(outcome)
        return EpisodeReceipt(
            run_id=receipt.run_id,
            executor_id=receipt.executor_id,
            candidate_id=receipt.candidate_id,
            candidate_digest=receipt.candidate_digest,
            scenario_id=receipt.scenario_id,
            scenario_digest=receipt.scenario_digest,
            split=receipt.split,
            seed=receipt.seed,
            spec_digest=receipt.spec_digest,
            policy=policy,
            outcome=outcome,
        )


__all__ = [
    "EpisodeReceipt",
    "MirrorSandbox",
    "SandboxExecutor",
    "SandboxUsage",
]
