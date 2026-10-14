"""Recorded human control, replay verification and actual imitation/Q learning.

Uploaded JSON can describe an episode but cannot mint a measured issuer receipt.
Application-owned authorization remains necessary. Process-local receipts are
issued only after actual replay or by the parent of a validated actor process.
Human feedback changes an authored action prior; it never fabricates game reward.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .game_learning import (
    TRACE_SCHEMA,
    GameLearningConfig,
    GameLearningError,
    GamePolicyLearner,
    _copy_json,
    _descriptor,
    _digest,
    _int,
    _json,
    _name,
    _sha,
)

DEMONSTRATION_SCHEMA = "skeleton.game.demonstration.v1"
_ISSUER = object()


@dataclass(frozen=True, slots=True)
class VerifiedGameEpisode:
    _trace_json: bytes = field(repr=False)
    source: str
    evidence_digest: str
    _issuer: object = field(repr=False)

    @property
    def trace(self) -> dict[str, Any]:
        import json

        return json.loads(self._trace_json)


def _issue_verified_episode(
    trace: Mapping[str, Any], source: str, evidence_digest: str
) -> VerifiedGameEpisode:
    if source not in ("local_actor_rollout", "human_demonstration"):
        raise GameLearningError("measured episode issuer source differs")
    return VerifiedGameEpisode(_json(trace), source, _sha(evidence_digest, "episode evidence"), _ISSUER)


def _require_verified_episode(value: Any) -> VerifiedGameEpisode:
    if not isinstance(value, VerifiedGameEpisode) or value._issuer is not _ISSUER:
        raise GameLearningError("a process-local measured episode receipt is required")
    return value


@dataclass(frozen=True, slots=True)
class VerifiedGameFeedback:
    _payload_json: bytes = field(repr=False)
    evidence_digest: str
    _issuer: object = field(repr=False)

    def _payload(self) -> dict[str, Any]:
        import json

        return json.loads(self._payload_json)

    @property
    def environment_digest(self) -> str:
        return self._payload()["environment_digest"]

    @property
    def observation(self) -> dict[str, float]:
        return self._payload()["observation"]

    @property
    def action(self) -> str:
        return self._payload()["action"]

    @property
    def weight(self) -> int:
        return self._payload()["weight"]

    @property
    def source_lineage(self) -> dict[str, Any]:
        return self._payload()["source_lineage"]


def _require_verified_feedback(value: Any) -> VerifiedGameFeedback:
    if not isinstance(value, VerifiedGameFeedback) or value._issuer is not _ISSUER:
        raise GameLearningError("a process-local authored feedback receipt is required")
    if _digest(value._payload()) != value.evidence_digest:
        raise GameLearningError("authored feedback receipt identity differs")
    return value


def _validator(spec: Any, lineage: Mapping[str, Any]) -> GamePolicyLearner:
    return GamePolicyLearner(
        spec, GameLearningConfig(), policy_id="recording-validator", source_lineage=lineage
    )


def current_observation(environment: Any, restored: Any = None) -> dict[str, float]:
    """Use the approved adapter's actual state projection after restoration."""
    if isinstance(restored, Mapping) and set(restored) == set(environment.spec.observation_bins):
        return dict(restored)
    observe = getattr(environment, "observe", None)
    if callable(observe):
        result = observe()
        if isinstance(result, Mapping) and isinstance(result.get("observation"), Mapping):
            return dict(result["observation"])
    for name in ("current_observation", "_observation"):
        projection = getattr(environment, name, None)
        if callable(projection):
            projection = projection()
        if isinstance(projection, Mapping):
            return dict(projection)
    raise GameLearningError("approved adapter does not expose a current observation after restore")


def close_environment(environment: Any) -> None:
    close = getattr(environment, "close", None)
    if callable(close):
        close()


def environment_snapshot_digest(environment: Any) -> str:
    snapshot = environment.snapshot()
    if not isinstance(snapshot, Mapping):
        raise GameLearningError("approved environment snapshot must be an object")
    # Native owners may issue large bounded savestates; use their checked
    # canonical identity rather than recopying bytes into the rollout receipt.
    for label in ("snapshot_digest", "state_digest", "digest"):
        if label in snapshot:
            return _sha(snapshot[label], "approved environment snapshot")
    return _digest(snapshot)


class GameDemonstrationRecorder:
    def __init__(
        self,
        spec: Any,
        *,
        episode_id: str,
        seed: int,
        source_lineage: Mapping[str, Any],
        actor_id: str,
        consent_ref: str,
        initial_observation: Mapping[str, float],
        start_snapshot: Mapping[str, Any] | None = None,
    ) -> None:
        self._validator = _validator(spec, source_lineage)
        self._environment = _descriptor(spec)
        self._episode_id = _name(episode_id, "demonstration episode identity")
        self._seed = _int(seed, "demonstration seed", 0, 2**63 - 1)
        self._lineage = _copy_json(dict(source_lineage), limit=65536)
        self._actor_id = _name(actor_id, "human actor identity")
        self._consent_ref = _name(consent_ref, "human learning consent reference")
        self._initial = self._validator._observation(initial_observation)
        self._observation = dict(self._initial)
        self._start = None if start_snapshot is None else _copy_json(dict(start_snapshot))
        self._transitions: list[dict[str, Any]] = []
        self._bytes = 0
        self._closed = False

    def append(
        self,
        action: str,
        next_observation: Mapping[str, float],
        reward_components: Mapping[str, float],
        terminated: bool,
        truncated: bool,
        *,
        info: Mapping[str, Any] | None = None,
        transition_digest: str | None = None,
    ) -> None:
        if (
            self._closed
            or self._transitions
            and (self._transitions[-1]["terminated"] or self._transitions[-1]["truncated"])
        ):
            raise GameLearningError("demonstration recording already ended")
        if len(self._transitions) >= self._environment["max_episode_steps"]:
            raise GameLearningError("demonstration step budget exhausted")
        data: dict[str, Any] = {
            "sequence": len(self._transitions) + 1,
            "observation": self._observation,
            "action": action,
            "next_observation": next_observation,
            "reward_components": reward_components,
            "reward": math.fsum(reward_components.values()),
            "terminated": terminated,
            "truncated": truncated,
        }
        if info is not None:
            data["info"] = info
        if transition_digest:
            data["transition_digest"] = transition_digest
        transition = self._validator._transition(data, len(self._transitions) + 1)
        size = len(_json(transition))
        if self._bytes + size > self._validator.config.trace_byte_limit:
            raise GameLearningError("demonstration trace byte budget exhausted")
        self._bytes += size
        self._transitions.append(transition)
        self._observation = transition["next_observation"]

    def finish(self, *, collection_stopped: bool = False) -> GameDemonstration:
        if self._closed or not self._transitions or type(collection_stopped) is not bool:
            raise GameLearningError("demonstration is empty, already closed or has an invalid stop flag")
        transitions = _copy_json(self._transitions)
        last = transitions[-1]
        if not (last["terminated"] or last["truncated"]):
            if not collection_stopped:
                raise GameLearningError("unfinished demonstration needs an explicit authored collection stop")
            last["truncated"] = True
        elif collection_stopped:
            raise GameLearningError("native terminal episode must retain its actual termination reason")
        trace = {
            "schema_version": TRACE_SCHEMA,
            "environment": self._environment,
            "episode_id": self._episode_id,
            "seed": self._seed,
            "source_lineage": self._lineage,
            "transitions": transitions,
            "return": math.fsum(step["reward"] for step in transitions),
            "steps": len(transitions),
        }
        trace["trace_digest"] = _digest(trace)
        self._validator.validate_trace(trace)
        payload = {
            "schema_version": DEMONSTRATION_SCHEMA,
            "trace": trace,
            "actor_id": self._actor_id,
            "consent_ref": self._consent_ref,
            "initial_observation": self._initial,
            "start_snapshot": self._start,
            "collection_stopped": collection_stopped,
        }
        payload["demonstration_digest"] = _digest(payload)
        demonstration = GameDemonstration.from_dict(payload)
        self._closed = True
        return demonstration


@dataclass(frozen=True, slots=True)
class GameDemonstration:
    _payload_json: bytes = field(repr=False)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> GameDemonstration:
        if not isinstance(value, Mapping):
            raise GameLearningError("human demonstration must be an object")
        raw = _copy_json(dict(value))
        if (
            set(raw)
            != {
                "schema_version",
                "trace",
                "actor_id",
                "consent_ref",
                "initial_observation",
                "start_snapshot",
                "collection_stopped",
                "demonstration_digest",
            }
            or raw["schema_version"] != DEMONSTRATION_SCHEMA
        ):
            raise GameLearningError("human demonstration schema differs")
        digest = _sha(raw["demonstration_digest"], "human demonstration")
        if _digest({key: item for key, item in raw.items() if key != "demonstration_digest"}) != digest:
            raise GameLearningError("human demonstration digest differs")
        _name(raw["actor_id"], "human actor identity")
        _name(raw["consent_ref"], "human consent reference")
        if (
            type(raw["collection_stopped"]) is not bool
            or raw["start_snapshot"] is not None
            and not isinstance(raw["start_snapshot"], dict)
        ):
            raise GameLearningError("human demonstration collection origin differs")
        if not isinstance(raw["trace"], dict) or not isinstance(raw["initial_observation"], dict):
            raise GameLearningError("human demonstration lacks its recorded transition chain")
        return cls(_json(raw))

    def as_dict(self) -> dict[str, Any]:
        import json

        return json.loads(self._payload_json)

    @property
    def digest(self) -> str:
        return self.as_dict()["demonstration_digest"]

    def verify(
        self,
        request: Any,
        *,
        cancel: Callable[[], bool] | None = None,
        authorize: Callable[[], None] | None = None,
    ) -> VerifiedGameEpisode:
        if not callable(authorize):
            raise GameLearningError(
                "human origin and current consent require an application authorization callback"
            )
        payload = self.as_dict()
        environment = None
        try:
            GamePolicyLearner._guard(cancel, authorize)
            environment = request.build(cancel=cancel)
            validator = _validator(environment.spec, payload["trace"]["source_lineage"])
            trace = validator.validate_trace(payload["trace"])
            if payload["start_snapshot"] is None:
                observation = dict(environment.reset(trace["seed"]))
            else:
                restored = environment.restore(payload["start_snapshot"])
                observation = current_observation(environment, restored)
            observation = validator._observation(observation)
            if (
                observation != validator._observation(payload["initial_observation"])
                or observation != trace["transitions"][0]["observation"]
            ):
                raise GameLearningError("demonstration initial observation differs from actual replay")
            for index, row in enumerate(trace["transitions"]):
                GamePolicyLearner._guard(cancel, authorize)
                if validator._observation(row["observation"]) != observation:
                    raise GameLearningError("demonstration observation differs from actual replay")
                step = environment.step(row["action"])
                actual = {
                    "sequence": index + 1,
                    "observation": observation,
                    "action": row["action"],
                    "next_observation": step.observation,
                    "reward_components": step.reward_components,
                    "reward": math.fsum(step.reward_components.values()),
                    "terminated": step.terminated,
                    "truncated": step.truncated,
                }
                if "info" in row:
                    actual["info"] = step.info
                if "transition_digest" in row:
                    actual["transition_digest"] = step.transition_digest
                normalized = validator._transition(actual, index + 1)
                if payload["collection_stopped"] and index == len(trace["transitions"]) - 1:
                    if normalized["terminated"] or normalized["truncated"]:
                        raise GameLearningError("authored collection stop conflicts with native termination")
                    normalized["truncated"] = True
                if normalized != validator._transition(row, index + 1):
                    raise GameLearningError(
                        "demonstration actions/rewards/native evidence differ from actual replay"
                    )
                observation = normalized["next_observation"]
            GamePolicyLearner._guard(cancel, authorize)
            proof = _digest(
                {
                    "demonstration_digest": payload["demonstration_digest"],
                    "trace_digest": trace["trace_digest"],
                    "environment_digest": environment.spec.environment_digest,
                    "actual_final_snapshot_digest": environment_snapshot_digest(environment),
                }
            )
            return _issue_verified_episode(trace, "human_demonstration", proof)
        finally:
            if environment is not None:
                close_environment(environment)


def learn_demonstrations(
    learner: GamePolicyLearner,
    request: Any,
    recordings: Sequence[GameDemonstration | Mapping[str, Any]],
    *,
    imitation_strength: float | None = None,
    on_checkpoint: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
    cancel: Callable[[], bool] | None = None,
    authorize: Callable[[], None] | None = None,
) -> dict[str, Any]:
    if not isinstance(recordings, (tuple, list)) or not 1 <= len(recordings) <= 256:
        raise GameLearningError("human demonstration batch exceeds its count budget")
    if imitation_strength is not None and imitation_strength != learner.config.imitation_strength:
        raise GameLearningError("imitation strength differs from the pinned policy configuration")
    summaries = []
    updates = 0
    for raw in recordings:
        recording = raw if isinstance(raw, GameDemonstration) else GameDemonstration.from_dict(raw)
        verified = recording.verify(request, cancel=cancel, authorize=authorize)
        result = learner.learn_verified_episode(
            verified, on_checkpoint=on_checkpoint, cancel=cancel, authorize=authorize
        )
        updates += result.updates
        summaries.extend(result.episode_summaries)
    return {
        "snapshot": learner.snapshot(),
        "episode_summaries": summaries,
        "updates": updates,
        "imitation_observations": learner.snapshot()["imitation_observations"],
        "source": "human_demonstration",
    }


def authored_feedback(
    spec: Any,
    *,
    observation: Mapping[str, float],
    action: str,
    weight: int,
    source_lineage: Mapping[str, Any],
    actor_id: str,
    consent_ref: str,
    feedback_id: str,
    authorize: Callable[[], None],
) -> VerifiedGameFeedback:
    if not callable(authorize):
        raise GameLearningError("authored feedback requires current application authorization")
    authorize()
    validator = _validator(spec, source_lineage)
    observed = validator._observation(observation)
    if action not in validator.descriptor["actions"]:
        raise GameLearningError("authored feedback action is not a policy action")
    _int(weight, "authored preference weight", -16, 16)
    if weight == 0:
        raise GameLearningError("authored preference weight cannot be zero")
    payload = {
        "schema_version": "skeleton.game.authored_feedback.v1",
        "environment_digest": spec.environment_digest,
        "observation": observed,
        "action": action,
        "weight": weight,
        "source_lineage": dict(source_lineage),
        "actor_id": _name(actor_id, "feedback actor"),
        "consent_ref": _name(consent_ref, "feedback consent"),
        "feedback_id": _name(feedback_id, "feedback identity"),
        "semantics": "authored action preference; no environment reward or success assertion",
    }
    return VerifiedGameFeedback(_json(payload), _digest(payload), _ISSUER)
