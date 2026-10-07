"""Immutable contracts for the Mirror Room learning sandbox.

Mirror Room is an implementation of the existing feedback-learning plane.  It
is deliberately non-authoritative: candidates can be generated, exercised,
compared, and iterated inside the room, but no object in this module grants
production mutation authority.

The contracts are intentionally provider-neutral.  A caller may back the
sandbox with a local model, a simulator, a policy variant, a prompt program, or
another deterministic adapter without moving provider credentials into the
learning plane.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Mapping

from skeleton.eval.experiment_registry import (
    ExperimentManifest,
    MetricDirection,
    TrafficMode,
)


_MAX_TEXT = 4096
_MAX_ITEMS = 4096
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DATA_CLASSES = frozenset({"public", "internal", "confidential", "restricted"})


class MirrorRoomError(RuntimeError):
    """A Mirror Room contract, isolation, or evidence invariant was violated."""


class _FrozenDict(dict):
    """JSON-compatible mapping that rejects mutation after construction."""

    @staticmethod
    def _immutable(*args: object, **kwargs: object) -> None:
        raise TypeError("Mirror Room evidence mappings are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return _FrozenDict({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


class ScenarioSplit(str, Enum):
    """Visibility boundary for learning scenarios."""

    TRAIN = "train"
    VALIDATION = "validation"
    HOLDOUT = "holdout"


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value):
        raise MirrorRoomError(f"{name} must be a canonical token")
    return value


def _text(name: str, value: object, *, maximum: int = _MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MirrorRoomError(f"{name} must be non-empty text")
    result = value.strip()
    if result != value or len(result) > maximum:
        raise MirrorRoomError(f"{name} must be normalized and bounded")
    return result


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MirrorRoomError(f"{name} must be a positive integer")
    return value


def _non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MirrorRoomError(f"{name} must be a non-negative integer")
    return value


def _finite(name: str, value: object, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MirrorRoomError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise MirrorRoomError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise MirrorRoomError(f"{name} must be >= {minimum}")
    return result


def _unit(name: str, value: object) -> float:
    result = _finite(name, value)
    if not 0.0 <= result <= 1.0:
        raise MirrorRoomError(f"{name} must be within [0, 1]")
    return result


def _sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise MirrorRoomError(f"{name} must be a lowercase sha256 digest")
    return value


def _tokens(name: str, values: object, *, allow_empty: bool = True) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, (tuple, list, set, frozenset)):
        raise MirrorRoomError(f"{name} must be a collection")
    result = tuple(sorted({_token(name, value) for value in values}))
    if not result and not allow_empty:
        raise MirrorRoomError(f"{name} must be non-empty")
    if len(result) > _MAX_ITEMS:
        raise MirrorRoomError(f"{name} exceeds item limit")
    return result


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise MirrorRoomError("Mirror Room payload must be deterministic JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _frozen_json_mapping(name: str, value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise MirrorRoomError(f"{name} must be a mapping")
    # JSON round-trip breaks caller aliases and rejects non-deterministic values.
    encoded = _canonical_json(value)
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise MirrorRoomError(f"{name} must be a JSON object")
    if len(decoded) > _MAX_ITEMS:
        raise MirrorRoomError(f"{name} exceeds item limit")
    return _freeze_json(decoded)


@dataclass(frozen=True, slots=True)
class MirrorCandidate:
    """One quarantined behavior candidate.

    ``parameters`` is intentionally generic.  It may identify model weights,
    prompt/policy configuration, routing parameters, or a simulated behavior
    program.  It is never interpreted as production authority.
    """

    candidate_id: str
    version: str
    producer_id: str
    change_ref: str
    change_digest: str
    parameters: Mapping[str, Any]
    parent_candidate_id: str | None = None
    evidence_refs: tuple[str, ...] = ()
    production_authority: bool = False
    direct_self_modify: bool = False

    def __post_init__(self) -> None:
        for field in ("candidate_id", "version", "producer_id", "change_ref"):
            object.__setattr__(self, field, _token(field, getattr(self, field)))
        object.__setattr__(self, "change_digest", _sha256("change_digest", self.change_digest))
        if self.parent_candidate_id is not None:
            object.__setattr__(
                self,
                "parent_candidate_id",
                _token("parent_candidate_id", self.parent_candidate_id),
            )
            if self.parent_candidate_id == self.candidate_id:
                raise MirrorRoomError("candidate cannot parent itself")
        object.__setattr__(
            self,
            "evidence_refs",
            _tokens("evidence_ref", self.evidence_refs),
        )
        object.__setattr__(
            self,
            "parameters",
            _frozen_json_mapping("parameters", self.parameters),
        )
        if self.production_authority is not False:
            raise MirrorRoomError("Mirror Room candidate cannot have production authority")
        if self.direct_self_modify is not False:
            raise MirrorRoomError("Mirror Room candidate cannot directly self-modify")

    def payload(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "version": self.version,
            "producer_id": self.producer_id,
            "change_ref": self.change_ref,
            "change_digest": self.change_digest,
            "parameters": self.parameters,
            "parent_candidate_id": self.parent_candidate_id,
            "evidence_refs": list(self.evidence_refs),
            "production_authority": False,
            "direct_self_modify": False,
        }

    @property
    def behavior_digest(self) -> str:
        """Stable identity of the effective behavior artifact.

        Candidate IDs, versions, evidence labels, and lineage are intentionally
        excluded. The content-addressed change artifact remains part of the
        identity so distinct weight/prompt/policy artifacts are not collapsed
        merely because they expose the same high-level parameter metadata.
        """

        return _digest(
            {
                "change_digest": self.change_digest,
                "parameters": self.parameters,
            }
        )

    @property
    def parameter_digest(self) -> str:
        """Behavior-state identity independent of candidate naming metadata."""
        return _digest(self.parameters)

    @property
    def digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True, slots=True)
class MirrorScenario:
    """A sealed scenario with explicit train/validation/holdout visibility."""

    scenario_id: str
    split: ScenarioSplit
    payload: Mapping[str, Any]
    tags: tuple[str, ...] = ()
    weight: float = 1.0
    data_class: str = "public"
    authorization_ref: str | None = None
    source_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario_id", _token("scenario_id", self.scenario_id))
        try:
            object.__setattr__(self, "split", ScenarioSplit(self.split))
        except ValueError as exc:
            raise MirrorRoomError("invalid scenario split") from exc
        object.__setattr__(self, "payload", _frozen_json_mapping("scenario payload", self.payload))
        object.__setattr__(self, "tags", _tokens("scenario tag", self.tags))
        weight = _finite("scenario weight", self.weight, minimum=0.0)
        if weight <= 0.0:
            raise MirrorRoomError("scenario weight must be positive")
        object.__setattr__(self, "weight", weight)
        data_class = _token("data_class", self.data_class).lower()
        if data_class not in _DATA_CLASSES:
            raise MirrorRoomError("unsupported Mirror Room scenario data class")
        object.__setattr__(self, "data_class", data_class)
        if self.authorization_ref is not None:
            object.__setattr__(
                self,
                "authorization_ref",
                _token("authorization_ref", self.authorization_ref),
            )
        if data_class != "public" and self.authorization_ref is None:
            raise MirrorRoomError(
                "non-public Mirror Room scenario requires learning authorization receipt"
            )
        if self.source_ref is not None:
            object.__setattr__(
                self,
                "source_ref",
                _text("source_ref", self.source_ref, maximum=1024),
            )

    @property
    def payload_digest(self) -> str:
        return _digest(self.payload)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "scenario_id": self.scenario_id,
                "split": self.split.value,
                "payload_digest": self.payload_digest,
                "tags": list(self.tags),
                "weight": self.weight,
                "data_class": self.data_class,
                "authorization_ref": self.authorization_ref,
                "source_ref": self.source_ref,
            }
        )


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    """Least-privilege execution policy carried into every episode."""

    allowed_capabilities: tuple[str, ...] = ("compute",)
    max_steps_per_episode: int = 128
    max_tokens_per_episode: int = 32_768
    max_cost_units_per_episode: float = 1.0
    deterministic_replay_required: bool = True
    network_allowed: bool = False
    filesystem_write_allowed: bool = False
    subprocess_allowed: bool = False
    external_side_effects_allowed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "allowed_capabilities",
            _tokens("allowed_capability", self.allowed_capabilities, allow_empty=False),
        )
        object.__setattr__(
            self,
            "max_steps_per_episode",
            _positive_int("max_steps_per_episode", self.max_steps_per_episode),
        )
        object.__setattr__(
            self,
            "max_tokens_per_episode",
            _positive_int("max_tokens_per_episode", self.max_tokens_per_episode),
        )
        cost = _finite(
            "max_cost_units_per_episode",
            self.max_cost_units_per_episode,
            minimum=0.0,
        )
        if cost <= 0.0:
            raise MirrorRoomError("max_cost_units_per_episode must be positive")
        object.__setattr__(self, "max_cost_units_per_episode", cost)
        for field in (
            "deterministic_replay_required",
            "network_allowed",
            "filesystem_write_allowed",
            "subprocess_allowed",
            "external_side_effects_allowed",
        ):
            if not isinstance(getattr(self, field), bool):
                raise MirrorRoomError(f"{field} must be boolean")
        if (
            self.network_allowed
            or self.filesystem_write_allowed
            or self.subprocess_allowed
            or self.external_side_effects_allowed
        ):
            raise MirrorRoomError(
                "Mirror Room default contract is hermetic; side-effect capabilities are forbidden"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "allowed_capabilities": list(self.allowed_capabilities),
                "max_steps_per_episode": self.max_steps_per_episode,
                "max_tokens_per_episode": self.max_tokens_per_episode,
                "max_cost_units_per_episode": self.max_cost_units_per_episode,
                "deterministic_replay_required": self.deterministic_replay_required,
                "network_allowed": False,
                "filesystem_write_allowed": False,
                "subprocess_allowed": False,
                "external_side_effects_allowed": False,
            }
        )


@dataclass(frozen=True, slots=True)
class MirrorBudget:
    """Whole-run resource ceiling independent of per-episode sandbox limits."""

    max_generations: int = 8
    max_candidates_per_generation: int = 8
    max_episodes: int = 2048
    max_total_steps: int = 100_000
    max_total_tokens: int = 4_000_000
    max_total_cost_units: float = 256.0
    max_validation_candidate_evaluations: int = 32

    def __post_init__(self) -> None:
        for field in (
            "max_generations",
            "max_candidates_per_generation",
            "max_episodes",
            "max_total_steps",
            "max_total_tokens",
            "max_validation_candidate_evaluations",
        ):
            object.__setattr__(self, field, _positive_int(field, getattr(self, field)))
        cost = _finite("max_total_cost_units", self.max_total_cost_units, minimum=0.0)
        if cost <= 0.0:
            raise MirrorRoomError("max_total_cost_units must be positive")
        object.__setattr__(self, "max_total_cost_units", cost)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "max_generations": self.max_generations,
                "max_candidates_per_generation": self.max_candidates_per_generation,
                "max_episodes": self.max_episodes,
                "max_total_steps": self.max_total_steps,
                "max_total_tokens": self.max_total_tokens,
                "max_total_cost_units": self.max_total_cost_units,
                "max_validation_candidate_evaluations": self.max_validation_candidate_evaluations,
            }
        )


@dataclass(frozen=True, slots=True)
class MirrorMetricPolicy:
    """Promotion-oriented interpretation of one independent experiment metric."""

    metric_id: str
    direction: MetricDirection
    minimum_improvement: float = 0.0
    max_regression: float = 0.0
    confidence_level: float = 0.95
    guardrail: bool = False
    weight: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric_id", _token("metric_id", self.metric_id))
        try:
            object.__setattr__(self, "direction", MetricDirection(self.direction))
        except ValueError as exc:
            raise MirrorRoomError("invalid metric direction") from exc
        object.__setattr__(
            self,
            "minimum_improvement",
            _finite("minimum_improvement", self.minimum_improvement, minimum=0.0),
        )
        object.__setattr__(
            self,
            "max_regression",
            _finite("max_regression", self.max_regression, minimum=0.0),
        )
        confidence = _unit("confidence_level", self.confidence_level)
        if confidence < 0.5 or confidence >= 1.0:
            raise MirrorRoomError("confidence_level must be within [0.5, 1)")
        object.__setattr__(self, "confidence_level", confidence)
        if not isinstance(self.guardrail, bool):
            raise MirrorRoomError("guardrail must be boolean")
        weight = _finite("weight", self.weight, minimum=0.0)
        if weight <= 0.0:
            raise MirrorRoomError("weight must be positive")
        object.__setattr__(self, "weight", weight)

    def payload(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "direction": self.direction.value,
            "minimum_improvement": self.minimum_improvement,
            "max_regression": self.max_regression,
            "confidence_level": self.confidence_level,
            "guardrail": self.guardrail,
            "weight": self.weight,
        }


@dataclass(frozen=True, slots=True)
class EpisodeOutcome:
    """Executor-returned observation from one hermetic episode."""

    metric_values: Mapping[str, float]
    observation_digest: str
    steps: int
    tokens: int
    cost_units: float
    capabilities_used: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.metric_values, Mapping) or not self.metric_values:
            raise MirrorRoomError("metric_values must be a non-empty mapping")
        metrics: dict[str, float] = {}
        for key, value in self.metric_values.items():
            metrics[_token("metric_id", key)] = _unit(f"metric_values[{key}]", value)
        object.__setattr__(self, "metric_values", _FrozenDict(dict(sorted(metrics.items()))))
        object.__setattr__(
            self,
            "observation_digest",
            _sha256("observation_digest", self.observation_digest),
        )
        object.__setattr__(self, "steps", _non_negative_int("steps", self.steps))
        object.__setattr__(self, "tokens", _non_negative_int("tokens", self.tokens))
        object.__setattr__(
            self,
            "cost_units",
            _finite("cost_units", self.cost_units, minimum=0.0),
        )
        object.__setattr__(
            self,
            "capabilities_used",
            _tokens("capability", self.capabilities_used),
        )
        object.__setattr__(self, "evidence_refs", _tokens("evidence_ref", self.evidence_refs))

    def payload(self) -> dict[str, Any]:
        return {
            "metric_values": dict(self.metric_values),
            "observation_digest": self.observation_digest,
            "steps": self.steps,
            "tokens": self.tokens,
            "cost_units": self.cost_units,
            "capabilities_used": list(self.capabilities_used),
            "evidence_refs": list(self.evidence_refs),
        }

    @property
    def digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True, slots=True)
class MirrorRoomSpec:
    """Fully bound Mirror Room experiment contract."""

    manifest: ExperimentManifest
    production_baseline: MirrorCandidate
    metrics: tuple[MirrorMetricPolicy, ...]
    sandbox_policy: SandboxPolicy = SandboxPolicy()
    budget: MirrorBudget = MirrorBudget()
    seed_salt: str = "mirror-room-v1"
    hard_example_limit: int = 16
    stagnation_patience: int = 2

    def __post_init__(self) -> None:
        if not isinstance(self.manifest, ExperimentManifest):
            raise MirrorRoomError("manifest must be ExperimentManifest")
        eligibility = self.manifest.eligibility
        if eligibility.traffic_mode is not TrafficMode.OFFLINE:
            raise MirrorRoomError("Mirror Room requires an offline experiment manifest")
        if eligibility.max_traffic_fraction != 0.0:
            raise MirrorRoomError("Mirror Room cannot receive production traffic")
        if eligibility.external_side_effects_allowed:
            raise MirrorRoomError("Mirror Room cannot authorize external side effects")
        if not isinstance(self.production_baseline, MirrorCandidate):
            raise MirrorRoomError("production_baseline must be MirrorCandidate")
        if self.production_baseline.parent_candidate_id is not None:
            raise MirrorRoomError("production baseline cannot be a child candidate")
        if not isinstance(self.metrics, tuple) or not self.metrics:
            raise MirrorRoomError("metrics must be a non-empty tuple")
        if any(not isinstance(metric, MirrorMetricPolicy) for metric in self.metrics):
            raise MirrorRoomError("metrics must contain MirrorMetricPolicy")
        metric_ids = [metric.metric_id for metric in self.metrics]
        if len(metric_ids) != len(set(metric_ids)):
            raise MirrorRoomError("Mirror Room metric IDs must be unique")

        manifest_metrics = {metric.metric_id: metric for metric in self.manifest.metrics}
        if set(metric_ids) != set(manifest_metrics):
            raise MirrorRoomError("Mirror Room metrics must exactly match experiment manifest metrics")
        for metric in self.metrics:
            if manifest_metrics[metric.metric_id].direction is not metric.direction:
                raise MirrorRoomError(f"metric direction mismatch: {metric.metric_id}")

        if not isinstance(self.sandbox_policy, SandboxPolicy):
            raise MirrorRoomError("sandbox_policy must be SandboxPolicy")
        if not isinstance(self.budget, MirrorBudget):
            raise MirrorRoomError("budget must be MirrorBudget")
        object.__setattr__(self, "seed_salt", _token("seed_salt", self.seed_salt))
        object.__setattr__(
            self,
            "hard_example_limit",
            _positive_int("hard_example_limit", self.hard_example_limit),
        )
        object.__setattr__(
            self,
            "stagnation_patience",
            _positive_int(
                "stagnation_patience",
                self.stagnation_patience,
            ),
        )
        if self.stagnation_patience > self.budget.max_generations:
            raise MirrorRoomError(
                "stagnation_patience cannot exceed generation budget"
            )

        # The Mirror Room may tighten the declared experiment budget, never widen it.
        if self.budget.max_episodes > self.manifest.budget.max_samples:
            raise MirrorRoomError("Mirror Room episode budget exceeds experiment sample budget")
        if self.budget.max_total_tokens > self.manifest.budget.max_tokens:
            raise MirrorRoomError("Mirror Room token budget exceeds experiment token budget")
        if self.budget.max_total_cost_units > self.manifest.budget.max_cost_units:
            raise MirrorRoomError("Mirror Room cost budget exceeds experiment cost budget")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "manifest_digest": self.manifest.manifest_digest,
                "production_baseline_digest": self.production_baseline.digest,
                "metrics": [metric.payload() for metric in sorted(self.metrics, key=lambda x: x.metric_id)],
                "sandbox_policy_digest": self.sandbox_policy.digest,
                "budget_digest": self.budget.digest,
                "seed_salt": self.seed_salt,
                "hard_example_limit": self.hard_example_limit,
                "stagnation_patience": self.stagnation_patience,
                "production_authority": False,
                "direct_self_modify": False,
            }
        )


@dataclass(frozen=True, slots=True)
class HardExample:
    """Training-visible counterexample selected without holdout disclosure."""

    scenario_id: str
    scenario_digest: str
    difficulty: float
    metric_deltas: Mapping[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario_id", _token("scenario_id", self.scenario_id))
        object.__setattr__(self, "scenario_digest", _sha256("scenario_digest", self.scenario_digest))
        object.__setattr__(self, "difficulty", _finite("difficulty", self.difficulty, minimum=0.0))
        if not isinstance(self.metric_deltas, Mapping):
            raise MirrorRoomError("metric_deltas must be a mapping")
        normalized = {
            _token("metric_id", key): _finite(f"metric_deltas[{key}]", value)
            for key, value in self.metric_deltas.items()
        }
        object.__setattr__(self, "metric_deltas", _FrozenDict(dict(sorted(normalized.items()))))


@dataclass(frozen=True, slots=True)
class LearningFeedback:
    """Only information a candidate generator may observe between generations."""

    generation: int
    champion: MirrorCandidate
    training_scenarios: tuple[MirrorScenario, ...]
    hard_examples: tuple[HardExample, ...]
    prior_candidate_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "generation", _positive_int("generation", self.generation))
        if not isinstance(self.champion, MirrorCandidate):
            raise MirrorRoomError("champion must be MirrorCandidate")
        if any(
            not isinstance(item, MirrorScenario) or item.split is not ScenarioSplit.TRAIN
            for item in self.training_scenarios
        ):
            raise MirrorRoomError("LearningFeedback can expose only training scenarios")
        if any(not isinstance(item, HardExample) for item in self.hard_examples):
            raise MirrorRoomError("hard_examples must contain HardExample")
        if self.prior_candidate_id is not None:
            object.__setattr__(
                self,
                "prior_candidate_id",
                _token("prior_candidate_id", self.prior_candidate_id),
            )


__all__ = [
    "EpisodeOutcome",
    "HardExample",
    "LearningFeedback",
    "MirrorBudget",
    "MirrorCandidate",
    "MirrorMetricPolicy",
    "MirrorRoomError",
    "MirrorRoomSpec",
    "MirrorScenario",
    "SandboxPolicy",
    "ScenarioSplit",
]
