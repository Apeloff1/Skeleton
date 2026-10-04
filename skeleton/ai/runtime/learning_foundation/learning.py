"""Bounded reinforcement, curriculum and verifier-model programs for P3-T2."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass

from skeleton.ai.runtime.inference import LocalModelBackend
from skeleton.ai.runtime.training.evaluation import (
    EvaluationHarness,
    EvaluationResult,
    EvaluationSuite,
)
from skeleton.learning.model_program import TrainingReceipt


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


def _number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LearningProgramError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise LearningProgramError(f"{name} must be finite")
    return result


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
        object.__setattr__(
            self,
            "observation_schema_digest",
            _sha("observation_schema_digest", self.observation_schema_digest),
        )
        object.__setattr__(
            self, "action_schema_digest", _sha("action_schema_digest", self.action_schema_digest)
        )
        object.__setattr__(self, "reward_min", _number("reward_min", self.reward_min))
        object.__setattr__(self, "reward_max", _number("reward_max", self.reward_max))
        if self.reward_min > self.reward_max:
            raise LearningProgramError("reward bounds are inverted")
        if (
            isinstance(self.max_steps, bool)
            or not isinstance(self.max_steps, int)
            or not 1 <= self.max_steps <= 1_000_000
        ):
            raise LearningProgramError("max_steps must be in [1, 1000000]")
        object.__setattr__(
            self,
            "safety_constraint_refs",
            _refs("safety_constraint_ref", self.safety_constraint_refs, minimum=1),
        )

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
    observations_digest: str | None = None
    actions_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "episode_id", _text("episode_id", self.episode_id))
        object.__setattr__(self, "environment_id", _text("environment_id", self.environment_id))
        object.__setattr__(self, "environment_digest", _sha("environment_digest", self.environment_digest))
        object.__setattr__(self, "policy_digest", _sha("policy_digest", self.policy_digest))
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise LearningProgramError("seed must be an integer")
        normalized = [_number("episode reward", value) for value in self.rewards]
        if not normalized:
            raise LearningProgramError("episode requires at least one reward")
        object.__setattr__(self, "rewards", tuple(normalized))
        object.__setattr__(self, "violation_refs", _refs("violation_ref", self.violation_refs))
        object.__setattr__(self, "trace_digest", _sha("trace_digest", self.trace_digest))
        if not isinstance(self.terminated, bool):
            raise LearningProgramError("terminated must be boolean")
        for name in ("observations_digest", "actions_digest"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _sha(name, value))

    def trace_payload(self) -> dict[str, object]:
        return {
            "episode_id": self.episode_id,
            "environment_id": self.environment_id,
            "environment_digest": self.environment_digest,
            "policy_digest": self.policy_digest,
            "seed": self.seed,
            "rewards": list(self.rewards),
            "terminated": self.terminated,
            "violation_refs": list(self.violation_refs),
            "observations_digest": self.observations_digest,
            "actions_digest": self.actions_digest,
        }

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
        object.__setattr__(
            self, "minimum_mean_reward", _number("minimum_mean_reward", self.minimum_mean_reward)
        )
        if (
            isinstance(self.required_episodes, bool)
            or not isinstance(self.required_episodes, int)
            or self.required_episodes <= 0
        ):
            raise LearningProgramError("required_episodes must be positive")
        maximum = _number("maximum_failure_rate", self.maximum_failure_rate)
        if not 0.0 <= maximum <= 1.0:
            raise LearningProgramError("maximum_failure_rate must be in [0, 1]")
        object.__setattr__(self, "maximum_failure_rate", maximum)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "stage_id": self.stage_id,
                "environment_id": self.environment_id,
                "minimum_mean_reward": self.minimum_mean_reward,
                "required_episodes": self.required_episodes,
                "maximum_failure_rate": self.maximum_failure_rate,
            }
        )


@dataclass(frozen=True, slots=True)
class CurriculumDecision:
    stage_id: str
    episode_ids: tuple[str, ...]
    mean_reward: float
    failure_rate: float
    passed: bool
    decision_digest: str
    policy_digest: str | None = None
    stage_digest: str | None = None
    episode_trace_digests: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage_id", _text("stage_id", self.stage_id))
        object.__setattr__(self, "episode_ids", _refs("episode_id", self.episode_ids, minimum=1))
        object.__setattr__(self, "decision_digest", _sha("decision_digest", self.decision_digest))
        object.__setattr__(self, "mean_reward", _number("mean_reward", self.mean_reward))
        rate = _number("failure_rate", self.failure_rate)
        if not 0.0 <= rate <= 1.0:
            raise LearningProgramError("failure_rate must be in [0, 1]")
        if not isinstance(self.passed, bool):
            raise LearningProgramError("passed must be boolean")
        object.__setattr__(self, "failure_rate", rate)
        for name in ("policy_digest", "stage_digest"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _sha(name, value))
        object.__setattr__(
            self,
            "episode_trace_digests",
            tuple(_sha("episode_trace_digest", ref) for ref in self.episode_trace_digests),
        )


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
        object.__setattr__(
            self, "training_receipt_digest", _sha("training_receipt_digest", self.training_receipt_digest)
        )
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
        object.__setattr__(
            self,
            "curriculum_decision_refs",
            _refs("curriculum_decision_ref", self.curriculum_decision_refs, minimum=1),
        )
        object.__setattr__(self, "reason", _text("reason", self.reason))
        object.__setattr__(self, "decision_digest", _sha("decision_digest", self.decision_digest))
        if not isinstance(self.passed, bool):
            raise LearningProgramError("passed must be boolean")

    @property
    def production_promotion_authorized(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class VerifierEvaluationReceipt:
    """A measured local benchmark result, with no caller-supplied success flag."""

    candidate_digest: str
    model_digest: str
    training_receipt_digest: str
    benchmark_ref: str
    suite_digest: str
    result_digest: str
    verifier_id: str
    trainer_id: str
    total_cases: int
    passed_cases: int
    seed: int

    def __post_init__(self) -> None:
        for name in (
            "candidate_digest",
            "model_digest",
            "training_receipt_digest",
            "suite_digest",
            "result_digest",
        ):
            object.__setattr__(self, name, _sha(name, getattr(self, name)))
        for name in ("benchmark_ref", "verifier_id", "trainer_id"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if (
            isinstance(self.total_cases, bool)
            or not isinstance(self.total_cases, int)
            or self.total_cases <= 0
            or isinstance(self.passed_cases, bool)
            or not isinstance(self.passed_cases, int)
            or not 0 <= self.passed_cases <= self.total_cases
        ):
            raise LearningProgramError("evaluation case counts must be bounded integers")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise LearningProgramError("seed must be an integer")
        if self.verifier_id == self.trainer_id:
            raise LearningProgramError("benchmark requires independent verifier")

    @property
    def passed(self) -> bool:
        return self.total_cases > 0 and self.passed_cases == self.total_cases

    @property
    def production_promotion_authorized(self) -> bool:
        return False

    @property
    def digest(self) -> str:
        return _digest(
            {
                "candidate_digest": self.candidate_digest,
                "model_digest": self.model_digest,
                "training_receipt_digest": self.training_receipt_digest,
                "benchmark_ref": self.benchmark_ref,
                "suite_digest": self.suite_digest,
                "result_digest": self.result_digest,
                "verifier_id": self.verifier_id,
                "trainer_id": self.trainer_id,
                "total_cases": self.total_cases,
                "passed_cases": self.passed_cases,
                "seed": self.seed,
            }
        )


class LearningProgram:
    def __init__(self) -> None:
        self._environments: dict[str, ReinforcementEnvironment] = {}
        self._environment_digests: dict[str, str] = {}
        self._episodes: dict[str, EpisodeReceipt] = {}
        self._episode_digests: dict[str, str] = {}
        self._curriculum_decisions: dict[str, CurriculumDecision] = {}
        self._curriculum_stages: dict[str, CurriculumStage] = {}
        self._evaluations: dict[str, tuple[VerifierEvaluationReceipt, EvaluationSuite, EvaluationResult]] = {}
        self._evaluation_payloads: dict[str, str] = {}

    def register_environment(self, environment: ReinforcementEnvironment) -> None:
        if not isinstance(environment, ReinforcementEnvironment):
            raise TypeError("environment must be ReinforcementEnvironment")
        prior = self._environments.get(environment.environment_id)
        if prior is not None and (
            prior != environment
            or environment.digest != self._environment_digests[environment.environment_id]
        ):
            raise LearningProgramError("environment identity conflict")
        self._environments[environment.environment_id] = environment
        self._environment_digests[environment.environment_id] = environment.digest

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
        if environment.digest != self._environment_digests.get(env_id):
            raise LearningProgramError("environment receipt integrity failure")
        if len(rewards) > environment.max_steps:
            raise LearningProgramError("episode exceeds environment max_steps")
        normalized = tuple(_number("episode reward", value) for value in rewards)
        if any(value < environment.reward_min or value > environment.reward_max for value in normalized):
            raise LearningProgramError("reward exceeds declared environment bounds")
        if not isinstance(terminated, bool):
            raise LearningProgramError("terminated must be boolean")
        oid = _sha("observations_digest", observations_digest)
        aid = _sha("actions_digest", actions_digest)
        payload = {
            "episode_id": _text("episode_id", episode_id),
            "environment_id": env_id,
            "environment_digest": environment.digest,
            "policy_digest": _sha("policy_digest", policy_digest),
            "seed": seed,
            "rewards": list(normalized),
            "terminated": terminated,
            "violation_refs": list(_refs("violation_ref", violation_refs)),
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
            terminated=terminated,
            violation_refs=tuple(violation_refs),
            trace_digest=_digest(payload),
            observations_digest=oid,
            actions_digest=aid,
        )
        prior = self._episodes.get(receipt.episode_id)
        if prior is not None and prior != receipt:
            raise LearningProgramError("episode identity conflict")
        self._episodes[receipt.episode_id] = receipt
        self._episode_digests[receipt.episode_id] = receipt.trace_digest
        return receipt

    def _episode(self, episode_id: str) -> EpisodeReceipt:
        try:
            episode = self._episodes[_text("episode_id", episode_id)]
        except KeyError as exc:
            raise LearningProgramError("curriculum references unknown episode") from exc
        if not isinstance(episode, EpisodeReceipt):
            raise LearningProgramError("episode receipt integrity failure")
        environment = self._environments.get(episode.environment_id)
        if (
            environment is None
            or environment.digest != self._environment_digests.get(episode.environment_id)
            or episode.environment_digest != environment.digest
            or episode.observations_digest is None
            or episode.actions_digest is None
            or episode.trace_digest != _digest(episode.trace_payload())
            or episode.trace_digest != self._episode_digests.get(episode.episode_id)
        ):
            raise LearningProgramError("episode receipt integrity failure")
        return episode

    def _stage_decision(self, stage: CurriculumStage, episode_ids: Sequence[str]) -> CurriculumDecision:
        ids = _refs("episode_id", episode_ids, minimum=1)
        episodes = [self._episode(ref) for ref in ids]
        if any(episode.environment_id != stage.environment_id for episode in episodes):
            raise LearningProgramError("curriculum episode environment mismatch")
        if len({episode.policy_digest for episode in episodes}) != 1:
            raise LearningProgramError("curriculum episodes must bind one exact policy")
        if len(episodes) < stage.required_episodes:
            raise LearningProgramError("curriculum stage lacks required episode count")
        mean_reward = _number("mean_reward", sum(item.total_reward for item in episodes) / len(episodes))
        failure_rate = sum(item.failed for item in episodes) / len(episodes)
        passed = mean_reward >= stage.minimum_mean_reward and failure_rate <= stage.maximum_failure_rate
        payload = {
            "stage_id": stage.stage_id,
            "stage_digest": stage.digest,
            "policy_digest": episodes[0].policy_digest,
            "episode_ids": list(ids),
            "episode_trace_digests": [item.trace_digest for item in episodes],
            "mean_reward": mean_reward,
            "failure_rate": failure_rate,
            "passed": passed,
        }
        return CurriculumDecision(
            stage_id=stage.stage_id,
            episode_ids=ids,
            mean_reward=mean_reward,
            failure_rate=failure_rate,
            passed=passed,
            decision_digest=_digest(payload),
            policy_digest=episodes[0].policy_digest,
            stage_digest=stage.digest,
            episode_trace_digests=tuple(item.trace_digest for item in episodes),
        )

    def evaluate_stage(
        self,
        stage: CurriculumStage,
        *,
        episode_ids: Sequence[str],
    ) -> CurriculumDecision:
        if not isinstance(stage, CurriculumStage):
            raise TypeError("stage must be CurriculumStage")
        decision = self._stage_decision(stage, episode_ids)
        self._curriculum_decisions[decision.decision_digest] = decision
        self._curriculum_stages[decision.decision_digest] = stage
        return decision

    async def evaluate_benchmark(
        self,
        candidate: VerifierCandidate,
        *,
        model: LocalModelBackend,
        training_receipt: TrainingReceipt,
        benchmark_ref: str,
        suite: EvaluationSuite,
        verifier_id: str,
        seed: int = 0,
    ) -> VerifierEvaluationReceipt:
        """Execute a declared held-out suite and issue measured local evidence.

        This qualifies a candidate inside the reference program. Production
        activation still belongs to the independent model lifecycle authority.
        Population labels and contamination fingerprints are declarations;
        this reference gate does not prove real-world dataset disjointness.
        """
        if not isinstance(candidate, VerifierCandidate) or not isinstance(training_receipt, TrainingReceipt):
            raise TypeError("candidate and training_receipt types are invalid")
        if not isinstance(suite, EvaluationSuite):
            raise TypeError("suite must be EvaluationSuite")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise LearningProgramError("seed must be an integer")
        verifier = _text("verifier_id", verifier_id)
        benchmark = _text("benchmark_ref", benchmark_ref)
        if benchmark not in candidate.benchmark_refs:
            raise LearningProgramError("benchmark is not declared by candidate")
        if (
            training_receipt.model_digest != candidate.model_digest
            or training_receipt.digest != candidate.training_receipt_digest
            or model.model_digest != candidate.model_digest
        ):
            raise LearningProgramError("benchmark candidate/training/model identity mismatch")
        if verifier == training_receipt.trainer_id:
            raise LearningProgramError("benchmark requires independent verifier")
        if suite.population not in {"heldout", "holdout", "test"}:
            raise LearningProgramError("benchmark suite must use a held-out population")
        identities = (candidate.digest, training_receipt.digest, suite.digest)
        result = await EvaluationHarness().evaluate(model, suite, seed=seed)
        if identities != (candidate.digest, training_receipt.digest, suite.digest):
            raise LearningProgramError("benchmark identities changed during evaluation")
        receipt = self._benchmark_receipt(
            candidate, training_receipt.trainer_id, benchmark, suite, result, verifier, seed
        )
        self._evaluations[receipt.digest] = (receipt, suite, result)
        self._evaluation_payloads[receipt.digest] = _json(
            {"suite": suite.as_dict(), "result": result.as_dict()}
        )
        return receipt

    @staticmethod
    def _benchmark_receipt(
        candidate: VerifierCandidate,
        trainer_id: str,
        benchmark: str,
        suite: EvaluationSuite,
        result: EvaluationResult,
        verifier: str,
        seed: int,
    ) -> VerifierEvaluationReceipt:
        case_ids = {case.case_id for case in suite.cases}
        if (
            result.candidate_model_digest != candidate.model_digest
            or result.suite_digest != suite.digest
            or set(result.outputs) != case_ids
        ):
            raise LearningProgramError("benchmark result identity or case coverage mismatch")
        passed = {
            case.case_id
            for case in suite.cases
            if case.expected_substring.casefold() in result.outputs[case.case_id].casefold()
        }
        if set(result.passed_case_ids) != passed or set(result.failed_case_ids) != case_ids - passed:
            raise LearningProgramError("benchmark result classification mismatch")
        return VerifierEvaluationReceipt(
            candidate_digest=candidate.digest,
            model_digest=candidate.model_digest,
            training_receipt_digest=candidate.training_receipt_digest,
            benchmark_ref=benchmark,
            suite_digest=suite.digest,
            result_digest=result.digest,
            verifier_id=verifier,
            trainer_id=trainer_id,
            total_cases=len(case_ids),
            passed_cases=len(passed),
            seed=seed,
        )

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
        for ref in _refs("curriculum_decision_ref", curriculum_decision_refs, minimum=1):
            digest = _sha("curriculum_decision_ref", ref)
            try:
                decision = self._curriculum_decisions[digest]
                stage = self._curriculum_stages[digest]
            except KeyError as exc:
                raise LearningProgramError("unknown curriculum decision") from exc
            expected = self._stage_decision(stage, decision.episode_ids)
            if decision != expected or digest != expected.decision_digest:
                raise LearningProgramError("curriculum decision integrity failure")
            if decision.policy_digest != candidate.model_digest:
                raise LearningProgramError("curriculum policy does not match candidate model")
            decisions.append(decision)
        refs = _refs("evaluation_ref", evaluation_refs, minimum=2)
        evaluations: list[VerifierEvaluationReceipt] = []
        for ref in refs:
            try:
                evaluation, suite, result = self._evaluations[ref]
            except KeyError as exc:
                raise LearningProgramError("unknown executable evaluation receipt") from exc
            if (
                evaluation.digest != ref
                or evaluation
                != self._benchmark_receipt(
                    candidate,
                    evaluation.trainer_id,
                    evaluation.benchmark_ref,
                    suite,
                    result,
                    evaluation.verifier_id,
                    evaluation.seed,
                )
                or _json({"suite": suite.as_dict(), "result": result.as_dict()})
                != self._evaluation_payloads.get(ref)
            ):
                raise LearningProgramError("evaluation receipt integrity failure")
            if evaluation.trainer_id != trainer or evaluation.verifier_id == trainer:
                raise LearningProgramError("evaluation verifier/trainer identity mismatch")
            evaluations.append(evaluation)
        if len({item.suite_digest for item in evaluations}) != len(evaluations):
            raise LearningProgramError("evaluation suites must be distinct")
        if {item.benchmark_ref for item in evaluations} != set(candidate.benchmark_refs):
            raise LearningProgramError("candidate benchmark coverage mismatch")
        passed = all(item.passed for item in decisions) and all(item.passed for item in evaluations)
        reason = (
            "all independent learning gates passed"
            if passed
            else "one or more measured learning gates failed"
        )
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
    "VerifierEvaluationReceipt",
]
