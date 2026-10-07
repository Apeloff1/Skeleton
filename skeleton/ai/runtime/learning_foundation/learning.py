"""Bounded reinforcement, curriculum and verifier-model programs for P3-T2."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Mapping, Sequence


class LearningProgramError(RuntimeError):
    """A learning-program transition lacks bounded reproducible evidence."""


def _json(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise LearningProgramError("value is not deterministic JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _text(name: str, value: object, *, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LearningProgramError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise LearningProgramError(f"{name} exceeds {maximum} characters")
    return result


def _sha(name: str, value: object) -> str:
    result = _text(name, value, maximum=64).lower()
    if len(result) != 64 or any(ch not in "0123456789abcdef" for ch in result):
        raise LearningProgramError(f"{name} must be lowercase sha256")
    return result


def _refs(name: str, values: Sequence[str], *, minimum: int = 0) -> tuple[str, ...]:
    result: list[str] = []
    for raw in values:
        item = _text(name, raw)
        if item in result:
            raise LearningProgramError(f"{name} contains duplicate {item}")
        result.append(item)
    if len(result) < minimum:
        raise LearningProgramError(f"{name} requires at least {minimum} entries")
    return tuple(result)


@dataclass(frozen=True, slots=True)
class ReinforcementEnvironment:
    environment_id: str
    observation_schema_digest: str
    action_schema_digest: str
    reward_min: float
    reward_max: float
    max_steps: int
    safety_constraint_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "environment_id", _text("environment_id", self.environment_id))
        object.__setattr__(self, "observation_schema_digest", _sha("observation_schema_digest", self.observation_schema_digest))
        object.__setattr__(self, "action_schema_digest", _sha("action_schema_digest", self.action_schema_digest))
        if isinstance(self.reward_min, bool) or not isinstance(self.reward_min, (int, float)):
            raise LearningProgramError("reward_min must be numeric")
        if isinstance(self.reward_max, bool) or not isinstance(self.reward_max, (int, float)):
            raise LearningProgramError("reward_max must be numeric")
        if self.reward_min > self.reward_max:
            raise LearningProgramError("reward bounds are inverted")
        if isinstance(self.max_steps, bool) or not isinstance(self.max_steps, int) or not 1 <= self.max_steps <= 1_000_000:
            raise LearningProgramError("max_steps must be in [1, 1000000]")
        object.__setattr__(self, "safety_constraint_refs", _refs("safety_constraint_ref", self.safety_constraint_refs, minimum=1))

    @property
    def digest(self) -> str:
        return _digest(
            {
                "environment_id": self.environment_id,
                "observation_schema_digest": self.observation_schema_digest,
                "action_schema_digest": self.action_schema_digest,
                "reward_min": float(self.reward_min),
                "reward_max": float(self.reward_max),
                "max_steps": self.max_steps,
                "safety_constraint_refs": list(self.safety_constraint_refs),
            }
        )


@dataclass(frozen=True, slots=True)
class EpisodeReceipt:
    episode_id: str
    environment_id: str
    environment_digest: str
    policy_digest: str
    seed: int
    rewards: tuple[float, ...]
    terminated: bool
    violation_refs: tuple[str, ...]
    trace_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "episode_id", _text("episode_id", self.episode_id))
        object.__setattr__(self, "environment_id", _text("environment_id", self.environment_id))
        object.__setattr__(self, "environment_digest", _sha("environment_digest", self.environment_digest))
        object.__setattr__(self, "policy_digest", _sha("policy_digest", self.policy_digest))
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise LearningProgramError("seed must be an integer")
        normalized: list[float] = []
        for value in self.rewards:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise LearningProgramError("episode rewards must be numeric")
            normalized.append(float(value))
        if not normalized:
            raise LearningProgramError("episode requires at least one reward")
        object.__setattr__(self, "rewards", tuple(normalized))
        object.__setattr__(self, "violation_refs", _refs("violation_ref", self.violation_refs))
        object.__setattr__(self, "trace_digest", _sha("trace_digest", self.trace_digest))

    @property
    def total_reward(self) -> float:
        return float(sum(self.rewards))

    @property
    def failed(self) -> bool:
        return bool(self.violation_refs) or not self.terminated


@dataclass(frozen=True, slots=True)
class CurriculumStage:
    stage_id: str
    environment_id: str
    minimum_mean_reward: float
    required_episodes: int
    maximum_failure_rate: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage_id", _text("stage_id", self.stage_id))
        object.__setattr__(self, "environment_id", _text("environment_id", self.environment_id))
        if isinstance(self.minimum_mean_reward, bool) or not isinstance(self.minimum_mean_reward, (int, float)):
            raise LearningProgramError("minimum_mean_reward must be numeric")
        if isinstance(self.required_episodes, bool) or not isinstance(self.required_episodes, int) or self.required_episodes <= 0:
            raise LearningProgramError("required_episodes must be positive")
        if not 0.0 <= self.maximum_failure_rate <= 1.0:
            raise LearningProgramError("maximum_failure_rate must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class CurriculumDecision:
    stage_id: str
    episode_ids: tuple[str, ...]
    mean_reward: float
    failure_rate: float
    passed: bool
    decision_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage_id", _text("stage_id", self.stage_id))
        object.__setattr__(self, "episode_ids", _refs("episode_id", self.episode_ids, minimum=1))
        object.__setattr__(self, "decision_digest", _sha("decision_digest", self.decision_digest))


@dataclass(frozen=True, slots=True)
class VerifierCandidate:
    candidate_id: str
    model_digest: str
    training_receipt_digest: str
    benchmark_refs: tuple[str, ...]
    intended_claims: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _text("candidate_id", self.candidate_id))
        object.__setattr__(self, "model_digest", _sha("model_digest", self.model_digest))
        object.__setattr__(self, "training_receipt_digest", _sha("training_receipt_digest", self.training_receipt_digest))
        object.__setattr__(self, "benchmark_refs", _refs("benchmark_ref", self.benchmark_refs, minimum=1))
        object.__setattr__(self, "intended_claims", _refs("intended_claim", self.intended_claims, minimum=1))

    @property
    def digest(self) -> str:
        return _digest(
            {
                "candidate_id": self.candidate_id,
                "model_digest": self.model_digest,
                "training_receipt_digest": self.training_receipt_digest,
                "benchmark_refs": list(self.benchmark_refs),
                "intended_claims": list(self.intended_claims),
            }
        )


@dataclass(frozen=True, slots=True)
class VerifierDecision:
    candidate_digest: str
    verifier_id: str
    evaluation_refs: tuple[str, ...]
    curriculum_decision_refs: tuple[str, ...]
    passed: bool
    reason: str
    decision_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_digest", _sha("candidate_digest", self.candidate_digest))
        object.__setattr__(self, "verifier_id", _text("verifier_id", self.verifier_id))
        object.__setattr__(self, "evaluation_refs", _refs("evaluation_ref", self.evaluation_refs, minimum=2))
        object.__setattr__(self, "curriculum_decision_refs", _refs("curriculum_decision_ref", self.curriculum_decision_refs, minimum=1))
        object.__setattr__(self, "reason", _text("reason", self.reason))
        object.__setattr__(self, "decision_digest", _sha("decision_digest", self.decision_digest))


class LearningProgram:
    def __init__(self) -> None:
        self._environments: dict[str, ReinforcementEnvironment] = {}
        self._episodes: dict[str, EpisodeReceipt] = {}
        self._curriculum_decisions: dict[str, CurriculumDecision] = {}

    def register_environment(self, environment: ReinforcementEnvironment) -> None:
        if not isinstance(environment, ReinforcementEnvironment):
            raise TypeError("environment must be ReinforcementEnvironment")
        prior = self._environments.get(environment.environment_id)
        if prior is not None and prior != environment:
            raise LearningProgramError("environment identity conflict")
        self._environments[environment.environment_id] = environment

    def record_episode(
        self,
        *,
        episode_id: str,
        environment_id: str,
        policy_digest: str,
        seed: int,
        rewards: Sequence[float],
        terminated: bool,
        violation_refs: Sequence[str] = (),
        observations_digest: str,
        actions_digest: str,
    ) -> EpisodeReceipt:
        env_id = _text("environment_id", environment_id)
        try:
            environment = self._environments[env_id]
        except KeyError as exc:
            raise LearningProgramError("environment is not registered") from exc
        if len(rewards) > environment.max_steps:
            raise LearningProgramError("episode exceeds environment max_steps")
        normalized = tuple(float(value) for value in rewards)
        if any(value < environment.reward_min or value > environment.reward_max for value in normalized):
            raise LearningProgramError("reward exceeds declared environment bounds")
        oid = _sha("observations_digest", observations_digest)
        aid = _sha("actions_digest", actions_digest)
        payload = {
            "episode_id": episode_id,
            "environment_digest": environment.digest,
            "policy_digest": _sha("policy_digest", policy_digest),
            "seed": seed,
            "rewards": list(normalized),
            "terminated": bool(terminated),
            "violation_refs": list(violation_refs),
            "observations_digest": oid,
            "actions_digest": aid,
        }
        receipt = EpisodeReceipt(
            episode_id=episode_id,
            environment_id=env_id,
            environment_digest=environment.digest,
            policy_digest=policy_digest,
            seed=seed,
            rewards=normalized,
            terminated=bool(terminated),
            violation_refs=tuple(violation_refs),
            trace_digest=_digest(payload),
        )
        prior = self._episodes.get(receipt.episode_id)
        if prior is not None and prior != receipt:
            raise LearningProgramError("episode identity conflict")
        self._episodes[receipt.episode_id] = receipt
        return receipt

    def evaluate_stage(
        self,
        stage: CurriculumStage,
        *,
        episode_ids: Sequence[str],
    ) -> CurriculumDecision:
        if not isinstance(stage, CurriculumStage):
            raise TypeError("stage must be CurriculumStage")
        episodes: list[EpisodeReceipt] = []
        for episode_id in episode_ids:
            try:
                episode = self._episodes[_text("episode_id", episode_id)]
            except KeyError as exc:
                raise LearningProgramError("curriculum references unknown episode") from exc
            if episode.environment_id != stage.environment_id:
                raise LearningProgramError("curriculum episode environment mismatch")
            episodes.append(episode)
        if len(episodes) < stage.required_episodes:
            raise LearningProgramError("curriculum stage lacks required episode count")
        mean_reward = sum(item.total_reward for item in episodes) / len(episodes)
        failure_rate = sum(item.failed for item in episodes) / len(episodes)
        passed = mean_reward >= stage.minimum_mean_reward and failure_rate <= stage.maximum_failure_rate
        payload = {
            "stage_id": stage.stage_id,
            "episode_ids": [item.episode_id for item in episodes],
            "mean_reward": mean_reward,
            "failure_rate": failure_rate,
            "passed": passed,
        }
        decision = CurriculumDecision(
            stage_id=stage.stage_id,
            episode_ids=tuple(item.episode_id for item in episodes),
            mean_reward=mean_reward,
            failure_rate=failure_rate,
            passed=passed,
            decision_digest=_digest(payload),
        )
        self._curriculum_decisions[decision.decision_digest] = decision
        return decision

    def evaluate_verifier_candidate(
        self,
        candidate: VerifierCandidate,
        *,
        verifier_id: str,
        trainer_id: str,
        evaluation_refs: Sequence[str],
        curriculum_decision_refs: Sequence[str],
    ) -> VerifierDecision:
        if not isinstance(candidate, VerifierCandidate):
            raise TypeError("candidate must be VerifierCandidate")
        verifier = _text("verifier_id", verifier_id)
        trainer = _text("trainer_id", trainer_id)
        if verifier == trainer:
            raise LearningProgramError("verifier candidate requires independent verifier")
        decisions: list[CurriculumDecision] = []
        for ref in curriculum_decision_refs:
            digest = _sha("curriculum_decision_ref", ref)
            try:
                decisions.append(self._curriculum_decisions[digest])
            except KeyError as exc:
                raise LearningProgramError("unknown curriculum decision") from exc
        refs = _refs("evaluation_ref", evaluation_refs, minimum=2)
        passed = bool(decisions) and all(item.passed for item in decisions)
        reason = "all independent learning gates passed" if passed else "one or more curriculum gates failed"
        payload = {
            "candidate_digest": candidate.digest,
            "verifier_id": verifier,
            "evaluation_refs": list(refs),
            "curriculum_decision_refs": [item.decision_digest for item in decisions],
            "passed": passed,
            "reason": reason,
        }
        return VerifierDecision(
            candidate_digest=candidate.digest,
            verifier_id=verifier,
            evaluation_refs=refs,
            curriculum_decision_refs=tuple(item.decision_digest for item in decisions),
            passed=passed,
            reason=reason,
            decision_digest=_digest(payload),
        )


__all__ = [
    "CurriculumDecision",
    "CurriculumStage",
    "EpisodeReceipt",
    "LearningProgram",
    "LearningProgramError",
    "ReinforcementEnvironment",
    "VerifierCandidate",
    "VerifierDecision",
]
