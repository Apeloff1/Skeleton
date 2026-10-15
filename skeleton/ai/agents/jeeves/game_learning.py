"""Bounded measured tabular game-policy learning under the Jeeves owner.

An application supplies environments and its existing authority callbacks. This
module performs real Q updates and paired environment evaluations, but owns no
database, production promotion, hardware emulation or source-rights authority.
Snapshots commit at episode boundaries. A failed episode or rejected checkpoint
restores the preceding complete policy, including exploration random state.
"""

from __future__ import annotations

import bisect
import copy
import hashlib
import json
import math
import random
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from functools import wraps
from itertools import pairwise
from pathlib import Path
from typing import Any

from .game_learning_runtime import EpisodeStep, GameEnvironmentSpec

POLICY_SCHEMA = "skeleton.jeeves.game_learning_policy.v2"
TRACE_SCHEMA = "skeleton.game.trace.v1"
ALGORITHM = "tabular_q_learning_v1"
MAX_BYTES = 8 * 1024 * 1024
MAX_LIFETIME_EPISODES = 65536
MAX_LIFETIME_UPDATES = 16777216


def _exclusive(method: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(method)
    def invoke(self: Any, *args: Any, **kwargs: Any) -> Any:
        with self.operation():
            return method(self, *args, **kwargs)

    return invoke


class GameLearningError(ValueError):
    """Invalid learning input, evidence, identity or exhausted resource budget."""


class GameLearningCancelled(GameLearningError):
    """The application cancelled learning before another durable episode."""


def _plain(value: Any, *, depth: int = 0, nodes: list[int] | None = None) -> Any:
    if nodes is None:
        nodes = [0]
    nodes[0] += 1
    if depth > 24 or nodes[0] > 500000:
        raise GameLearningError("learning JSON structural budget exceeded")
    if value is None or type(value) in (str, bool, int, float):
        return value
    if isinstance(value, Mapping):
        if len(value) > 16384 or any(not isinstance(key, str) for key in value):
            raise GameLearningError("learning JSON object keys or size differ")
        return {key: _plain(item, depth=depth + 1, nodes=nodes) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        if len(value) > 65536:
            raise GameLearningError("learning JSON sequence budget exceeded")
        return [_plain(item, depth=depth + 1, nodes=nodes) for item in value]
    raise GameLearningError("learning evidence contains unsupported JSON values")


def _json(value: Any, *, limit: int = MAX_BYTES) -> bytes:
    try:
        data = json.dumps(
            _plain(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError) as exc:
        raise GameLearningError("learning evidence must be finite JSON") from exc
    if len(data) > limit:
        raise GameLearningError("learning evidence byte budget exceeded")
    return data


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _copy_json(value: Any, *, limit: int = MAX_BYTES) -> Any:
    return json.loads(_json(value, limit=limit))


def _int(value: Any, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise GameLearningError(f"{label} must be an integer in [{minimum}, {maximum}]")
    return value


def _number(value: Any, label: str, maximum: float = 1e12) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise GameLearningError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise GameLearningError(f"{label} must be finite") from exc
    if not math.isfinite(result) or abs(result) > maximum:
        raise GameLearningError(f"{label} exceeds finite numeric bounds")
    return result


def _name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256 or any(ord(char) < 32 for char in value):
        raise GameLearningError(f"invalid {label}")
    return value


def _sha(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise GameLearningError(f"invalid {label} digest")
    return value


def _descriptor(spec: GameEnvironmentSpec | Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "environment_id",
        "environment_digest",
        "actions",
        "observation_bins",
        "reward_components",
        "max_episode_steps",
    )
    if isinstance(spec, Mapping):
        if set(spec) != set(fields):
            raise GameLearningError("environment descriptor fields differ")
        raw = dict(spec)
    else:
        try:
            raw = {key: getattr(spec, key) for key in fields}
        except AttributeError as exc:
            raise GameLearningError("environment descriptor is incomplete") from exc
    result: dict[str, Any] = {
        "environment_id": _name(raw["environment_id"], "environment identity"),
        "environment_digest": _sha(raw["environment_digest"], "environment"),
        "max_episode_steps": _int(raw["max_episode_steps"], "episode steps", 1, 4096),
    }
    for key, maximum in (("actions", 32), ("reward_components", 16)):
        values = raw[key]
        if not isinstance(values, (tuple, list)) or not 1 <= len(values) <= maximum:
            raise GameLearningError(f"invalid declared {key}")
        names = [_name(value, key) for value in values]
        if any(len(name) > 64 for name in names):
            raise GameLearningError(f"declared {key} identity exceeds capacity")
        if len(set(names)) != len(names):
            raise GameLearningError(f"duplicate declared {key}")
        result[key] = names
    bins = raw["observation_bins"]
    if not isinstance(bins, Mapping) or not 1 <= len(bins) <= 32:
        raise GameLearningError("invalid observation feature budget")
    normalized: dict[str, list[float]] = {}
    for key in bins:
        _name(key, "observation feature")
        if len(key) > 64:
            raise GameLearningError("observation feature identity exceeds capacity")
    for key in sorted(bins):
        thresholds = bins[key]
        if not isinstance(thresholds, (list, tuple)) or not 1 <= len(thresholds) <= 64:
            raise GameLearningError("invalid observation threshold budget")
        numbers = [_number(value, "observation threshold") for value in thresholds]
        if any(right <= left for left, right in pairwise(numbers)):
            raise GameLearningError("observation thresholds must strictly increase")
        normalized[key] = numbers
    result["observation_bins"] = normalized
    return result


def _runtime() -> dict[str, Any]:
    return {
        "algorithm": ALGORITHM,
        "implementation_digest": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python": list(sys.version_info[:3]),
        "random_state_version": 3,
    }


@dataclass(frozen=True, slots=True)
class GameLearningConfig:
    alpha: float = 0.25
    gamma: float = 0.95
    epsilon: float = 0.3
    epsilon_decay: float = 0.98
    min_epsilon: float = 0.03
    seed: int = 0
    max_updates: int = 65536
    max_states: int = 16384
    max_episodes: int = 1024
    reward_clip: float = 100.0
    trace_byte_limit: int = MAX_BYTES
    imitation_strength: float = 1.0

    def __post_init__(self) -> None:
        for key in ("alpha", "gamma", "epsilon", "epsilon_decay", "min_epsilon"):
            number = _number(getattr(self, key), key, 1.0)
            if not 0 <= number <= 1 or (key in ("alpha", "epsilon_decay") and number == 0):
                raise GameLearningError(f"{key} outside its learning range")
            object.__setattr__(self, key, number)
        if self.min_epsilon > self.epsilon:
            raise GameLearningError("minimum epsilon exceeds initial epsilon")
        _int(self.seed, "seed", 0, 2**63 - 1)
        _int(self.max_updates, "update budget", 1, 1048576)
        _int(self.max_states, "state budget", 1, 16384)
        _int(self.max_episodes, "episode budget", 1, 8192)
        _int(self.trace_byte_limit, "trace byte budget", 1024, MAX_BYTES)
        clip = _number(self.reward_clip, "reward clip", 1e6)
        if clip <= 0:
            raise GameLearningError("reward clip must be positive")
        object.__setattr__(self, "reward_clip", clip)
        strength = _number(self.imitation_strength, "imitation strength", 16.0)
        if strength < 0:
            raise GameLearningError("imitation strength cannot be negative")
        object.__setattr__(self, "imitation_strength", strength)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GameTrainingResult:
    snapshot: dict[str, Any]
    episode_summaries: tuple[dict[str, Any], ...]
    traces: tuple[dict[str, Any], ...]
    updates: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "snapshot": _copy_json(self.snapshot),
            "episode_summaries": _copy_json(self.episode_summaries),
            "traces": _copy_json(self.traces),
            "updates": self.updates,
            "algorithm": ALGORITHM,
        }


@dataclass(frozen=True, slots=True)
class GameEvaluationResult:
    evidence: dict[str, Any]

    @property
    def digest(self) -> str:
        return self.evidence["evaluation_digest"]

    def as_dict(self) -> dict[str, Any]:
        return _copy_json(self.evidence)


class GamePolicyLearner:
    """An episode-atomic, deterministic, sparse tabular action policy."""

    def __init__(
        self,
        spec: GameEnvironmentSpec,
        config: GameLearningConfig,
        *,
        policy_id: str,
        source_lineage: Mapping[str, Any],
        parent_snapshot: Mapping[str, Any] | None = None,
    ) -> None:
        self.spec = spec
        self.descriptor = _descriptor(spec)
        if not isinstance(config, GameLearningConfig):
            raise GameLearningError("typed learning configuration required")
        self.config = config
        self.policy_id = _name(policy_id, "policy identity")
        if not isinstance(source_lineage, Mapping) or not source_lineage:
            raise GameLearningError("explicit source lineage required")
        self.source_lineage = _copy_json(dict(source_lineage), limit=65536)
        if self.source_lineage.get("rights_acknowledged") is False:
            raise GameLearningError("source lineage explicitly denies rights")
        for label in ("admitted_traces", "admitted_feedback"):
            admitted = self.source_lineage.get(label, {})
            if not isinstance(admitted, dict) or len(admitted) > 256:
                raise GameLearningError("admitted authored evidence lineage budget differs")
            for receipt_digest, lineage in admitted.items():
                _sha(receipt_digest, "admitted authored evidence")
                if not isinstance(lineage, dict) or not lineage:
                    raise GameLearningError("admitted authored evidence lineage must be explicit")
        self._runtime = _runtime()
        self._features = tuple(self.descriptor["observation_bins"])
        self._actions = tuple(self.descriptor["actions"])
        self._q: dict[tuple[int, ...], list[float]] = {}
        self._visits: dict[tuple[int, ...], list[int]] = {}
        self._imitation: dict[tuple[int, ...], tuple[list[int], list[int]]] = {}
        self._imitation_total = 0
        self._imitation_receipts: list[dict[str, Any]] = []
        self._rng = random.Random(config.seed)
        self._episodes: list[dict[str, Any]] = []
        self._updates = 0
        self._inherited_episodes: list[dict[str, Any]] = []
        self._inherited_updates = 0
        self._inherited_q_bound = 0.0
        self._parent_snapshot_digest: str | None = None
        self._parent_policy_id: str | None = None
        self._previous_snapshot_digest: str | None = None
        self._snapshot_digest_cache: str | None = None
        self._busy = False
        self._operation_lock = threading.RLock()
        if parent_snapshot is not None:
            restored = type(self).from_snapshot(
                parent_snapshot,
                expected_spec=spec,
                expected_config=config,
                expected_source_lineage=self.source_lineage,
            )
            if restored.policy_id != self.policy_id:
                raise GameLearningError("resume policy identity differs")
            self._adopt(restored._capture())

    @property
    def snapshot_digest(self) -> str:
        if self._snapshot_digest_cache is None:
            self._snapshot_digest_cache = self.snapshot()["snapshot_digest"]
        return self._snapshot_digest_cache

    @contextmanager
    def operation(self):
        """Reserve this mutable learner for one thread; actors use frozen copies."""
        if not self._operation_lock.acquire(blocking=False):
            raise GameLearningError("policy learner is owned by another active operation")
        try:
            yield self
        finally:
            self._operation_lock.release()

    def _observation(self, value: Any) -> dict[str, float]:
        if not isinstance(value, Mapping) or set(value) != set(self._features):
            raise GameLearningError("observation features differ from environment")
        return {key: _number(value[key], f"observation {key}") for key in self._features}

    def _state(self, observation: Mapping[str, float]) -> tuple[int, ...]:
        return tuple(
            bisect.bisect_right(self.descriptor["observation_bins"][key], observation[key])
            for key in self._features
        )

    def _row(self, state: tuple[int, ...]) -> list[float]:
        if state not in self._q:
            if len(self._q) >= self.config.max_states:
                raise GameLearningError("cumulative policy state budget exhausted")
            self._q[state] = [0.0] * len(self._actions)
            self._visits[state] = [0] * len(self._actions)
        return self._q[state]

    @_exclusive
    def predict(self, observation: Mapping[str, float]) -> dict[str, Any]:
        state = self._state(self._observation(observation))
        values = self._q.get(state, [0.0] * len(self._actions))
        visits = self._visits.get(state, [0] * len(self._actions))
        scores = self._scores(state)
        index = max(range(len(scores)), key=scores.__getitem__)
        positive, negative = self._imitation.get(state, ([0] * len(self._actions), [0] * len(self._actions)))
        return {
            "action": self._actions[index],
            "state": list(state),
            "q_values": dict(zip(self._actions, values, strict=True)),
            "visits": dict(zip(self._actions, visits, strict=True)),
            "policy_digest": self.snapshot_digest,
            "action_scores": dict(zip(self._actions, scores, strict=True)),
            "imitation_counts": {
                action: {"positive": positive[i], "negative": negative[i]}
                for i, action in enumerate(self._actions)
            },
            "imitation_strength": self.config.imitation_strength,
        }

    def _scores(self, state: tuple[int, ...]) -> list[float]:
        values = self._q.get(state, [0.0] * len(self._actions))
        positive, negative = self._imitation.get(state, ([0] * len(self._actions), [0] * len(self._actions)))
        total = sum(positive) + sum(negative)
        if not total:
            return list(values)
        return [
            value + self.config.imitation_strength * (positive[i] - negative[i]) / total
            for i, value in enumerate(values)
        ]

    def _greedy(self, observation: Mapping[str, float]) -> str:
        state = self._state(observation)
        values = self._scores(state)
        return self._actions[max(range(len(values)), key=values.__getitem__)]

    def _action(self, observation: Mapping[str, float]) -> str:
        self._snapshot_digest_cache = None
        epsilon = max(
            self.config.min_epsilon,
            self.config.epsilon * self.config.epsilon_decay ** len(self._episodes),
        )
        if self._rng.random() < epsilon:
            return self._actions[self._rng.randrange(len(self._actions))]
        return self._greedy(observation)

    def _update(self, transition: Mapping[str, Any]) -> None:
        if self._updates >= self.config.max_updates:
            raise GameLearningError("cumulative policy update budget exhausted")
        if self._updates + self._inherited_updates >= MAX_LIFETIME_UPDATES:
            raise GameLearningError("lifetime policy update budget exhausted")
        state = self._state(transition["observation"])
        row = self._row(state)
        index = self._actions.index(transition["action"])
        raw_reward = transition["reward"]
        reward = min(self.config.reward_clip, max(-self.config.reward_clip, raw_reward))
        continuation = 0.0
        if not transition["terminated"]:
            continuation = self.config.gamma * max(self._row(self._state(transition["next_observation"])))
        value = row[index] + self.config.alpha * (reward + continuation - row[index])
        if not math.isfinite(value) or abs(value) > 1e15:
            raise GameLearningError("Q update exceeded finite numerical bounds")
        row[index] = value
        self._visits[state][index] += 1
        self._updates += 1
        self._snapshot_digest_cache = None

    @staticmethod
    def _guard(cancel: Callable[[], bool] | None, authorize: Callable[[], None] | None) -> None:
        if cancel is not None and cancel():
            raise GameLearningCancelled("game learning was cancelled")
        if authorize is not None:
            authorize()

    def _capture(self) -> dict[str, Any]:
        return {
            "q": copy.deepcopy(self._q),
            "visits": copy.deepcopy(self._visits),
            "rng": self._rng.getstate(),
            "episodes": copy.deepcopy(self._episodes),
            "updates": self._updates,
            "previous": self._previous_snapshot_digest,
            "inherited_episodes": copy.deepcopy(self._inherited_episodes),
            "inherited_updates": self._inherited_updates,
            "inherited_q_bound": self._inherited_q_bound,
            "parent_snapshot_digest": self._parent_snapshot_digest,
            "parent_policy_id": self._parent_policy_id,
            "imitation": copy.deepcopy(self._imitation),
            "imitation_total": self._imitation_total,
            "imitation_receipts": copy.deepcopy(self._imitation_receipts),
        }

    def _adopt(self, state: Mapping[str, Any]) -> None:
        self._q = state["q"]
        self._visits = state["visits"]
        self._rng.setstate(state["rng"])
        self._episodes = state["episodes"]
        self._updates = state["updates"]
        self._previous_snapshot_digest = state["previous"]
        self._inherited_episodes = state["inherited_episodes"]
        self._inherited_updates = state["inherited_updates"]
        self._inherited_q_bound = state["inherited_q_bound"]
        self._parent_snapshot_digest = state["parent_snapshot_digest"]
        self._parent_policy_id = state["parent_policy_id"]
        self._imitation = state["imitation"]
        self._imitation_total = state["imitation_total"]
        self._imitation_receipts = state["imitation_receipts"]
        self._snapshot_digest_cache = None

    @_exclusive
    def snapshot(self) -> dict[str, Any]:
        payload = {
            "schema_version": POLICY_SCHEMA,
            "algorithm": ALGORITHM,
            "policy_id": self.policy_id,
            "environment": self.descriptor,
            "configuration": self.config.as_dict(),
            "source_lineage": self.source_lineage,
            "runtime": self._runtime,
            "episodes": self._episodes,
            "committed_episodes": len(self._episodes),
            "committed_updates": self._updates,
            "inherited_episodes": self._inherited_episodes,
            "inherited_updates": self._inherited_updates,
            "inherited_q_bound": self._inherited_q_bound,
            "parent_snapshot_digest": self._parent_snapshot_digest,
            "parent_policy_id": self._parent_policy_id,
            "training_seeds": sorted({item["seed"] for item in self._inherited_episodes + self._episodes}),
            "previous_snapshot_digest": self._previous_snapshot_digest,
            "random_state": self._rng.getstate(),
            "q_table": [
                {"state": list(state), "values": self._q[state], "visits": self._visits[state]}
                for state in sorted(self._q)
            ],
            "imitation_observations": self._imitation_total,
            "imitation_receipts": self._imitation_receipts,
            "imitation_table": [
                {
                    "state": list(state),
                    "positive": self._imitation[state][0],
                    "negative": self._imitation[state][1],
                }
                for state in sorted(self._imitation)
            ],
        }
        copied = _copy_json(payload)
        copied["snapshot_digest"] = _digest(copied)
        _json(copied)
        return copied

    @classmethod
    def fork(
        cls,
        parent_snapshot: Mapping[str, Any],
        *,
        newpolicy_id: str,
        newsource_lineage: Mapping[str, Any],
        config: GameLearningConfig,
        expected_spec: GameEnvironmentSpec | None = None,
    ) -> GamePolicyLearner:
        """Warm-start a new bounded candidate without resetting learned values.

        The caller admits the exact parent through its existing tenant/source
        authority. Parent data and held-out leakage history remain immutable;
        only the new candidate's update budget, exploration RNG and cursor reset.
        """
        parent = cls.from_snapshot(parent_snapshot, expected_spec=expected_spec)
        if not isinstance(config, GameLearningConfig):
            raise GameLearningError("typed fork learning configuration required")
        if parent._updates == 0:
            raise GameLearningError("fork requires a parent with committed learning updates")
        if newpolicy_id == parent.policy_id or any(
            item["policy_id"] == newpolicy_id for item in parent._inherited_episodes
        ):
            raise GameLearningError("fork requires a distinct candidate policy identity")
        if max(len(parent._q), len(parent._imitation)) > config.max_states:
            raise GameLearningError("parent table exceeds new candidate state budget")
        history = copy.deepcopy(parent._inherited_episodes + parent._episodes)
        inherited_updates = parent._inherited_updates + parent._updates
        if len(history) >= MAX_LIFETIME_EPISODES or inherited_updates >= MAX_LIFETIME_UPDATES:
            raise GameLearningError("parent policy lifetime learning budget exhausted")
        candidate = cls(parent.spec, config, policy_id=newpolicy_id, source_lineage=newsource_lineage)
        candidate._q = copy.deepcopy(parent._q)
        candidate._visits = copy.deepcopy(parent._visits)
        candidate._imitation = copy.deepcopy(parent._imitation)
        candidate._imitation_total = parent._imitation_total
        candidate._imitation_receipts = copy.deepcopy(parent._imitation_receipts)
        candidate._inherited_episodes = history
        candidate._inherited_updates = inherited_updates
        candidate._inherited_q_bound = max(
            (abs(value) for row in parent._q.values() for value in row), default=0.0
        )
        candidate._parent_snapshot_digest = parent.snapshot_digest
        candidate._parent_policy_id = parent.policy_id
        candidate.snapshot()
        return candidate

    @classmethod
    def from_snapshot(
        cls,
        snapshot: Mapping[str, Any],
        *,
        expected_spec: GameEnvironmentSpec | None = None,
        expected_config: GameLearningConfig | None = None,
        expected_source_lineage: Mapping[str, Any] | None = None,
    ) -> GamePolicyLearner:
        if not isinstance(snapshot, Mapping):
            raise GameLearningError("policy snapshot must be an object")
        raw = _copy_json(dict(snapshot))
        fields = {
            "schema_version",
            "algorithm",
            "policy_id",
            "environment",
            "configuration",
            "source_lineage",
            "runtime",
            "episodes",
            "committed_episodes",
            "committed_updates",
            "inherited_episodes",
            "inherited_updates",
            "inherited_q_bound",
            "parent_snapshot_digest",
            "parent_policy_id",
            "training_seeds",
            "previous_snapshot_digest",
            "random_state",
            "q_table",
            "snapshot_digest",
            "imitation_observations",
            "imitation_receipts",
            "imitation_table",
        }
        if set(raw) != fields or raw["schema_version"] != POLICY_SCHEMA or raw["algorithm"] != ALGORITHM:
            raise GameLearningError("unsupported policy snapshot schema")
        claimed = _sha(raw.pop("snapshot_digest"), "policy snapshot")
        if _digest(raw) != claimed:
            raise GameLearningError("policy snapshot digest differs")
        descriptor = _descriptor(raw["environment"])
        if expected_spec is not None and descriptor != _descriptor(expected_spec):
            raise GameLearningError("policy environment identity differs")
        if not isinstance(raw["configuration"], dict) or set(raw["configuration"]) != set(
            asdict(GameLearningConfig())
        ):
            raise GameLearningError("policy configuration fields differ")
        try:
            config = GameLearningConfig(**raw["configuration"])
        except TypeError as exc:
            raise GameLearningError("invalid policy configuration") from exc
        if expected_config is not None and config != expected_config:
            raise GameLearningError("policy configuration identity differs")
        if expected_source_lineage is not None and raw["source_lineage"] != _copy_json(
            dict(expected_source_lineage), limit=65536
        ):
            raise GameLearningError("policy source lineage differs")
        if raw["runtime"] != _runtime():
            raise GameLearningError("policy learning runtime identity differs")
        spec = expected_spec or GameEnvironmentSpec(
            environment_id=descriptor["environment_id"],
            environment_digest=descriptor["environment_digest"],
            actions=tuple(descriptor["actions"]),
            observation_bins={key: tuple(value) for key, value in descriptor["observation_bins"].items()},
            reward_components=tuple(descriptor["reward_components"]),
            max_episode_steps=descriptor["max_episode_steps"],
        )
        learner = cls(spec, config, policy_id=raw["policy_id"], source_lineage=raw["source_lineage"])
        updates = _int(raw["committed_updates"], "committed updates", 0, config.max_updates)
        count = _int(raw["committed_episodes"], "committed episodes", 0, config.max_episodes)
        episodes = raw["episodes"]
        if not isinstance(episodes, list) or len(episodes) != count:
            raise GameLearningError("policy episode cursor differs")
        inherited_updates = _int(
            raw["inherited_updates"], "inherited updates", 0, MAX_LIFETIME_UPDATES - updates
        )
        inherited = raw["inherited_episodes"]
        if not isinstance(inherited, list) or len(inherited) + count > MAX_LIFETIME_EPISODES:
            raise GameLearningError("inherited policy episode budget differs")
        inherited_q_bound = _number(raw["inherited_q_bound"], "inherited Q bound", 1e15)
        if inherited_q_bound < 0:
            raise GameLearningError("inherited Q bound cannot be negative")
        parent_digest = raw["parent_snapshot_digest"]
        parent_id = raw["parent_policy_id"]
        if parent_digest is None:
            if parent_id is not None or inherited or inherited_updates or inherited_q_bound:
                raise GameLearningError("initial policy cannot claim inherited learned state")
        else:
            _sha(parent_digest, "parent policy snapshot")
            _name(parent_id, "parent policy identity")
            if parent_id == learner.policy_id:
                raise GameLearningError("candidate and parent policy identities collide")
        if inherited_updates == 0 and inherited_q_bound != 0:
            raise GameLearningError("untrained parent cannot claim learned Q magnitude")
        ids: set[str] = set()
        digests: set[str] = set()
        total_steps = 0
        inherited_steps = 0
        policy_ordinals: dict[str, int] = {}
        for index, episode in enumerate(inherited + episodes):
            if not isinstance(episode, dict) or set(episode) != {
                "episode_id",
                "trace_digest",
                "seed",
                "steps",
                "return",
                "source",
                "ordinal",
                "policy_id",
            }:
                raise GameLearningError("invalid policy episode ledger")
            identity = _name(episode["episode_id"], "episode identity")
            trace_digest = _sha(episode["trace_digest"], "episode trace")
            if identity in ids or trace_digest in digests:
                raise GameLearningError("duplicate committed episode identity")
            ids.add(identity)
            digests.add(trace_digest)
            episode_policy_id = _name(episode["policy_id"], "episode policy identity")
            expected_ordinal = policy_ordinals.get(episode_policy_id, 0)
            _int(episode["ordinal"], "episode ordinal", expected_ordinal, expected_ordinal)
            policy_ordinals[episode_policy_id] = expected_ordinal + 1
            if (index < len(inherited)) == (episode_policy_id == learner.policy_id):
                raise GameLearningError("episode parent/current policy scope differs")
            _int(episode["seed"], "episode seed", 0, 2**63 - 1)
            steps = _int(episode["steps"], "episode steps", 1, descriptor["max_episode_steps"])
            if index < len(inherited):
                inherited_steps += steps
            else:
                total_steps += steps
            _number(episode["return"], "episode return", 1e15)
            if episode["source"] not in (
                "local_environment",
                "offline_import",
                "local_actor_rollout",
                "human_demonstration",
            ):
                raise GameLearningError("invalid episode evidence source")
        if (
            total_steps != updates
            or inherited_steps != inherited_updates
            or raw["training_seeds"] != sorted({item["seed"] for item in inherited + episodes})
        ):
            raise GameLearningError("policy cumulative episode usage differs")
        previous = raw["previous_snapshot_digest"]
        if previous is not None:
            _sha(previous, "previous snapshot")
        if (count == 0) != (previous is None):
            raise GameLearningError("policy checkpoint lineage differs")
        table = raw["q_table"]
        if not isinstance(table, list) or len(table) > config.max_states:
            raise GameLearningError("policy state budget differs")
        if count == 0 and inherited_updates == 0 and table:
            raise GameLearningError("untrained policy cannot contain learned table rows")
        visits_total = 0
        prior_state: tuple[int, ...] | None = None
        for row in table:
            if not isinstance(row, dict) or set(row) != {"state", "values", "visits"}:
                raise GameLearningError("invalid policy table row")
            if not isinstance(row["state"], list) or len(row["state"]) != len(learner._features):
                raise GameLearningError("policy state dimensions differ")
            state = tuple(
                _int(value, "state bin", 0, len(descriptor["observation_bins"][key]))
                for key, value in zip(learner._features, row["state"], strict=True)
            )
            if prior_state is not None and state <= prior_state:
                raise GameLearningError("policy table order or uniqueness differs")
            prior_state = state
            if (
                not isinstance(row["values"], list)
                or not isinstance(row["visits"], list)
                or len(row["values"]) != len(learner._actions)
                or len(row["visits"]) != len(learner._actions)
            ):
                raise GameLearningError("policy action dimensions differ")
            learner._q[state] = [_number(value, "Q value", 1e15) for value in row["values"]]
            learner._visits[state] = [
                _int(value, "action visits", 0, inherited_updates + updates) for value in row["visits"]
            ]
            for value, visits in zip(learner._q[state], learner._visits[state], strict=True):
                if visits == 0 and value != 0.0:
                    raise GameLearningError("unvisited policy action has a learned Q value")
                numerical_bound = inherited_q_bound + config.reward_clip * updates
                if abs(value) > numerical_bound and not math.isclose(
                    abs(value),
                    numerical_bound,
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                ):
                    raise GameLearningError("policy Q value exceeds cumulative reward bound")
            visits_total += sum(learner._visits[state])
        if visits_total != inherited_updates + updates:
            raise GameLearningError("policy visit counters differ from committed updates")
        imitation_total = _int(
            raw["imitation_observations"], "imitation observations", 0, MAX_LIFETIME_UPDATES
        )
        imitation_table = raw["imitation_table"]
        if not isinstance(imitation_table, list) or len(imitation_table) > config.max_states:
            raise GameLearningError("imitation state budget differs")
        prior_state = None
        observed_total = 0
        for row in imitation_table:
            if (
                not isinstance(row, dict)
                or set(row) != {"state", "positive", "negative"}
                or not isinstance(row["state"], list)
                or len(row["state"]) != len(learner._features)
            ):
                raise GameLearningError("imitation table schema differs")
            state = tuple(
                _int(value, "imitation state bin", 0, len(descriptor["observation_bins"][key]))
                for key, value in zip(learner._features, row["state"], strict=True)
            )
            if prior_state is not None and state <= prior_state:
                raise GameLearningError("imitation state order differs")
            prior_state = state
            vectors = []
            for label in ("positive", "negative"):
                if not isinstance(row[label], list) or len(row[label]) != len(learner._actions):
                    raise GameLearningError("imitation action dimensions differ")
                vector = [
                    _int(value, "imitation action count", 0, MAX_LIFETIME_UPDATES) for value in row[label]
                ]
                observed_total += sum(vector)
                vectors.append(vector)
            if not sum(vectors[0]) + sum(vectors[1]):
                raise GameLearningError("empty imitation row is invalid")
            learner._imitation[state] = (vectors[0], vectors[1])
        receipts = raw["imitation_receipts"]
        if not isinstance(receipts, list) or len(receipts) > 1024:
            raise GameLearningError("imitation receipt budget differs")
        receipt_ids = set()
        receipt_total = 0
        for receipt in receipts:
            if not isinstance(receipt, dict) or set(receipt) != {"digest", "source", "observations"}:
                raise GameLearningError("imitation receipt schema differs")
            identity = _sha(receipt["digest"], "imitation receipt")
            if identity in receipt_ids or receipt["source"] not in (
                "human_demonstration",
                "authored_feedback",
            ):
                raise GameLearningError("imitation receipt source or identity differs")
            receipt_ids.add(identity)
            receipt_total += _int(
                receipt["observations"], "imitation receipt observations", 1, MAX_LIFETIME_UPDATES
            )
        if observed_total != imitation_total or receipt_total != imitation_total:
            raise GameLearningError("imitation counters differ from recorded authored observations")
        learner._imitation_total = imitation_total
        learner._imitation_receipts = receipts
        rng = raw["random_state"]
        if (
            not isinstance(rng, list)
            or len(rng) != 3
            or type(rng[0]) is not int
            or rng[0] != 3
            or not isinstance(rng[1], list)
            or len(rng[1]) != 625
            or rng[2] is not None
        ):
            raise GameLearningError("invalid policy exploration state")
        for index, value in enumerate(rng[1]):
            _int(value, "exploration random word", 0, 624 if index == 624 else 2**32 - 1)
        try:
            learner._rng.setstate((3, tuple(rng[1]), None))
        except (TypeError, ValueError) as exc:
            raise GameLearningError("invalid policy exploration state") from exc
        if count == 0 and learner._rng.getstate() != random.Random(config.seed).getstate():
            raise GameLearningError("untrained policy exploration identity differs")
        learner._episodes = episodes
        learner._updates = updates
        learner._inherited_episodes = inherited
        learner._inherited_updates = inherited_updates
        learner._inherited_q_bound = inherited_q_bound
        learner._parent_snapshot_digest = parent_digest
        learner._parent_policy_id = parent_id
        learner._previous_snapshot_digest = previous
        if learner.snapshot_digest != claimed:
            raise GameLearningError("policy snapshot canonical identity differs")
        return learner

    def _transition(self, value: Mapping[str, Any], sequence: int) -> dict[str, Any]:
        fields = {
            "sequence",
            "observation",
            "action",
            "next_observation",
            "reward",
            "reward_components",
            "terminated",
            "truncated",
        }
        if (
            not isinstance(value, Mapping)
            or not fields <= set(value)
            or set(value) - fields - {"info", "transition_digest"}
        ):
            raise GameLearningError("transition fields differ")
        _int(value["sequence"], "transition sequence", sequence, sequence)
        action = value["action"]
        if not isinstance(action, str) or action not in self._actions:
            raise GameLearningError("transition action is undeclared")
        for key in ("terminated", "truncated"):
            if type(value[key]) is not bool:
                raise GameLearningError("transition termination flags must be boolean")
        if value["terminated"] and value["truncated"]:
            raise GameLearningError("transition cannot both terminate and truncate")
        components = value["reward_components"]
        if not isinstance(components, Mapping) or set(components) != set(
            self.descriptor["reward_components"]
        ):
            raise GameLearningError("transition reward components differ")
        normalized = {
            key: _number(components[key], f"reward {key}", 1e9)
            for key in self.descriptor["reward_components"]
        }
        reward = _number(value["reward"], "transition reward", 1e12)
        if reward != math.fsum(normalized.values()):
            raise GameLearningError("transition reward does not equal component sum")
        result = {
            "sequence": sequence,
            "observation": self._observation(value["observation"]),
            "action": action,
            "next_observation": self._observation(value["next_observation"]),
            "reward": reward,
            "reward_components": normalized,
            "terminated": value["terminated"],
            "truncated": value["truncated"],
        }
        if "info" in value:
            if not isinstance(value["info"], Mapping):
                raise GameLearningError("transition info must be an object")
            result["info"] = _copy_json(dict(value["info"]), limit=4096)
        if value.get("transition_digest"):
            result["transition_digest"] = _sha(value["transition_digest"], "engine transition")
        return result

    def validate_trace(self, trace: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(trace, Mapping):
            raise GameLearningError("episode trace must be an object")
        raw = _copy_json(dict(trace), limit=self.config.trace_byte_limit)
        if (
            set(raw)
            != {
                "schema_version",
                "environment",
                "episode_id",
                "seed",
                "source_lineage",
                "transitions",
                "return",
                "steps",
                "trace_digest",
            }
            or raw["schema_version"] != TRACE_SCHEMA
        ):
            raise GameLearningError("unsupported offline trace schema")
        claimed = _sha(raw.pop("trace_digest"), "trace")
        if _digest(raw) != claimed:
            raise GameLearningError("episode trace digest differs")
        if _descriptor(raw["environment"]) != self.descriptor:
            raise GameLearningError("episode environment identity differs")
        if raw["source_lineage"] != self.source_lineage:
            admitted = self.source_lineage.get("admitted_traces", {})
            if claimed not in admitted or admitted[claimed] != raw["source_lineage"]:
                raise GameLearningError("episode source lineage differs from admitted trace binding")
        _name(raw["episode_id"], "episode identity")
        _int(raw["seed"], "episode seed", 0, 2**63 - 1)
        steps = _int(raw["steps"], "episode steps", 1, self.descriptor["max_episode_steps"])
        if not isinstance(raw["transitions"], list) or len(raw["transitions"]) != steps:
            raise GameLearningError("episode transition count differs")
        normalized = []
        previous = None
        for index, value in enumerate(raw["transitions"], 1):
            transition = self._transition(value, index)
            if previous is not None and transition["observation"] != previous["next_observation"]:
                raise GameLearningError("episode observation chain is discontinuous")
            if index < steps and (transition["terminated"] or transition["truncated"]):
                raise GameLearningError("episode continues after termination")
            normalized.append(transition)
            previous = transition
        if not (normalized[-1]["terminated"] or normalized[-1]["truncated"]):
            raise GameLearningError("episode must end with termination or truncation")
        if _number(raw["return"], "episode return", 1e15) != math.fsum(item["reward"] for item in normalized):
            raise GameLearningError("episode return differs from declared reward components")
        raw["trace_digest"] = claimed
        return raw

    def _seed(self, ordinal: int) -> int:
        return int.from_bytes(
            hashlib.sha256(f"{self.config.seed}:{ordinal}".encode()).digest()[:8], "big"
        ) % (2**63)

    def _run_episode(
        self,
        factory: Callable[[], Any],
        *,
        seed: int,
        episode_id: str,
        select: Callable[[Mapping[str, float]], str],
        update: bool,
        cancel: Callable[[], bool] | None,
        authorize: Callable[[], None] | None,
        step_budget: int | None = None,
    ) -> dict[str, Any]:
        self._guard(cancel, authorize)
        environment = factory()
        try:
            return self._run_open_episode(
                environment,
                seed=seed,
                episode_id=episode_id,
                select=select,
                update=update,
                cancel=cancel,
                authorize=authorize,
                step_budget=step_budget,
            )
        finally:
            close = getattr(environment, "close", None)
            if callable(close):
                close()

    def _run_open_episode(
        self,
        environment: Any,
        *,
        seed: int,
        episode_id: str,
        select: Callable[[Mapping[str, float]], str],
        update: bool,
        cancel: Callable[[], bool] | None,
        authorize: Callable[[], None] | None,
        step_budget: int | None = None,
    ) -> dict[str, Any]:
        if _descriptor(environment.spec) != self.descriptor:
            raise GameLearningError("factory returned a foreign environment")
        observation = self._observation(environment.reset(seed))
        transitions: list[dict[str, Any]] = []
        byte_count = 0
        for sequence in range(1, self.descriptor["max_episode_steps"] + 1):
            self._guard(cancel, authorize)
            if step_budget is not None and sequence > step_budget:
                raise GameLearningError("evaluation cumulative step budget exhausted")
            if update and self._updates >= self.config.max_updates:
                raise GameLearningError("cumulative policy update budget exhausted")
            if update and self._updates + self._inherited_updates >= MAX_LIFETIME_UPDATES:
                raise GameLearningError("lifetime policy update budget exhausted")
            action = select(observation)
            step: EpisodeStep = environment.step(action)
            self._guard(cancel, authorize)
            if type(step.terminated) is not bool or type(step.truncated) is not bool:
                raise GameLearningError("environment returned untyped termination flags")
            components = step.reward_components
            if not isinstance(components, Mapping):
                raise GameLearningError("environment returned invalid rewards")
            values = {key: _number(value, "environment reward", 1e9) for key, value in components.items()}
            data: dict[str, Any] = {
                "sequence": sequence,
                "observation": observation,
                "action": action,
                "next_observation": step.observation,
                "reward": math.fsum(values.values()),
                "reward_components": values,
                "terminated": step.terminated,
                "truncated": step.truncated
                or (sequence == self.descriptor["max_episode_steps"] and not step.terminated),
            }
            info = getattr(step, "info", None)
            if info:
                data["info"] = info
            transition_digest = getattr(step, "transition_digest", None)
            if transition_digest:
                data["transition_digest"] = transition_digest
            transition = self._transition(data, sequence)
            byte_count += len(_json(transition))
            if byte_count > self.config.trace_byte_limit:
                raise GameLearningError("episode trace byte budget exhausted")
            if update:
                self._update(transition)
            transitions.append(transition)
            observation = transition["next_observation"]
            if transition["terminated"] or transition["truncated"]:
                break
        trace = {
            "schema_version": TRACE_SCHEMA,
            "environment": self.descriptor,
            "episode_id": episode_id,
            "seed": seed,
            "source_lineage": self.source_lineage,
            "transitions": transitions,
            "return": math.fsum(item["reward"] for item in transitions),
            "steps": len(transitions),
        }
        trace["trace_digest"] = _digest(trace)
        _json(trace, limit=self.config.trace_byte_limit)
        return trace

    def _commit_episode(
        self,
        trace: Mapping[str, Any],
        *,
        source: str,
        prior_digest: str,
        on_checkpoint: Callable[[dict[str, Any], dict[str, Any]], None] | None,
        cancel: Callable[[], bool] | None,
        authorize: Callable[[], None] | None,
    ) -> dict[str, Any]:
        if len(self._episodes) >= self.config.max_episodes:
            raise GameLearningError("cumulative policy episode budget exhausted")
        if len(self._inherited_episodes) + len(self._episodes) >= MAX_LIFETIME_EPISODES:
            raise GameLearningError("lifetime policy episode budget exhausted")
        if any(
            item["episode_id"] == trace["episode_id"] or item["trace_digest"] == trace["trace_digest"]
            for item in self._inherited_episodes + self._episodes
        ):
            raise GameLearningError("episode was already committed")
        summary = {
            "episode_id": trace["episode_id"],
            "trace_digest": trace["trace_digest"],
            "seed": trace["seed"],
            "steps": trace["steps"],
            "return": trace["return"],
            "source": source,
            "ordinal": len(self._episodes),
            "policy_id": self.policy_id,
        }
        self._episodes.append(summary)
        self._previous_snapshot_digest = prior_digest
        self._snapshot_digest_cache = None
        snapshot = self.snapshot()
        self._guard(cancel, authorize)
        if on_checkpoint is not None:
            on_checkpoint(snapshot, _copy_json(trace, limit=self.config.trace_byte_limit))
        return summary

    def _record_imitation(self, observation: Mapping[str, float], action: str, weight: int) -> None:
        _int(weight, "authored preference weight", -16, 16)
        if not weight or action not in self._actions:
            raise GameLearningError("authored action preference is invalid")
        if self._imitation_total + abs(weight) > MAX_LIFETIME_UPDATES:
            raise GameLearningError("lifetime imitation observation budget exhausted")
        state = self._state(self._observation(observation))
        if state not in self._imitation:
            if len(self._imitation) >= self.config.max_states:
                raise GameLearningError("imitation state budget exhausted")
            self._imitation[state] = ([0] * len(self._actions), [0] * len(self._actions))
        vector = self._imitation[state][0 if weight > 0 else 1]
        vector[self._actions.index(action)] += abs(weight)
        self._imitation_total += abs(weight)
        self._snapshot_digest_cache = None

    @_exclusive
    def learn_verified_episode(
        self,
        episode: Any,
        *,
        on_checkpoint: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
        cancel: Callable[[], bool] | None = None,
        authorize: Callable[[], None] | None = None,
    ) -> GameTrainingResult:
        """Apply a process-local measured receipt; serialized issuer labels confer no proof."""
        from .game_learning_demonstrations import _require_verified_episode

        verified = _require_verified_episode(episode)
        if self._busy:
            raise GameLearningError("policy learner already executing")
        self._busy = True
        prior = self._capture()
        first_updates = self._updates
        try:
            self._guard(cancel, authorize)
            trace = self.validate_trace(verified.trace)
            if any(
                item["episode_id"] == trace["episode_id"] or item["trace_digest"] == trace["trace_digest"]
                for item in self._inherited_episodes + self._episodes
            ):
                raise GameLearningError("verified episode was already committed")
            if len(self._imitation_receipts) >= 1024 and verified.source == "human_demonstration":
                raise GameLearningError("imitation receipt budget exhausted")
            prior_digest = self.snapshot_digest
            for transition in trace["transitions"]:
                self._guard(cancel, authorize)
                transition = self._transition(transition, transition["sequence"])
                if verified.source == "human_demonstration":
                    self._record_imitation(transition["observation"], transition["action"], 1)
                self._update(transition)
            if verified.source == "human_demonstration":
                if any(receipt["digest"] == verified.evidence_digest for receipt in self._imitation_receipts):
                    raise GameLearningError("human demonstration was already learned")
                self._imitation_receipts.append(
                    {
                        "digest": verified.evidence_digest,
                        "source": verified.source,
                        "observations": trace["steps"],
                    }
                )
            summary = self._commit_episode(
                trace,
                source=verified.source,
                prior_digest=prior_digest,
                on_checkpoint=on_checkpoint,
                cancel=cancel,
                authorize=authorize,
            )
            return GameTrainingResult(self.snapshot(), (summary,), (trace,), self._updates - first_updates)
        except BaseException:
            self._adopt(prior)
            raise
        finally:
            self._busy = False

    @_exclusive
    def learn_authored_feedback(
        self,
        feedback: Any,
        *,
        on_checkpoint: Callable[[dict[str, Any], None], None] | None = None,
        cancel: Callable[[], bool] | None = None,
        authorize: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        """Change authored action preferences without inventing Q rewards or visits."""
        from .game_learning_demonstrations import _require_verified_feedback

        verified = _require_verified_feedback(feedback)
        if self._busy:
            raise GameLearningError("policy learner already executing")
        if verified.environment_digest != self.descriptor["environment_digest"]:
            raise GameLearningError("feedback environment identity differs")
        if (
            verified.source_lineage != self.source_lineage
            and self.source_lineage.get("admitted_feedback", {}).get(verified.evidence_digest)
            != verified.source_lineage
        ):
            raise GameLearningError("feedback source lineage is not admitted")
        if any(receipt["digest"] == verified.evidence_digest for receipt in self._imitation_receipts):
            raise GameLearningError("authored feedback was already learned")
        if len(self._imitation_receipts) >= 1024:
            raise GameLearningError("imitation receipt budget exhausted")
        self._busy = True
        prior = self._capture()
        try:
            self._guard(cancel, authorize)
            self._record_imitation(verified.observation, verified.action, verified.weight)
            self._imitation_receipts.append(
                {
                    "digest": verified.evidence_digest,
                    "source": "authored_feedback",
                    "observations": abs(verified.weight),
                }
            )
            snapshot = self.snapshot()
            self._guard(cancel, authorize)
            if on_checkpoint is not None:
                on_checkpoint(snapshot, None)
            return snapshot
        except BaseException:
            self._adopt(prior)
            raise
        finally:
            self._busy = False

    @_exclusive
    def train(
        self,
        environment_factory: Callable[[], Any],
        *,
        episodes: int,
        seeds: Sequence[int] | None = None,
        on_checkpoint: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
        cancel: Callable[[], bool] | None = None,
        authorize: Callable[[], None] | None = None,
    ) -> GameTrainingResult:
        count = _int(episodes, "requested episodes", 1, self.config.max_episodes)
        if len(self._episodes) + count > self.config.max_episodes:
            raise GameLearningError("cumulative policy episode budget exhausted")
        if len(self._inherited_episodes) + len(self._episodes) + count > MAX_LIFETIME_EPISODES:
            raise GameLearningError("lifetime policy episode budget exhausted")
        if seeds is not None and (not isinstance(seeds, (tuple, list)) or len(seeds) != count):
            raise GameLearningError("requested episode seed count differs")
        if self._busy:
            raise GameLearningError("policy learner already executing")
        self._busy = True
        summaries: list[dict[str, Any]] = []
        traces: list[dict[str, Any]] = []
        returned_bytes = 0
        first_updates = self._updates
        try:
            for index in range(count):
                prior = self._capture()
                try:
                    ordinal = len(self._episodes)
                    seed = (
                        self._seed(ordinal)
                        if seeds is None
                        else _int(seeds[index], "episode seed", 0, 2**63 - 1)
                    )
                    prior_digest = self.snapshot_digest
                    episode_id = "episode:" + _digest(
                        {
                            "policy_id": self.policy_id,
                            "ordinal": ordinal,
                            "seed": seed,
                            "environment_digest": self.descriptor["environment_digest"],
                        }
                    )
                    trace = self._run_episode(
                        environment_factory,
                        seed=seed,
                        episode_id=episode_id,
                        select=self._action,
                        update=True,
                        cancel=cancel,
                        authorize=authorize,
                    )
                    size = len(_json(trace))
                    if returned_bytes + size > self.config.trace_byte_limit:
                        raise GameLearningError("training result trace byte budget exhausted")
                    summary = self._commit_episode(
                        trace,
                        source="local_environment",
                        prior_digest=prior_digest,
                        on_checkpoint=on_checkpoint,
                        cancel=cancel,
                        authorize=authorize,
                    )
                except BaseException:
                    self._adopt(prior)
                    raise
                returned_bytes += size
                summaries.append(summary)
                traces.append(trace)
            return GameTrainingResult(
                self.snapshot(), tuple(summaries), tuple(traces), self._updates - first_updates
            )
        finally:
            self._busy = False

    @_exclusive
    def train_offline(
        self,
        traces: Sequence[Mapping[str, Any]],
        *,
        on_checkpoint: Callable[[dict[str, Any], dict[str, Any]], None] | None = None,
        cancel: Callable[[], bool] | None = None,
        authorize: Callable[[], None] | None = None,
    ) -> GameTrainingResult:
        if not isinstance(traces, (list, tuple)) or not 1 <= len(traces) <= self.config.max_episodes:
            raise GameLearningError("offline trace count exceeds episode budget")
        if len(self._episodes) + len(traces) > self.config.max_episodes:
            raise GameLearningError("cumulative policy episode budget exhausted")
        if len(self._inherited_episodes) + len(self._episodes) + len(traces) > MAX_LIFETIME_EPISODES:
            raise GameLearningError("lifetime policy episode budget exhausted")
        if self._busy:
            raise GameLearningError("policy learner already executing")
        self._busy = True
        summaries = []
        validated = []
        returned_bytes = 0
        first_updates = self._updates
        try:
            for source_trace in traces:
                prior = self._capture()
                try:
                    self._guard(cancel, authorize)
                    trace = self.validate_trace(source_trace)
                    size = len(_json(trace))
                    if returned_bytes + size > self.config.trace_byte_limit:
                        raise GameLearningError("offline result trace byte budget exhausted")
                    if any(
                        item["episode_id"] == trace["episode_id"]
                        or item["trace_digest"] == trace["trace_digest"]
                        for item in self._inherited_episodes + self._episodes
                    ):
                        raise GameLearningError("offline episode was already committed")
                    prior_digest = self.snapshot_digest
                    for transition in trace["transitions"]:
                        self._guard(cancel, authorize)
                        self._update(self._transition(transition, transition["sequence"]))
                    summary = self._commit_episode(
                        trace,
                        source="offline_import",
                        prior_digest=prior_digest,
                        on_checkpoint=on_checkpoint,
                        cancel=cancel,
                        authorize=authorize,
                    )
                except BaseException:
                    self._adopt(prior)
                    raise
                returned_bytes += size
                summaries.append(summary)
                validated.append(trace)
            return GameTrainingResult(
                self.snapshot(), tuple(summaries), tuple(validated), self._updates - first_updates
            )
        finally:
            self._busy = False

    @_exclusive
    def evaluate(
        self,
        environment_factory: Callable[[], Any],
        *,
        heldout_seeds: Sequence[int],
        baseline_snapshot: Mapping[str, Any] | None = None,
        cancel: Callable[[], bool] | None = None,
        authorize: Callable[[], None] | None = None,
    ) -> GameEvaluationResult:
        if not isinstance(heldout_seeds, (list, tuple)) or not 1 <= len(heldout_seeds) <= 64:
            raise GameLearningError("held-out evaluation episode budget exceeded")
        seeds = [_int(seed, "held-out seed", 0, 2**63 - 1) for seed in heldout_seeds]
        training_seeds = {item["seed"] for item in self._inherited_episodes + self._episodes}
        if len(set(seeds)) != len(seeds) or training_seeds.intersection(seeds):
            raise GameLearningError("evaluation seeds must be unique and disjoint from training")
        if self._busy:
            raise GameLearningError("policy learner already executing")
        baseline = None
        if baseline_snapshot is not None:
            baseline = type(self).from_snapshot(baseline_snapshot, expected_spec=self.spec)
            if {item["seed"] for item in baseline._inherited_episodes + baseline._episodes}.intersection(
                seeds
            ):
                raise GameLearningError("baseline evaluation seeds overlap training")
        before = self.snapshot_digest
        self._busy = True
        records = []
        measured_steps = 0
        try:
            for seed in seeds:
                rng = random.Random(
                    int.from_bytes(hashlib.sha256(f"baseline:{seed}".encode()).digest(), "big")
                )
                select_baseline = (
                    baseline._greedy
                    if baseline is not None
                    else lambda _observation, episode_rng=rng: self._actions[
                        episode_rng.randrange(len(self._actions))
                    ]
                )
                candidate_trace = self._run_episode(
                    environment_factory,
                    seed=seed,
                    episode_id=f"evaluation:candidate:{seed}",
                    select=self._greedy,
                    update=False,
                    cancel=cancel,
                    authorize=authorize,
                    step_budget=65536 - measured_steps,
                )
                measured_steps += candidate_trace["steps"]
                baseline_trace = self._run_episode(
                    environment_factory,
                    seed=seed,
                    episode_id=f"evaluation:baseline:{seed}",
                    select=select_baseline,
                    update=False,
                    cancel=cancel,
                    authorize=authorize,
                    step_budget=65536 - measured_steps,
                )
                measured_steps += baseline_trace["steps"]
                record: dict[str, Any] = {"seed": seed}
                for label, trace in (("candidate", candidate_trace), ("baseline", baseline_trace)):
                    last = trace["transitions"][-1]
                    record[label] = {
                        "return": trace["return"],
                        "steps": trace["steps"],
                        "terminated": last["terminated"],
                        "truncated": last["truncated"],
                        "trace_digest": trace["trace_digest"],
                        "reward_components": {
                            key: math.fsum(step["reward_components"][key] for step in trace["transitions"])
                            for key in self.descriptor["reward_components"]
                        },
                    }
                record["return_difference"] = candidate_trace["return"] - baseline_trace["return"]
                records.append(record)
            self._guard(cancel, authorize)
            if self.snapshot_digest != before:
                raise GameLearningError("evaluation changed the training policy")
            evidence = {
                "schema_version": "skeleton.game.policy_evaluation.v1",
                "policy_id": self.policy_id,
                "policy_digest": before,
                "environment": self.descriptor,
                "source_lineage": self.source_lineage,
                "baseline": {
                    "kind": "parent_policy" if baseline is not None else "seeded_uniform_random",
                    "policy_digest": baseline.snapshot_digest if baseline else None,
                },
                "heldout_seeds": seeds,
                "episodes": records,
                "measured_steps": measured_steps,
                "candidate_mean_return": math.fsum(item["candidate"]["return"] for item in records)
                / len(records),
                "baseline_mean_return": math.fsum(item["baseline"]["return"] for item in records)
                / len(records),
                "mean_return_difference": math.fsum(item["return_difference"] for item in records)
                / len(records),
                "candidate_termination_rate": sum(item["candidate"]["terminated"] for item in records)
                / len(records),
                "baseline_termination_rate": sum(item["baseline"]["terminated"] for item in records)
                / len(records),
                "candidate_mean_steps": math.fsum(item["candidate"]["steps"] for item in records)
                / len(records),
                "baseline_mean_steps": math.fsum(item["baseline"]["steps"] for item in records)
                / len(records),
                "production_promotion_authorized": False,
            }
            evidence["evaluation_digest"] = _digest(evidence)
            return GameEvaluationResult(evidence)
        finally:
            self._busy = False
