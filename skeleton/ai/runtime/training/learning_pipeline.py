"""Executable local post-training evidence on the existing SQLite ledger.

Policies are trusted, stateless, side-effect-free Python callbacks. Their only
runtime input is a bounded observation; this API grants no tool or network
authority. Committed transitions are never replayed during recovery.
"""

from __future__ import annotations

import json
import types
import uuid
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from functools import wraps

from skeleton.ai.runtime.inference import LocalModelBackend

from .evaluation import (
    EvaluationCase,
    EvaluationHarness,
    EvaluationResult,
    EvaluationSuite,
    evaluation_case_passes,
)
from .post_training import (
    CurriculumDecision,
    CurriculumEngine,
    CurriculumStage,
    DeterministicRLEnvironment,
    PostTrainingExperiment,
    PostTrainingLedger,
    RLStepReceipt,
    _canonical,
    _digest,
    _require_digest,
)


class PostTrainingExecutionError(RuntimeError):
    """Execution is stale, unbound, exhausted, cancelled, or corrupt."""


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError(f"{name} must be non-empty text of at most 256 characters")
    return value.strip()


def _positive(value: int, name: str, ceiling: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= ceiling:
        raise ValueError(f"{name} must be an integer in [1, {ceiling}]")
    return value


def _policy_value(value: object, depth: int = 0) -> object:
    if depth > 4:
        raise ValueError("policy captured configuration exceeds bounded depth")
    if isinstance(value, types.FunctionType):
        return {"function_digest": _function_digest(value, depth + 1)}
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (tuple, list)):
        return [_policy_value(item, depth + 1) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _policy_value(item, depth + 1) for key, item in value.items()}
    model_digest = getattr(value, "model_digest", None)
    if isinstance(model_digest, str):
        return {"local_model_digest": _require_digest(model_digest, field="captured model_digest")}
    raise TypeError("policy captured configuration must be bounded JSON or an identified local model")


def _code_payload(code: types.CodeType, depth: int) -> dict[str, object]:
    if depth > 4:
        raise ValueError("policy code exceeds bounded depth")
    constants = []
    for value in code.co_consts:
        if isinstance(value, types.CodeType):
            constants.append({"nested_code": _code_payload(value, depth + 1)})
        elif isinstance(value, bytes):
            constants.append({"bytes": value.hex()})
        else:
            constants.append(_policy_value(value, depth + 1))
    return {
        "bytecode": code.co_code.hex(),
        "constants": constants,
        "names": code.co_names,
        "variables": code.co_varnames,
        "cells": code.co_cellvars,
        "free_variables": code.co_freevars,
        "argument_count": code.co_argcount,
        "positional_only": code.co_posonlyargcount,
        "keyword_only": code.co_kwonlyargcount,
        "flags": code.co_flags,
        "exception_table": code.co_exceptiontable.hex(),
    }


def _function_digest(callback: Callable, depth: int = 0) -> str:
    if not isinstance(callback, types.FunctionType):
        raise TypeError("local policy must be a plain Python function")
    captures = {
        name: _policy_value(cell.cell_contents, depth + 1)
        for name, cell in zip(callback.__code__.co_freevars, callback.__closure__ or ())
    }
    globals_used = {
        name: _policy_value(callback.__globals__[name], depth + 1)
        for name in callback.__code__.co_names
        if name in callback.__globals__
    }
    payload = {
        "code_digest": _digest(_code_payload(callback.__code__, depth)),
        "defaults": _policy_value(callback.__defaults__, depth + 1),
        "keyword_defaults": _policy_value(callback.__kwdefaults__, depth + 1),
        "captures": captures,
        "globals": globals_used,
    }
    if len(_canonical(payload).encode("utf-8")) > 64 * 1024:
        raise ValueError("policy captured configuration exceeds byte budget")
    return _digest(payload)


def _curriculum_payload(curriculum: CurriculumEngine) -> list[dict[str, object]]:
    if not isinstance(curriculum, CurriculumEngine) or len(curriculum.stages) > 128:
        raise ValueError("curriculum must contain at most 128 declared stages")
    return [curriculum.stages[key].as_dict() for key in sorted(curriculum.stages)]


def _ledger_locked(method):
    @wraps(method)
    def invoke(self, *args, **kwargs):
        with self.ledger._lock:
            return method(self, *args, **kwargs)

    return invoke


@dataclass(frozen=True, slots=True)
class LocalPolicyObservation:
    episode_id: str
    seed: int
    step: int
    state_digest: str
    allowed_actions: tuple[str, ...]
    remaining_steps: int


@dataclass(frozen=True, slots=True)
class LocalPostTrainingPolicy:
    policy_id: str
    version: str
    model_digest: str
    code_revision: str
    decide: Callable[[LocalPolicyObservation], str] = field(repr=False, compare=False)
    side_effect_free: bool = True

    def __post_init__(self) -> None:
        for name in ("policy_id", "version", "code_revision"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "model_digest", _require_digest(self.model_digest, field="model_digest"))
        if self.side_effect_free is not True:
            raise ValueError("local policy callbacks must be side-effect-free")
        _function_digest(self.decide)

    def as_dict(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "model_digest": self.model_digest,
            "code_revision": self.code_revision,
            "callback_digest": _function_digest(self.decide),
            "side_effect_free": True,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class PostTrainingExecutionSpec:
    run_id: str
    experiment_digest: str
    policy_digest: str
    model_digest: str
    curriculum_digest: str
    evaluation_suite_digest: str
    trainer_id: str
    max_steps: int = 1024
    max_episodes: int = 32
    max_episode_steps: int = 128

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _text(self.run_id, "run_id"))
        object.__setattr__(self, "trainer_id", _text(self.trainer_id, "trainer_id"))
        for name in (
            "experiment_digest",
            "policy_digest",
            "model_digest",
            "curriculum_digest",
            "evaluation_suite_digest",
        ):
            object.__setattr__(self, name, _require_digest(getattr(self, name), field=name))
        _positive(self.max_steps, "max_steps", 100_000)
        _positive(self.max_episodes, "max_episodes", 128)
        _positive(self.max_episode_steps, "max_episode_steps", 4096)

    @staticmethod
    def curriculum_digest_for(curriculum: CurriculumEngine) -> str:
        return _digest(_curriculum_payload(curriculum))


@dataclass(frozen=True, slots=True)
class ExecutedEpisodeReceipt:
    run_id: str
    episode_id: str
    binding_digest: str
    policy_digest: str
    model_digest: str
    environment_digest: str
    seed: int
    status: str
    steps: int
    total_reward: float
    terminal: bool
    step_receipt_digests: tuple[str, ...]
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class ExecutedCurriculumReceipt:
    run_id: str
    binding_digest: str
    curriculum_digest: str
    episode_refs: tuple[str, ...]
    decision: CurriculumDecision
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class ExecutedEvaluationReceipt:
    run_id: str
    binding_digest: str
    model_digest: str
    suite_digest: str
    result_digest: str
    verifier_id: str
    passed: bool
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class PostTrainingQualificationReceipt:
    run_id: str
    model_digest: str
    policy_digest: str
    binding_digest: str
    curriculum_refs: tuple[str, ...]
    evaluation_ref: str
    verifier_id: str
    status: str
    production_promotion_authorized: bool
    receipt_digest: str


class PostTrainingRunner:
    """Run bounded local episodes and derive measured candidate qualification."""

    def __init__(self, ledger: PostTrainingLedger) -> None:
        if not isinstance(ledger, PostTrainingLedger):
            raise TypeError("ledger must be PostTrainingLedger")
        self.ledger = ledger
        self._token = uuid.uuid4().hex
        self._runtime: dict[str, tuple[dict, LocalPostTrainingPolicy, int]] = {}
        with ledger.execution_transaction() as db:
            for statement in (
                "CREATE TABLE IF NOT EXISTS post_environment_behavior (environment_digest TEXT PRIMARY KEY, behavior_digest TEXT NOT NULL, payload TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS post_execution (run_id TEXT PRIMARY KEY, binding_digest TEXT NOT NULL, binding_json TEXT NOT NULL, status TEXT NOT NULL, epoch INTEGER NOT NULL, token TEXT NOT NULL, steps INTEGER NOT NULL, episodes INTEGER NOT NULL)",
                "CREATE TABLE IF NOT EXISTS post_episode (episode_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES post_execution(run_id), ordinal INTEGER NOT NULL, payload TEXT NOT NULL, payload_digest TEXT NOT NULL, UNIQUE(run_id,ordinal))",
                "CREATE TABLE IF NOT EXISTS post_execution_step (run_id TEXT NOT NULL REFERENCES post_execution(run_id), episode_id TEXT NOT NULL REFERENCES post_episode(episode_id), step INTEGER NOT NULL, receipt_digest TEXT NOT NULL REFERENCES rl_step(receipt_digest), witness_digest TEXT NOT NULL, PRIMARY KEY(episode_id,step))",
                "CREATE TABLE IF NOT EXISTS post_episode_evidence (receipt_digest TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES post_execution(run_id), episode_id TEXT NOT NULL UNIQUE REFERENCES post_episode(episode_id), payload TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS post_curriculum_evidence (receipt_digest TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES post_execution(run_id), payload TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS post_evaluation_evidence (receipt_digest TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES post_execution(run_id), request_digest TEXT NOT NULL UNIQUE, payload TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS post_qualification (receipt_digest TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES post_execution(run_id), payload TEXT NOT NULL)",
            ):
                db.execute(statement)

    def _execution(self, db, run_id: str) -> tuple[dict, str, int, str, int, int]:
        row = db.execute(
            "SELECT binding_digest,binding_json,status,epoch,token,steps,episodes FROM post_execution WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise PostTrainingExecutionError("execution is not registered")
        try:
            binding = json.loads(row[1])
            if _digest(binding) != row[0] or binding["spec"]["run_id"] != run_id:
                raise ValueError("identity mismatch")
            if row[2] not in {"active", "cancelled", "budget_exhausted", "qualified"}:
                raise ValueError("invalid state")
            if any(type(value) is not int or value < 0 for value in (row[3], row[5], row[6])):
                raise ValueError("invalid counters")
            if row[5] > binding["spec"]["max_steps"] or row[6] > binding["spec"]["max_episodes"]:
                raise ValueError("usage exceeds binding")
            observed_steps = db.execute(
                "SELECT COUNT(*) FROM post_execution_step WHERE run_id=?", (run_id,)
            ).fetchone()[0]
            observed_episodes = db.execute(
                "SELECT COUNT(*) FROM post_episode WHERE run_id=?", (run_id,)
            ).fetchone()[0]
            if (row[5], row[6]) != (observed_steps, observed_episodes):
                raise ValueError("usage does not match committed work")
        except (ValueError, TypeError, KeyError) as exc:
            raise PostTrainingExecutionError("execution binding or usage integrity failure") from exc
        return binding, row[2], row[3], row[4], row[5], row[6]

    @_ledger_locked
    def bind_execution(
        self,
        spec: PostTrainingExecutionSpec,
        *,
        experiment: PostTrainingExperiment,
        environment: DeterministicRLEnvironment,
        policy: LocalPostTrainingPolicy,
        curriculum: CurriculumEngine,
    ) -> str:
        if not isinstance(spec, PostTrainingExecutionSpec) or not isinstance(
            experiment, PostTrainingExperiment
        ):
            raise TypeError("execution spec and experiment types are invalid")
        if type(environment) is not DeterministicRLEnvironment or not isinstance(
            policy, LocalPostTrainingPolicy
        ):
            raise TypeError("execution requires the canonical deterministic environment and local policy")
        rewards = dict(environment.rewards)
        if not 1 <= len(rewards) <= 64 or any(
            len(action) > 128 or abs(reward) > 1_000_000 for action, reward in rewards.items()
        ):
            raise ValueError("environment action/reward bounds exceeded")
        behavior = {
            "spec": environment.spec.as_dict(),
            "rewards": rewards,
            "terminal_actions": sorted(environment.terminal_actions),
        }
        binding = {
            "schema_version": "skeleton.post_training_execution.v1",
            "spec": asdict(spec),
            "experiment": experiment.as_dict(),
            "environment": behavior,
            "policy": policy.as_dict(),
            "curriculum": _curriculum_payload(curriculum),
        }
        if (
            spec.experiment_digest != experiment.digest
            or spec.model_digest != experiment.base_candidate_digest
            or spec.model_digest != policy.model_digest
            or spec.policy_digest != policy.digest
            or spec.curriculum_digest != _digest(binding["curriculum"])
            or spec.evaluation_suite_digest != experiment.evaluation_suite_digest
        ):
            raise PostTrainingExecutionError("execution policy/model/curriculum/evaluation identity mismatch")
        self.ledger.register_experiment(experiment)
        self.ledger.register_environment(environment.spec)
        encoded = _canonical(binding)
        digest = _digest(binding)
        with self.ledger.execution_transaction() as db:
            environment_digest = environment.spec.digest
            prior_behavior = db.execute(
                "SELECT behavior_digest,payload FROM post_environment_behavior WHERE environment_digest=?",
                (environment_digest,),
            ).fetchone()
            if prior_behavior is not None and prior_behavior != (_digest(behavior), _canonical(behavior)):
                raise PostTrainingExecutionError("versioned environment behavior is immutable")
            db.execute(
                "INSERT OR IGNORE INTO post_environment_behavior VALUES (?,?,?)",
                (environment_digest, _digest(behavior), _canonical(behavior)),
            )
            row = db.execute(
                "SELECT binding_digest,binding_json FROM post_execution WHERE run_id=?", (spec.run_id,)
            ).fetchone()
            if row is None:
                epoch = 0
                db.execute(
                    "INSERT INTO post_execution VALUES (?,?,?,?,?,?,?,?)",
                    (spec.run_id, digest, encoded, "active", epoch, self._token, 0, 0),
                )
            else:
                existing, _, epoch, _, _, _ = self._execution(db, spec.run_id)
                if _canonical(existing) != encoded or row[0] != digest:
                    raise PostTrainingExecutionError("execution identity is bound to different inputs")
                epoch += 1
                db.execute(
                    "UPDATE post_execution SET epoch=?,token=? WHERE run_id=?",
                    (epoch, self._token, spec.run_id),
                )
        self._runtime[spec.run_id] = (binding, policy, epoch)
        return digest

    def _episode(self, db, episode_id: str) -> dict | None:
        row = db.execute(
            "SELECT run_id,payload,payload_digest FROM post_episode WHERE episode_id=?", (episode_id,)
        ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row[1])
            if (
                _digest(payload) != row[2]
                or payload["episode_id"] != episode_id
                or payload["run_id"] != row[0]
            ):
                raise ValueError("identity mismatch")
        except (ValueError, KeyError, TypeError) as exc:
            raise PostTrainingExecutionError("episode cursor integrity failure") from exc
        return payload

    @staticmethod
    def _store_episode(db, payload: dict) -> None:
        db.execute(
            "UPDATE post_episode SET payload=?,payload_digest=? WHERE episode_id=?",
            (_canonical(payload), _digest(payload), payload["episode_id"]),
        )

    def _verify_steps(self, db, binding: dict, episode: dict) -> tuple[list[RLStepReceipt], list[str]]:
        rows = db.execute(
            "SELECT s.step,s.receipt_digest,s.witness_digest,r.payload FROM post_execution_step s JOIN rl_step r ON r.receipt_digest=s.receipt_digest WHERE s.episode_id=? AND s.run_id=? ORDER BY s.step",
            (episode["episode_id"], episode["run_id"]),
        ).fetchall()
        receipts = []
        refs = []
        previous = episode["initial_state"]
        env_digest = _digest(binding["environment"]["spec"])
        previous_witness = None
        for index, (step, ref, witness, encoded) in enumerate(rows, 1):
            try:
                receipt = RLStepReceipt(**json.loads(encoded))
                expected_next = _digest(
                    {
                        "environment": env_digest,
                        "episode": episode["episode_id"],
                        "previous": previous,
                        "action": receipt.action,
                        "step": index,
                    }
                )
                expected_witness = _digest(
                    {
                        "binding_digest": _digest(binding),
                        "receipt_digest": ref,
                        "previous_witness": previous_witness,
                    }
                )
                if (
                    step != index
                    or receipt.step != index
                    or receipt.digest != ref
                    or receipt.environment_digest != env_digest
                    or receipt.episode_id != episode["episode_id"]
                    or receipt.state_digest != previous
                    or receipt.next_state_digest != expected_next
                    or receipt.reward != binding["environment"]["rewards"][receipt.action]
                    or receipt.terminal != (receipt.action in binding["environment"]["terminal_actions"])
                    or witness != expected_witness
                    or (receipts and receipts[-1].terminal)
                ):
                    raise ValueError("transition mismatch")
            except (ValueError, TypeError, KeyError) as exc:
                raise PostTrainingExecutionError("executed transition evidence integrity failure") from exc
            receipts.append(receipt)
            refs.append(ref)
            previous = receipt.next_state_digest
            previous_witness = witness
        if len(receipts) != episode["step"] or previous != episode["state_digest"]:
            raise PostTrainingExecutionError("episode cursor does not match observed transitions")
        initial = _digest(
            {"environment": env_digest, "episode": episode["episode_id"], "seed": episode["seed"], "step": 0}
        )
        if initial != episode["initial_state"] or episode["terminal"] != bool(
            receipts and receipts[-1].terminal
        ):
            raise PostTrainingExecutionError("episode initial/terminal state integrity failure")
        return receipts, refs

    def _finish(self, db, binding: dict, episode: dict) -> ExecutedEpisodeReceipt:
        receipts, refs = self._verify_steps(db, binding, episode)
        payload = {
            "run_id": episode["run_id"],
            "episode_id": episode["episode_id"],
            "binding_digest": _digest(binding),
            "policy_digest": binding["spec"]["policy_digest"],
            "model_digest": binding["spec"]["model_digest"],
            "environment_digest": _digest(binding["environment"]["spec"]),
            "seed": episode["seed"],
            "status": episode["status"],
            "steps": len(receipts),
            "total_reward": sum(item.reward for item in receipts),
            "terminal": episode["terminal"],
            "step_receipt_digests": refs,
        }
        digest = _digest(payload)
        row = db.execute(
            "SELECT receipt_digest,payload FROM post_episode_evidence WHERE episode_id=?",
            (episode["episode_id"],),
        ).fetchone()
        if row is not None:
            if row != (digest, _canonical(payload)):
                raise PostTrainingExecutionError("episode evidence identity drift")
        else:
            db.execute(
                "INSERT INTO post_episode_evidence VALUES (?,?,?,?)",
                (digest, episode["run_id"], episode["episode_id"], _canonical(payload)),
            )
        return ExecutedEpisodeReceipt(
            **{**payload, "step_receipt_digests": tuple(refs), "receipt_digest": digest}
        )

    def run_episode(
        self, run_id: str, *, episode_id: str, seed: int = 0, cancelled: Callable[[], bool] | None = None
    ) -> ExecutedEpisodeReceipt:
        run_id, episode_id = _text(run_id, "run_id"), _text(episode_id, "episode_id")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError("episode seed must be an integer")
        try:
            registered, policy, admitted_epoch = self._runtime[run_id]
        except KeyError as exc:
            raise PostTrainingExecutionError(
                "runner must bind the exact execution before local policy work"
            ) from exc
        while True:
            with self.ledger.execution_transaction() as db:
                binding, status, epoch, token, used, episodes = self._execution(db, run_id)
                if (
                    binding != registered
                    or policy.as_dict() != binding["policy"]
                    or token != self._token
                    or epoch != admitted_epoch
                ):
                    raise PostTrainingExecutionError("runner is fenced or policy identity changed")
                episode = self._episode(db, episode_id)
                if episode is not None and (episode["run_id"] != run_id or episode["seed"] != seed):
                    raise PostTrainingExecutionError(
                        "episode identity is bound to a different execution or seed"
                    )
                if episode is not None and episode["status"] != "running":
                    return self._finish(db, binding, episode)
                if status != "active":
                    raise PostTrainingExecutionError(f"execution is {status}")
                env = DeterministicRLEnvironment(
                    # The versioned canonical spec is reloaded from the binding.
                    self._environment_spec(binding),
                    rewards=binding["environment"]["rewards"],
                    terminal_actions=binding["environment"]["terminal_actions"],
                )
                if episode is None:
                    if episodes >= binding["spec"]["max_episodes"]:
                        raise PostTrainingExecutionError("cumulative episode budget exhausted")
                    initial = env.reset(episode_id=episode_id, seed=seed)
                    episode = {
                        "run_id": run_id,
                        "episode_id": episode_id,
                        "seed": seed,
                        "initial_state": initial,
                        "step": 0,
                        "state_digest": initial,
                        "terminal": False,
                        "status": "running",
                    }
                    db.execute(
                        "INSERT INTO post_episode VALUES (?,?,?,?,?)",
                        (episode_id, run_id, episodes + 1, _canonical(episode), _digest(episode)),
                    )
                    db.execute("UPDATE post_execution SET episodes=episodes+1 WHERE run_id=?", (run_id,))
                else:
                    self._verify_steps(db, binding, episode)
                    env.restore(
                        episode_id=episode_id,
                        step=episode["step"],
                        state_digest=episode["state_digest"],
                        terminal=episode["terminal"],
                    )
                if cancelled is not None and cancelled() is True:
                    db.execute("UPDATE post_execution SET status='cancelled' WHERE run_id=?", (run_id,))
                    episode["status"] = "cancelled"
                elif used >= binding["spec"]["max_steps"]:
                    db.execute(
                        "UPDATE post_execution SET status='budget_exhausted' WHERE run_id=?", (run_id,)
                    )
                    episode["status"] = "budget_exhausted"
                else:
                    remaining = min(
                        binding["spec"]["max_steps"] - used,
                        binding["spec"]["max_episode_steps"] - episode["step"],
                    )
                    observation = LocalPolicyObservation(
                        episode_id,
                        seed,
                        episode["step"] + 1,
                        episode["state_digest"],
                        tuple(sorted(env.rewards)),
                        remaining,
                    )
                    action = policy.decide(observation)
                    if policy.as_dict() != binding["policy"]:
                        raise PostTrainingExecutionError("policy captured state changed during decision")
                    if not isinstance(action, str) or action not in env.rewards:
                        raise PostTrainingExecutionError(
                            "policy returned an action outside its declared authority"
                        )
                    receipt = env.step(action)
                    previous = db.execute(
                        "SELECT witness_digest FROM post_execution_step WHERE episode_id=? ORDER BY step DESC LIMIT 1",
                        (episode_id,),
                    ).fetchone()
                    witness = _digest(
                        {
                            "binding_digest": _digest(binding),
                            "receipt_digest": receipt.digest,
                            "previous_witness": None if previous is None else previous[0],
                        }
                    )
                    encoded = _canonical(receipt.as_dict())
                    old = db.execute(
                        "SELECT payload FROM rl_step WHERE receipt_digest=?", (receipt.digest,)
                    ).fetchone()
                    if old is not None and old[0] != encoded:
                        raise PostTrainingExecutionError("RL receipt identity collision")
                    db.execute(
                        "INSERT OR IGNORE INTO rl_step VALUES (?,?,?)",
                        (receipt.digest, receipt.environment_digest, encoded),
                    )
                    db.execute(
                        "INSERT INTO post_execution_step VALUES (?,?,?,?,?)",
                        (run_id, episode_id, receipt.step, receipt.digest, witness),
                    )
                    db.execute("UPDATE post_execution SET steps=steps+1 WHERE run_id=?", (run_id,))
                    episode.update(
                        step=receipt.step, state_digest=receipt.next_state_digest, terminal=receipt.terminal
                    )
                    if receipt.terminal or receipt.step >= binding["spec"]["max_episode_steps"]:
                        episode["status"] = "completed" if receipt.terminal else "truncated"
                self._store_episode(db, episode)
                if episode["status"] != "running":
                    return self._finish(db, binding, episode)

    @staticmethod
    def _environment_spec(binding: dict):
        from .post_training import RLEnvironmentSpec

        return RLEnvironmentSpec(**binding["environment"]["spec"])

    def _episode_reference(self, db, binding: dict, ref: str) -> ExecutedEpisodeReceipt:
        row = db.execute(
            "SELECT run_id,episode_id,payload FROM post_episode_evidence WHERE receipt_digest=?", (ref,)
        ).fetchone()
        if row is None or row[0] != binding["spec"]["run_id"]:
            raise PostTrainingExecutionError("episode reference was not issued for this execution")
        episode = self._episode(db, row[1])
        receipt = self._finish(db, binding, episode)
        if receipt.receipt_digest != ref or _digest(json.loads(row[2])) != ref:
            raise PostTrainingExecutionError("episode reference identity drift")
        return receipt

    @staticmethod
    def _episode_metrics(episodes: Sequence[ExecutedEpisodeReceipt]) -> dict[str, float]:
        rewards = [item.total_reward for item in episodes]
        return {
            "mean_reward": sum(rewards) / len(episodes),
            "total_reward": sum(rewards),
            "terminal_rate": sum(item.terminal for item in episodes) / len(episodes),
            "steps": float(sum(item.steps for item in episodes)),
        }

    def _curriculum_evidence(self, db, binding: dict, ref: str, encoded: str) -> dict:
        try:
            payload = json.loads(encoded)
            if (
                _digest(payload) != ref
                or payload["run_id"] != binding["spec"]["run_id"]
                or payload["binding_digest"] != _digest(binding)
                or payload["curriculum_digest"] != binding["spec"]["curriculum_digest"]
            ):
                raise ValueError("curriculum identity mismatch")
            episodes = [
                self._episode_reference(db, binding, item)
                for item in self._references(payload["episode_refs"])
            ]
            if any(item.status not in {"completed", "truncated"} for item in episodes):
                raise ValueError("invalid episode outcome")
            decision = CurriculumDecision(**payload["decision"])
            engine = CurriculumEngine(tuple(CurriculumStage(**stage) for stage in binding["curriculum"]))
            expected = engine.decide(
                decision.stage_id,
                metrics=self._episode_metrics(episodes),
                completed=decision.completed_before,
            )
            if expected != decision:
                raise ValueError("curriculum metric mismatch")
            issued = db.execute(
                "SELECT stage_id,payload FROM curriculum_decision WHERE decision_digest=?", (decision.digest,)
            ).fetchone()
            if issued != (decision.stage_id, _canonical(decision.as_dict())):
                raise ValueError("curriculum canonical evidence mismatch")
        except (ValueError, TypeError, KeyError) as exc:
            raise PostTrainingExecutionError("curriculum evidence integrity failure") from exc
        return payload

    def evaluate_stage(
        self, run_id: str, *, curriculum: CurriculumEngine, stage_id: str, episode_refs: Sequence[str]
    ) -> ExecutedCurriculumReceipt:
        refs = self._references(episode_refs)
        with self.ledger.execution_transaction() as db:
            binding, status, *_ = self._execution(db, run_id)
            if status != "active" or _curriculum_payload(curriculum) != binding["curriculum"]:
                raise PostTrainingExecutionError("curriculum identity is changed or execution is inactive")
            episodes = [self._episode_reference(db, binding, ref) for ref in refs]
            if any(item.status not in {"completed", "truncated"} for item in episodes):
                raise PostTrainingExecutionError(
                    "cancelled or exhausted episodes cannot authorize curriculum advancement"
                )
            metrics = self._episode_metrics(episodes)
            completed = []
            for prior_ref, encoded in db.execute(
                "SELECT receipt_digest,payload FROM post_curriculum_evidence WHERE run_id=?", (run_id,)
            ).fetchall():
                recorded = self._curriculum_evidence(db, binding, prior_ref, encoded)
                if recorded["decision"]["status"] in {"advance", "already_complete"}:
                    completed.append(recorded["decision"]["stage_id"])
            decision = curriculum.decide(stage_id, metrics=metrics, completed=tuple(sorted(set(completed))))
            payload = {
                "run_id": run_id,
                "binding_digest": _digest(binding),
                "curriculum_digest": binding["spec"]["curriculum_digest"],
                "episode_refs": list(refs),
                "decision": decision.as_dict(),
            }
            digest = _digest(payload)
            existing = db.execute(
                "SELECT stage_id,payload FROM curriculum_decision WHERE decision_digest=?", (decision.digest,)
            ).fetchone()
            if existing is not None and existing != (decision.stage_id, _canonical(decision.as_dict())):
                raise PostTrainingExecutionError("canonical curriculum evidence identity drift")
            db.execute(
                "INSERT OR IGNORE INTO curriculum_decision VALUES (?,?,?)",
                (decision.digest, decision.stage_id, _canonical(decision.as_dict())),
            )
            db.execute(
                "INSERT OR IGNORE INTO post_curriculum_evidence VALUES (?,?,?)",
                (digest, run_id, _canonical(payload)),
            )
            return ExecutedCurriculumReceipt(
                run_id, _digest(binding), binding["spec"]["curriculum_digest"], refs, decision, digest
            )

    @staticmethod
    def _references(refs: Sequence[str]) -> tuple[str, ...]:
        if isinstance(refs, (str, bytes)) or not 1 <= len(refs) <= 128:
            raise ValueError("evidence references must contain 1 to 128 entries")
        normalized = tuple(_require_digest(ref, field="evidence reference") for ref in refs)
        if len(set(normalized)) != len(normalized):
            raise ValueError("evidence references must be unique")
        return normalized

    async def evaluate_candidate(
        self,
        run_id: str,
        *,
        model: LocalModelBackend,
        suite: EvaluationSuite,
        verifier_id: str,
        seed: int = 0,
    ) -> ExecutedEvaluationReceipt:
        verifier = _text(verifier_id, "verifier_id")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError("evaluation seed must be an integer")
        with self.ledger.execution_transaction() as db:
            binding, status, evaluation_epoch, *_ = self._execution(db, run_id)
            if (
                status != "active"
                or model.model_digest != binding["spec"]["model_digest"]
                or suite.digest != binding["spec"]["evaluation_suite_digest"]
            ):
                raise PostTrainingExecutionError(
                    "evaluation model/suite identity mismatch or inactive execution"
                )
            if verifier in {binding["spec"]["trainer_id"], binding["policy"]["policy_id"]}:
                raise PostTrainingExecutionError("candidate evaluation requires independent verifier")
            if (
                suite.population not in {"test", "heldout", "holdout"}
                or len(suite.cases) > 128
                or len(_canonical(suite.as_dict()).encode("utf-8")) > 256 * 1024
                or any(case.max_output_tokens > 128 for case in suite.cases)
            ):
                raise PostTrainingExecutionError("candidate evaluation requires bounded held-out suite")
            request = _digest({"binding_digest": _digest(binding), "verifier_id": verifier, "seed": seed})
            existing = db.execute(
                "SELECT receipt_digest,payload FROM post_evaluation_evidence WHERE request_digest=?",
                (request,),
            ).fetchone()
            if existing is not None:
                return self._evaluation_receipt(binding, existing[0], existing[1])
        suite_digest = suite.digest
        result = await EvaluationHarness().evaluate(model, suite, seed=seed)
        if model.model_digest != binding["spec"]["model_digest"] or suite.digest != suite_digest:
            raise PostTrainingExecutionError("evaluation identity changed during execution")
        payload = {
            "run_id": run_id,
            "binding_digest": _digest(binding),
            "model_digest": model.model_digest,
            "suite_digest": suite_digest,
            "result_digest": result.digest,
            "verifier_id": verifier,
            "seed": seed,
            "suite": suite.as_dict(),
            "result": result.as_dict(),
        }
        if len(_canonical(payload).encode("utf-8")) > 1024 * 1024:
            raise PostTrainingExecutionError("measured evaluation payload byte budget exceeded")
        digest = _digest(payload)
        with self.ledger.execution_transaction() as db:
            current, status, current_epoch, *_ = self._execution(db, run_id)
            if current != binding or status != "active" or current_epoch != evaluation_epoch:
                raise PostTrainingExecutionError("evaluation execution was cancelled or rebound")
            previous = db.execute(
                "SELECT receipt_digest,payload FROM post_evaluation_evidence WHERE request_digest=?",
                (request,),
            ).fetchone()
            if previous is not None:
                if previous != (digest, _canonical(payload)):
                    raise PostTrainingExecutionError("concurrent evaluation produced conflicting evidence")
            else:
                db.execute(
                    "INSERT INTO post_evaluation_evidence VALUES (?,?,?,?)",
                    (digest, run_id, request, _canonical(payload)),
                )
        return self._evaluation_receipt(binding, digest, _canonical(payload))

    def _evaluation_receipt(self, binding: dict, ref: str, encoded: str) -> ExecutedEvaluationReceipt:
        try:
            payload = json.loads(encoded)
            if (
                _digest(payload) != ref
                or payload["binding_digest"] != _digest(binding)
                or payload["model_digest"] != binding["spec"]["model_digest"]
                or payload["suite_digest"] != binding["spec"]["evaluation_suite_digest"]
            ):
                raise ValueError("evaluation identity mismatch")
            suite_payload = dict(payload["suite"])
            claimed_suite = suite_payload.pop("suite_digest")
            result_payload = dict(payload["result"])
            accuracy = result_payload.pop("accuracy")
            result = EvaluationResult(**result_payload)
            cases = {item["case_id"]: item for item in suite_payload["cases"]}
            passed = {
                key
                for key, case in cases.items()
                if evaluation_case_passes(EvaluationCase(**case), result.outputs[key])
            }
            if (
                claimed_suite != payload["suite_digest"]
                or _digest(suite_payload) != claimed_suite
                or result.digest != payload["result_digest"]
                or result.suite_digest != claimed_suite
                or result.candidate_model_digest != payload["model_digest"]
                or result.accuracy != accuracy
                or set(result.outputs) != set(cases)
                or set(result.passed_case_ids) != passed
                or set(result.failed_case_ids) != set(cases) - passed
            ):
                raise ValueError("evaluation measured evidence mismatch")
        except (ValueError, TypeError, KeyError) as exc:
            raise PostTrainingExecutionError("evaluation evidence integrity failure") from exc
        return ExecutedEvaluationReceipt(
            payload["run_id"],
            _digest(binding),
            payload["model_digest"],
            payload["suite_digest"],
            payload["result_digest"],
            payload["verifier_id"],
            result.total > 0 and result.accuracy == 1.0,
            ref,
        )

    def qualify_candidate(
        self, run_id: str, *, curriculum_refs: Sequence[str], evaluation_ref: str, verifier_id: str
    ) -> PostTrainingQualificationReceipt:
        refs = self._references(curriculum_refs)
        with self.ledger.execution_transaction() as db:
            binding, status, *_ = self._execution(db, run_id)
            verifier = _text(verifier_id, "verifier_id")
            if status not in {"active", "qualified"} or verifier in {
                binding["spec"]["trainer_id"],
                binding["policy"]["policy_id"],
            }:
                raise PostTrainingExecutionError(
                    "qualification requires active execution and independent verifier"
                )
            stages = {}
            for ref in refs:
                row = db.execute(
                    "SELECT run_id,payload FROM post_curriculum_evidence WHERE receipt_digest=?", (ref,)
                ).fetchone()
                if row is None or row[0] != run_id:
                    raise PostTrainingExecutionError("curriculum evidence was not issued for this execution")
                payload = self._curriculum_evidence(db, binding, ref, row[1])
                stage = payload["decision"]["stage_id"]
                if stage in stages:
                    raise PostTrainingExecutionError("qualification cannot duplicate curriculum stages")
                stages[stage] = payload["decision"]["status"]
            if set(stages) != {item["stage_id"] for item in binding["curriculum"]}:
                raise PostTrainingExecutionError("qualification requires exact curriculum stage coverage")
            row = db.execute(
                "SELECT run_id,payload FROM post_evaluation_evidence WHERE receipt_digest=?",
                (evaluation_ref,),
            ).fetchone()
            if row is None or row[0] != run_id:
                raise PostTrainingExecutionError("evaluation evidence was not issued for this execution")
            evaluation = self._evaluation_receipt(binding, evaluation_ref, row[1])
            passed = evaluation.passed and all(
                value in {"advance", "already_complete"} for value in stages.values()
            )
            payload = {
                "run_id": run_id,
                "model_digest": binding["spec"]["model_digest"],
                "policy_digest": binding["spec"]["policy_digest"],
                "binding_digest": _digest(binding),
                "curriculum_refs": list(refs),
                "evaluation_ref": evaluation_ref,
                "verifier_id": verifier,
                "status": "qualified_candidate" if passed else "rejected",
                "production_promotion_authorized": False,
            }
            digest = _digest(payload)
            db.execute(
                "INSERT OR IGNORE INTO post_qualification VALUES (?,?,?)",
                (digest, run_id, _canonical(payload)),
            )
            if passed:
                db.execute("UPDATE post_execution SET status='qualified' WHERE run_id=?", (run_id,))
            return PostTrainingQualificationReceipt(
                **{**payload, "curriculum_refs": refs, "receipt_digest": digest}
            )

    def cancel(self, run_id: str) -> None:
        with self.ledger.execution_transaction() as db:
            _, status, *_ = self._execution(db, run_id)
            if status == "cancelled":
                return
            if status != "active":
                raise PostTrainingExecutionError("terminal execution cannot be cancelled")
            db.execute(
                "UPDATE post_execution SET status='cancelled',epoch=epoch+1,token='' WHERE run_id=?",
                (run_id,),
            )

    def status(self, run_id: str) -> dict[str, object]:
        with self.ledger.execution_transaction() as db:
            binding, status, epoch, _, steps, episodes = self._execution(db, run_id)
            return {
                "run_id": run_id,
                "binding_digest": _digest(binding),
                "status": status,
                "worker_epoch": epoch,
                "steps": steps,
                "episodes": episodes,
            }


__all__ = [
    "ExecutedCurriculumReceipt",
    "ExecutedEpisodeReceipt",
    "ExecutedEvaluationReceipt",
    "LocalPolicyObservation",
    "LocalPostTrainingPolicy",
    "PostTrainingExecutionError",
    "PostTrainingExecutionSpec",
    "PostTrainingQualificationReceipt",
    "PostTrainingRunner",
]
