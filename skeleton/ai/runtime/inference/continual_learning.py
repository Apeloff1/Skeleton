"""Persistent, reversible continual learning for local development.

This module turns isolated optimization rounds into an append-only developmental
lineage. It provides:
- bounded experience replay across accepted rounds;
- acquisition and retention evaluation against the current champion;
- fail-closed catastrophic-forgetting rejection;
- champion/challenger history with reversible developmental rollback;
- content-addressed JSON state that can survive process restarts.

It has no production, deployment, or promotion authority.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

from .artifact import LocalModelArtifactError, load_local_model_artifact
from .developmental_eval import (
    DevelopmentalComparisonReport,
    DevelopmentalEvalSuite,
    DevelopmentalEvaluationError,
    evaluate_local_candidate_developmentally,
)
from .multiview import CameraCoverageSelection
from .training_allocation import TrainingAllocationPolicy
from .training_methods import (
    TrainingEfficiencyPolicy,
    TrainingExample,
    TrainingMethod,
)
from .training_optimizer import (
    TrainingOptimizationPolicy,
    TrainingOptimizationResult,
    TrainingOptimizationError,
    optimize_training_mix,
)
from .visual_learning import VisualTrainingObservation


_MAX_REPLAY_ITEMS = 8_192
_MAX_ROUNDS = 4_096
_MAX_CHAMPIONS = 2_048


class ContinualLearningError(RuntimeError):
    """Continual learning state or round violates bounded learning policy."""


def _json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ContinualLearningError(
            "continual learning state is not deterministic JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ContinualLearningError(f"{field} must be sha256 text")
    result = value.strip().lower()
    if (
        len(result) != 64
        or any(ch not in "0123456789abcdef" for ch in result)
    ):
        raise ContinualLearningError(
            f"{field} must be lowercase sha256"
        )
    return result


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContinualLearningError(f"{field} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise ContinualLearningError(f"{field} exceeds maximum length")
    return result


def _finite(
    value: object,
    field: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContinualLearningError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ContinualLearningError(
            f"{field} must be in [{minimum}, {maximum}]"
        )
    return result


def _example_payload(example: TrainingExample) -> dict[str, object]:
    selection = example.camera_selection
    return {
        "example_id": example.example_id,
        "prompt": example.prompt,
        "response": example.response,
        "rejected_response": example.rejected_response,
        "teacher_response": example.teacher_response,
        "positive_text": example.positive_text,
        "negative_text": example.negative_text,
        "retrieval_context": example.retrieval_context,
        "trajectory": example.trajectory,
        "pseudo_label": example.pseudo_label,
        "task_id": example.task_id,
        "reward": example.reward,
        "difficulty": example.difficulty,
        "source_ref": example.source_ref,
        "replay": example.replay,
        "camera_view_refs": list(example.camera_view_refs),
        "camera_coverage_digest": example.camera_coverage_digest,
        "camera_selection": (
            None
            if selection is None
            else {
                "coverage_digest": selection.coverage_digest,
                "policy_digest": selection.policy_digest,
                "view_refs": list(selection.view_refs),
            }
        ),
        "visual_observations": [
            item.feature_payload()
            | {"feature_digest": item.feature_digest}
            for item in example.visual_observations
        ],
        "tags": list(example.tags),
        "example_digest": example.digest,
    }


def _example_from_payload(payload: Mapping[str, object]) -> TrainingExample:
    raw_selection = payload.get("camera_selection")
    selection: CameraCoverageSelection | None = None
    if raw_selection is not None:
        if not isinstance(raw_selection, Mapping):
            raise ContinualLearningError(
                "camera_selection snapshot must be a mapping"
            )
        selection = CameraCoverageSelection(
            coverage_digest=str(raw_selection.get("coverage_digest", "")),
            policy_digest=str(raw_selection.get("policy_digest", "")),
            view_refs=tuple(
                str(item)
                for item in raw_selection.get("view_refs", ())
            ),
        )

    raw_observations = payload.get("visual_observations", ())
    if (
        isinstance(raw_observations, (str, bytes))
        or not isinstance(raw_observations, Sequence)
    ):
        raise ContinualLearningError(
            "visual_observations snapshot must be a sequence"
        )
    observations: list[VisualTrainingObservation] = []
    for raw in raw_observations:
        if not isinstance(raw, Mapping):
            raise ContinualLearningError(
                "visual observation snapshot must be a mapping"
            )
        observations.append(
            VisualTrainingObservation(
                camera_view_ref=str(raw.get("camera_view_ref", "")),
                asset_id=str(raw.get("asset_id", "")),
                asset_digest=str(raw.get("asset_digest", "")),
                width=int(raw.get("width", 0)),
                height=int(raw.get("height", 0)),
                mean_rgb=tuple(float(v) for v in raw.get("mean_rgb", ())),
                std_rgb=tuple(float(v) for v in raw.get("std_rgb", ())),
                luminance_histogram=tuple(
                    float(v)
                    for v in raw.get("luminance_histogram", ())
                ),
                spatial_rgb=tuple(
                    float(v)
                    for v in raw.get("spatial_rgb", ())
                ),
                edge_density=float(raw.get("edge_density", 0.0)),
                feature_digest=str(raw.get("feature_digest", "")),
            )
        )

    example = TrainingExample(
        example_id=str(payload.get("example_id", "")),
        prompt=str(payload.get("prompt", "")),
        response=str(payload.get("response", "")),
        rejected_response=payload.get("rejected_response"),
        teacher_response=payload.get("teacher_response"),
        positive_text=payload.get("positive_text"),
        negative_text=payload.get("negative_text"),
        retrieval_context=payload.get("retrieval_context"),
        trajectory=payload.get("trajectory"),
        pseudo_label=payload.get("pseudo_label"),
        task_id=payload.get("task_id"),
        reward=payload.get("reward"),
        difficulty=float(payload.get("difficulty", 0.5)),
        source_ref=str(payload.get("source_ref", "source:unspecified")),
        replay=bool(payload.get("replay", False)),
        camera_view_refs=tuple(
            str(item) for item in payload.get("camera_view_refs", ())
        ),
        camera_coverage_digest=payload.get("camera_coverage_digest"),
        camera_selection=selection,
        visual_observations=tuple(observations),
        tags=tuple(str(item) for item in payload.get("tags", ())),
    )
    claimed = payload.get("example_digest")
    if claimed is not None and _sha(claimed, "example_digest") != example.digest:
        raise ContinualLearningError(
            "persisted training example digest mismatch"
        )
    return example


def _example_semantic_digest(example: TrainingExample) -> str:
    payload = _example_payload(example)
    payload["replay"] = False
    payload.pop("example_digest", None)
    return _digest(payload)


@dataclass(frozen=True, slots=True)
class ContinualLearningPolicy:
    """Acceptance and bounded replay policy for repeated training rounds."""

    max_replay_items: int = 1_024
    replay_examples_per_round: int = 64
    minimum_acquisition_gain: float = 0.0
    maximum_retention_drop: float = 0.02
    reject_equal_candidate: bool = True
    cleanup_rejected_candidates: bool = True

    def __post_init__(self) -> None:
        for field, value, minimum, maximum in (
            (
                "max_replay_items",
                self.max_replay_items,
                1,
                _MAX_REPLAY_ITEMS,
            ),
            (
                "replay_examples_per_round",
                self.replay_examples_per_round,
                0,
                _MAX_REPLAY_ITEMS,
            ),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not minimum <= value <= maximum
            ):
                raise ContinualLearningError(
                    f"{field} must be in [{minimum}, {maximum}]"
                )
        if self.replay_examples_per_round > self.max_replay_items:
            raise ContinualLearningError(
                "replay_examples_per_round exceeds replay capacity"
            )
        object.__setattr__(
            self,
            "minimum_acquisition_gain",
            _finite(
                self.minimum_acquisition_gain,
                "minimum_acquisition_gain",
                minimum=-1.0,
                maximum=1.0,
            ),
        )
        object.__setattr__(
            self,
            "maximum_retention_drop",
            _finite(
                self.maximum_retention_drop,
                "maximum_retention_drop",
                minimum=0.0,
                maximum=1.0,
            ),
        )
        if not isinstance(self.reject_equal_candidate, bool):
            raise ContinualLearningError(
                "reject_equal_candidate must be boolean"
            )
        if not isinstance(self.cleanup_rejected_candidates, bool):
            raise ContinualLearningError(
                "cleanup_rejected_candidates must be boolean"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "max_replay_items": self.max_replay_items,
                "replay_examples_per_round": self.replay_examples_per_round,
                "minimum_acquisition_gain": self.minimum_acquisition_gain,
                "maximum_retention_drop": self.maximum_retention_drop,
                "reject_equal_candidate": self.reject_equal_candidate,
                "cleanup_rejected_candidates": (
                    self.cleanup_rejected_candidates
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class ReplayMemoryItem:
    """One accepted example eligible for future deterministic replay."""

    example: TrainingExample
    admitted_round_digest: str
    admitted_generation: int
    importance: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.example, TrainingExample):
            raise TypeError("example must be TrainingExample")
        object.__setattr__(
            self,
            "admitted_round_digest",
            _sha(self.admitted_round_digest, "admitted_round_digest"),
        )
        if (
            isinstance(self.admitted_generation, bool)
            or not isinstance(self.admitted_generation, int)
            or self.admitted_generation < 1
        ):
            raise ContinualLearningError(
                "admitted_generation must be positive"
            )
        object.__setattr__(
            self,
            "importance",
            _finite(
                self.importance,
                "importance",
                minimum=0.0,
                maximum=1_000_000.0,
            ),
        )

    @property
    def semantic_digest(self) -> str:
        return _example_semantic_digest(self.example)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "example_digest": self.example.digest,
                "semantic_digest": self.semantic_digest,
                "admitted_round_digest": self.admitted_round_digest,
                "admitted_generation": self.admitted_generation,
                "importance": self.importance,
            }
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "example": _example_payload(self.example),
            "admitted_round_digest": self.admitted_round_digest,
            "admitted_generation": self.admitted_generation,
            "importance": self.importance,
            "semantic_digest": self.semantic_digest,
            "memory_digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class DevelopmentalChampion:
    """One authenticated local model retained in developmental lineage."""

    generation: int
    artifact_path: str
    model_id: str
    model_digest: str
    artifact_sha256: str
    source_round_digest: str | None
    training_plan_digest: str | None

    def __post_init__(self) -> None:
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation < 0
        ):
            raise ContinualLearningError(
                "champion generation must be non-negative"
            )
        object.__setattr__(
            self,
            "artifact_path",
            _text(self.artifact_path, "artifact_path", maximum=8192),
        )
        object.__setattr__(
            self,
            "model_id",
            _text(self.model_id, "model_id", maximum=512),
        )
        object.__setattr__(
            self,
            "model_digest",
            _sha(self.model_digest, "model_digest"),
        )
        object.__setattr__(
            self,
            "artifact_sha256",
            _sha(self.artifact_sha256, "artifact_sha256"),
        )
        if self.source_round_digest is not None:
            object.__setattr__(
                self,
                "source_round_digest",
                _sha(self.source_round_digest, "source_round_digest"),
            )
        if self.training_plan_digest is not None:
            object.__setattr__(
                self,
                "training_plan_digest",
                _sha(
                    self.training_plan_digest,
                    "training_plan_digest",
                ),
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "generation": self.generation,
                "artifact_path": self.artifact_path,
                "model_id": self.model_id,
                "model_digest": self.model_digest,
                "artifact_sha256": self.artifact_sha256,
                "source_round_digest": self.source_round_digest,
                "training_plan_digest": self.training_plan_digest,
            }
        )

    def verify_artifact(self) -> None:
        try:
            loaded = load_local_model_artifact(self.artifact_path)
        except LocalModelArtifactError as exc:
            raise ContinualLearningError(
                "developmental champion artifact is unavailable"
            ) from exc
        if (
            loaded.receipt.model_id != self.model_id
            or loaded.receipt.model_digest != self.model_digest
            or loaded.receipt.artifact_sha256 != self.artifact_sha256
        ):
            raise ContinualLearningError(
                "developmental champion artifact identity drift"
            )


@dataclass(frozen=True, slots=True)
class ContinualLearningRound:
    """One accepted or rejected challenger attempt."""

    round_index: int
    baseline_champion_digest: str
    challenger_model_digest: str
    challenger_artifact_sha256: str
    challenger_artifact_path: str
    optimization_digest: str
    acquisition_report_digest: str
    retention_report_digest: str
    replay_example_digests: tuple[str, ...]
    new_example_digests: tuple[str, ...]
    acquisition_gain: float
    retention_gain: float
    accepted: bool
    reason: str
    policy_digest: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.round_index, bool)
            or not isinstance(self.round_index, int)
            or not 1 <= self.round_index <= _MAX_ROUNDS
        ):
            raise ContinualLearningError(
                "round_index is outside hard bounds"
            )
        for field in (
            "baseline_champion_digest",
            "challenger_model_digest",
            "challenger_artifact_sha256",
            "optimization_digest",
            "acquisition_report_digest",
            "retention_report_digest",
            "policy_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "challenger_artifact_path",
            _text(
                self.challenger_artifact_path,
                "challenger_artifact_path",
                maximum=8192,
            ),
        )
        object.__setattr__(
            self,
            "replay_example_digests",
            tuple(
                sorted(
                    {
                        _sha(item, "replay_example_digest")
                        for item in self.replay_example_digests
                    }
                )
            ),
        )
        object.__setattr__(
            self,
            "new_example_digests",
            tuple(
                sorted(
                    {
                        _sha(item, "new_example_digest")
                        for item in self.new_example_digests
                    }
                )
            ),
        )
        object.__setattr__(
            self,
            "acquisition_gain",
            _finite(
                self.acquisition_gain,
                "acquisition_gain",
                minimum=-1.0,
                maximum=1.0,
            ),
        )
        object.__setattr__(
            self,
            "retention_gain",
            _finite(
                self.retention_gain,
                "retention_gain",
                minimum=-1.0,
                maximum=1.0,
            ),
        )
        if not isinstance(self.accepted, bool):
            raise ContinualLearningError("accepted must be boolean")
        object.__setattr__(
            self,
            "reason",
            _text(self.reason, "reason", maximum=1024),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "round_index": self.round_index,
                "baseline_champion_digest": self.baseline_champion_digest,
                "challenger_model_digest": self.challenger_model_digest,
                "challenger_artifact_sha256": self.challenger_artifact_sha256,
                "challenger_artifact_path": self.challenger_artifact_path,
                "optimization_digest": self.optimization_digest,
                "acquisition_report_digest": self.acquisition_report_digest,
                "retention_report_digest": self.retention_report_digest,
                "replay_example_digests": list(
                    self.replay_example_digests
                ),
                "new_example_digests": list(self.new_example_digests),
                "acquisition_gain": self.acquisition_gain,
                "retention_gain": self.retention_gain,
                "accepted": self.accepted,
                "reason": self.reason,
                "policy_digest": self.policy_digest,
                "production_authority": False,
            }
        )


@dataclass(frozen=True, slots=True)
class ContinualLearningState:
    """Append-only local developmental lineage and bounded replay memory."""

    lineage_id: str
    champions: tuple[DevelopmentalChampion, ...]
    active_champion_index: int
    replay_memory: tuple[ReplayMemoryItem, ...] = ()
    rounds: tuple[ContinualLearningRound, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "lineage_id",
            _text(self.lineage_id, "lineage_id", maximum=512),
        )
        if (
            not self.champions
            or len(self.champions) > _MAX_CHAMPIONS
            or any(
                not isinstance(item, DevelopmentalChampion)
                for item in self.champions
            )
        ):
            raise ContinualLearningError(
                "champions must be a bounded non-empty tuple"
            )
        if (
            isinstance(self.active_champion_index, bool)
            or not isinstance(self.active_champion_index, int)
            or not 0 <= self.active_champion_index < len(self.champions)
        ):
            raise ContinualLearningError(
                "active_champion_index is invalid"
            )
        if (
            len(self.replay_memory) > _MAX_REPLAY_ITEMS
            or any(
                not isinstance(item, ReplayMemoryItem)
                for item in self.replay_memory
            )
        ):
            raise ContinualLearningError(
                "replay_memory exceeds hard bounds"
            )
        memory_digests = [item.digest for item in self.replay_memory]
        if len(memory_digests) != len(set(memory_digests)):
            raise ContinualLearningError(
                "replay memory contains duplicate entries"
            )
        if (
            len(self.rounds) > _MAX_ROUNDS
            or any(
                not isinstance(item, ContinualLearningRound)
                for item in self.rounds
            )
        ):
            raise ContinualLearningError(
                "round history exceeds hard bounds"
            )
        indices = [item.round_index for item in self.rounds]
        if indices != list(range(1, len(self.rounds) + 1)):
            raise ContinualLearningError(
                "round history must be contiguous and append-only"
            )

    @property
    def active_champion(self) -> DevelopmentalChampion:
        return self.champions[self.active_champion_index]

    @property
    def digest(self) -> str:
        return _digest(self.payload())

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.continual_learning_state.v1",
            "lineage_id": self.lineage_id,
            "champions": [
                {
                    "generation": item.generation,
                    "artifact_path": item.artifact_path,
                    "model_id": item.model_id,
                    "model_digest": item.model_digest,
                    "artifact_sha256": item.artifact_sha256,
                    "source_round_digest": item.source_round_digest,
                    "training_plan_digest": item.training_plan_digest,
                    "champion_digest": item.digest,
                }
                for item in self.champions
            ],
            "active_champion_index": self.active_champion_index,
            "replay_memory": [
                item.as_dict() for item in self.replay_memory
            ],
            "rounds": [
                {
                    "round_index": item.round_index,
                    "baseline_champion_digest": (
                        item.baseline_champion_digest
                    ),
                    "challenger_model_digest": item.challenger_model_digest,
                    "challenger_artifact_sha256": (
                        item.challenger_artifact_sha256
                    ),
                    "challenger_artifact_path": item.challenger_artifact_path,
                    "optimization_digest": item.optimization_digest,
                    "acquisition_report_digest": (
                        item.acquisition_report_digest
                    ),
                    "retention_report_digest": (
                        item.retention_report_digest
                    ),
                    "replay_example_digests": list(
                        item.replay_example_digests
                    ),
                    "new_example_digests": list(item.new_example_digests),
                    "acquisition_gain": item.acquisition_gain,
                    "retention_gain": item.retention_gain,
                    "accepted": item.accepted,
                    "reason": item.reason,
                    "policy_digest": item.policy_digest,
                    "round_digest": item.digest,
                }
                for item in self.rounds
            ],
            "production_authority": False,
        }

    def as_dict(self) -> dict[str, object]:
        payload = self.payload()
        payload["state_digest"] = self.digest
        return payload


def initialize_continual_learning_state(
    *,
    lineage_id: str,
    baseline_path: str | Path,
) -> ContinualLearningState:
    """Create generation zero from one authenticated local model artifact."""

    try:
        loaded = load_local_model_artifact(baseline_path)
        resolved = str(Path(baseline_path).expanduser().resolve(strict=True))
    except (LocalModelArtifactError, OSError) as exc:
        raise ContinualLearningError(
            "baseline artifact cannot initialize continual learning"
        ) from exc
    champion = DevelopmentalChampion(
        generation=0,
        artifact_path=resolved,
        model_id=loaded.receipt.model_id,
        model_digest=loaded.receipt.model_digest,
        artifact_sha256=loaded.receipt.artifact_sha256,
        source_round_digest=None,
        training_plan_digest=None,
    )
    return ContinualLearningState(
        lineage_id=lineage_id,
        champions=(champion,),
        active_champion_index=0,
    )


def _select_replay(
    state: ContinualLearningState,
    *,
    limit: int,
) -> tuple[ReplayMemoryItem, ...]:
    if limit <= 0:
        return ()
    ranked = sorted(
        state.replay_memory,
        key=lambda item: (
            -item.importance,
            item.admitted_generation,
            item.example.digest,
        ),
    )
    if len(ranked) <= limit:
        return tuple(ranked)
    # Deterministically spread selection over the ranked memory instead of
    # always replaying only the same prefix.
    if limit == 1:
        return (ranked[0],)
    selected: list[ReplayMemoryItem] = []
    used: set[str] = set()
    for position in range(limit):
        index = round(
            position * (len(ranked) - 1) / (limit - 1)
        )
        item = ranked[index]
        if item.digest not in used:
            selected.append(item)
            used.add(item.digest)
    for item in ranked:
        if len(selected) >= limit:
            break
        if item.digest not in used:
            selected.append(item)
            used.add(item.digest)
    return tuple(selected)


def _merge_replay_memory(
    state: ContinualLearningState,
    *,
    accepted_examples: tuple[TrainingExample, ...],
    round_digest: str,
    generation: int,
    policy: ContinualLearningPolicy,
    used_replay_semantic_digests: frozenset[str],
    retention_gain: float,
) -> tuple[ReplayMemoryItem, ...]:
    retention_pressure = max(0.0, -retention_gain)
    by_example: dict[str, ReplayMemoryItem] = {}
    for item in state.replay_memory:
        importance = item.importance
        if item.semantic_digest in used_replay_semantic_digests:
            importance = min(
                1_000_000.0,
                importance + 0.1 + retention_pressure,
            )
        by_example[item.semantic_digest] = ReplayMemoryItem(
            example=item.example,
            admitted_round_digest=item.admitted_round_digest,
            admitted_generation=item.admitted_generation,
            importance=importance,
        )
    for example in accepted_examples:
        replay_example = replace(example, replay=True)
        semantic_digest = _example_semantic_digest(replay_example)
        existing = by_example.get(semantic_digest)
        if existing is None:
            by_example[semantic_digest] = ReplayMemoryItem(
                example=replay_example,
                admitted_round_digest=round_digest,
                admitted_generation=generation,
                importance=1.0 + replay_example.difficulty,
            )
        else:
            by_example[semantic_digest] = ReplayMemoryItem(
                example=existing.example,
                admitted_round_digest=existing.admitted_round_digest,
                admitted_generation=existing.admitted_generation,
                importance=min(
                    1_000_000.0,
                    existing.importance + 0.25,
                ),
            )
    ranked = sorted(
        by_example.values(),
        key=lambda item: (
            -item.importance,
            -item.admitted_generation,
            item.example.digest,
        ),
    )
    return tuple(ranked[: policy.max_replay_items])


def run_continual_learning_round(
    *,
    state: ContinualLearningState,
    new_examples: Sequence[TrainingExample],
    acquisition_suite: DevelopmentalEvalSuite,
    retention_suite: DevelopmentalEvalSuite,
    work_dir: str | Path,
    challenger_output_path: str | Path,
    model_id: str,
    policy: ContinualLearningPolicy | None = None,
    requested_methods: Sequence[TrainingMethod] | None = None,
    allocation_policy: TrainingAllocationPolicy | None = None,
    optimization_policy: TrainingOptimizationPolicy | None = None,
    efficiency_policy: TrainingEfficiencyPolicy | None = None,
    hidden_size: int = 32,
    final_epochs: int = 4,
    learning_rate: float = 0.05,
    max_vocab: int = 4_096,
    max_document_tokens: int = 1_024,
    seed: int = 0,
    temperature: float = 0.8,
) -> tuple[ContinualLearningState, ContinualLearningRound]:
    """Train one challenger and accept it only if acquisition+retention pass."""

    if not isinstance(state, ContinualLearningState):
        raise TypeError("state must be ContinualLearningState")
    actual = policy or ContinualLearningPolicy()
    rows = tuple(new_examples)
    if not rows or any(not isinstance(item, TrainingExample) for item in rows):
        raise ContinualLearningError(
            "new_examples must contain at least one TrainingExample"
        )
    ids = [item.example_id for item in rows]
    if len(ids) != len(set(ids)):
        raise ContinualLearningError(
            "new continual-learning example ids must be unique"
        )
    if not isinstance(acquisition_suite, DevelopmentalEvalSuite):
        raise TypeError("acquisition_suite must be DevelopmentalEvalSuite")
    if not isinstance(retention_suite, DevelopmentalEvalSuite):
        raise TypeError("retention_suite must be DevelopmentalEvalSuite")

    baseline = state.active_champion
    baseline.verify_artifact()

    new_semantic_digests = {
        _example_semantic_digest(item) for item in rows
    }
    new_example_ids = {item.example_id for item in rows}
    replay_items = tuple(
        item
        for item in _select_replay(
            state,
            limit=actual.replay_examples_per_round,
        )
        if (
            item.semantic_digest not in new_semantic_digests
            and item.example.example_id not in new_example_ids
        )
    )
    replay_examples = tuple(
        replace(item.example, replay=True)
        for item in replay_items
    )
    training_examples = (*rows, *replay_examples)

    try:
        optimization = optimize_training_mix(
            examples=training_examples,
            baseline_path=baseline.artifact_path,
            suite=acquisition_suite,
            work_dir=work_dir,
            final_output_path=challenger_output_path,
            model_id=model_id,
            requested_methods=requested_methods,
            allocation_policy=allocation_policy,
            optimization_policy=optimization_policy,
            efficiency_policy=efficiency_policy,
            hidden_size=hidden_size,
            final_epochs=final_epochs,
            learning_rate=learning_rate,
            max_vocab=max_vocab,
            max_document_tokens=max_document_tokens,
            seed=seed,
            temperature=temperature,
        )
    except TrainingOptimizationError as exc:
        raise ContinualLearningError(
            "continual challenger optimization failed"
        ) from exc

    receipt = optimization.final_receipt
    candidate_path = receipt.get("output_path")
    training_plan = receipt.get("training_plan")
    if (
        not isinstance(candidate_path, str)
        or not isinstance(training_plan, Mapping)
    ):
        raise ContinualLearningError(
            "optimized challenger receipt is incomplete"
        )
    plan_digest = _sha(
        training_plan.get("plan_digest"),
        "challenger training plan digest",
    )

    # These reports are acceptance diagnostics, not allocator observations.
    # The optimization probe reports already own method attribution.
    representative_method = optimization.allocation.method_weights[0].method
    try:
        acquisition = evaluate_local_candidate_developmentally(
            baseline_path=baseline.artifact_path,
            candidate_path=candidate_path,
            suite=acquisition_suite,
            training_plan_digest=plan_digest,
            method=representative_method,
        )
        retention = evaluate_local_candidate_developmentally(
            baseline_path=baseline.artifact_path,
            candidate_path=candidate_path,
            suite=retention_suite,
            training_plan_digest=plan_digest,
            method=representative_method,
        )
    except DevelopmentalEvaluationError as exc:
        raise ContinualLearningError(
            "continual challenger acceptance evaluation failed"
        ) from exc

    candidate_model = _sha(
        receipt.get("model_digest"),
        "challenger model_digest",
    )
    candidate_artifact = _sha(
        receipt.get("artifact_sha256"),
        "challenger artifact_sha256",
    )
    equal_candidate = candidate_model == baseline.model_digest
    acquisition_ok = (
        acquisition.validation_gain >= actual.minimum_acquisition_gain
    )
    retention_ok = (
        retention.validation_gain >= -actual.maximum_retention_drop
    )
    distinct_ok = not (
        actual.reject_equal_candidate and equal_candidate
    )
    accepted = acquisition_ok and retention_ok and distinct_ok
    reasons: list[str] = []
    if not acquisition_ok:
        reasons.append("insufficient-acquisition-gain")
    if not retention_ok:
        reasons.append("catastrophic-forgetting-guard")
    if not distinct_ok:
        reasons.append("candidate-identical-to-champion")
    if accepted:
        reasons.append("accepted-developmental-challenger")

    round_record = ContinualLearningRound(
        round_index=len(state.rounds) + 1,
        baseline_champion_digest=baseline.digest,
        challenger_model_digest=candidate_model,
        challenger_artifact_sha256=candidate_artifact,
        challenger_artifact_path=str(
            Path(candidate_path).expanduser().resolve(strict=False)
        ),
        optimization_digest=optimization.optimization_digest,
        acquisition_report_digest=acquisition.digest,
        retention_report_digest=retention.digest,
        replay_example_digests=tuple(
            item.example.digest for item in replay_items
        ),
        new_example_digests=tuple(item.digest for item in rows),
        acquisition_gain=acquisition.validation_gain,
        retention_gain=retention.validation_gain,
        accepted=accepted,
        reason=";".join(reasons),
        policy_digest=actual.digest,
    )

    if not accepted:
        if actual.cleanup_rejected_candidates:
            try:
                Path(candidate_path).unlink(missing_ok=True)
            except OSError:
                pass
        return (
            ContinualLearningState(
                lineage_id=state.lineage_id,
                champions=state.champions,
                active_champion_index=state.active_champion_index,
                replay_memory=state.replay_memory,
                rounds=(*state.rounds, round_record),
            ),
            round_record,
        )

    candidate_loaded = load_local_model_artifact(candidate_path)
    generation = baseline.generation + 1
    new_champion = DevelopmentalChampion(
        generation=generation,
        artifact_path=str(
            Path(candidate_path).expanduser().resolve(strict=True)
        ),
        model_id=candidate_loaded.receipt.model_id,
        model_digest=candidate_loaded.receipt.model_digest,
        artifact_sha256=candidate_loaded.receipt.artifact_sha256,
        source_round_digest=round_record.digest,
        training_plan_digest=plan_digest,
    )
    champions = (*state.champions, new_champion)
    replay_memory = _merge_replay_memory(
        state,
        accepted_examples=rows,
        round_digest=round_record.digest,
        generation=generation,
        policy=actual,
        used_replay_semantic_digests=frozenset(
            item.semantic_digest for item in replay_items
        ),
        retention_gain=retention.validation_gain,
    )
    return (
        ContinualLearningState(
            lineage_id=state.lineage_id,
            champions=champions,
            active_champion_index=len(champions) - 1,
            replay_memory=replay_memory,
            rounds=(*state.rounds, round_record),
        ),
        round_record,
    )


def rollback_developmental_champion(
    state: ContinualLearningState,
    *,
    champion_model_digest: str,
) -> ContinualLearningState:
    """Select an earlier authenticated developmental champion without mutation."""

    if not isinstance(state, ContinualLearningState):
        raise TypeError("state must be ContinualLearningState")
    target = _sha(champion_model_digest, "champion_model_digest")
    matches = [
        index
        for index, champion in enumerate(state.champions)
        if champion.model_digest == target
    ]
    if len(matches) != 1:
        raise ContinualLearningError(
            "rollback target must identify exactly one retained champion"
        )
    index = matches[0]
    state.champions[index].verify_artifact()
    return ContinualLearningState(
        lineage_id=state.lineage_id,
        champions=state.champions,
        active_champion_index=index,
        replay_memory=state.replay_memory,
        rounds=state.rounds,
    )


def save_continual_learning_state(
    state: ContinualLearningState,
    path: str | Path,
) -> str:
    """Atomically persist a content-addressed continual-learning snapshot."""

    if not isinstance(state, ContinualLearningState):
        raise TypeError("state must be ContinualLearningState")
    destination = Path(path).expanduser()
    parent = destination.parent
    if not parent.exists() or not parent.is_dir():
        raise ContinualLearningError(
            "state destination parent does not exist"
        )
    payload = state.as_dict()
    raw = (_json(payload) + "\n").encode("utf-8")
    temporary = destination.with_name(
        destination.name + ".tmp-" + state.digest[:12]
    )
    try:
        temporary.write_bytes(raw)
        temporary.replace(destination)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ContinualLearningError(
            "continual learning state could not be persisted"
        ) from exc
    return state.digest


def load_continual_learning_state(
    path: str | Path,
    *,
    verify_active_artifact: bool = True,
) -> ContinualLearningState:
    """Load and authenticate one persisted continual-learning snapshot."""

    source = Path(path).expanduser()
    try:
        raw = source.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContinualLearningError(
            "continual learning state cannot be read"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ContinualLearningError(
            "continual learning state root must be a mapping"
        )
    if payload.get("schema_version") != "skeleton.continual_learning_state.v1":
        raise ContinualLearningError(
            "unsupported continual learning state schema"
        )

    champions: list[DevelopmentalChampion] = []
    for raw_champion in payload.get("champions", ()):
        if not isinstance(raw_champion, Mapping):
            raise ContinualLearningError(
                "champion snapshot must be a mapping"
            )
        champion = DevelopmentalChampion(
            generation=int(raw_champion.get("generation", -1)),
            artifact_path=str(raw_champion.get("artifact_path", "")),
            model_id=str(raw_champion.get("model_id", "")),
            model_digest=str(raw_champion.get("model_digest", "")),
            artifact_sha256=str(raw_champion.get("artifact_sha256", "")),
            source_round_digest=raw_champion.get("source_round_digest"),
            training_plan_digest=raw_champion.get(
                "training_plan_digest"
            ),
        )
        claimed = raw_champion.get("champion_digest")
        if claimed is not None and _sha(
            claimed,
            "champion_digest",
        ) != champion.digest:
            raise ContinualLearningError(
                "persisted champion digest mismatch"
            )
        champions.append(champion)

    memory: list[ReplayMemoryItem] = []
    for raw_item in payload.get("replay_memory", ()):
        if not isinstance(raw_item, Mapping):
            raise ContinualLearningError(
                "replay memory snapshot must be a mapping"
            )
        raw_example = raw_item.get("example")
        if not isinstance(raw_example, Mapping):
            raise ContinualLearningError(
                "replay memory example must be a mapping"
            )
        item = ReplayMemoryItem(
            example=_example_from_payload(raw_example),
            admitted_round_digest=str(
                raw_item.get("admitted_round_digest", "")
            ),
            admitted_generation=int(
                raw_item.get("admitted_generation", 0)
            ),
            importance=float(raw_item.get("importance", 1.0)),
        )
        claimed = raw_item.get("memory_digest")
        if claimed is not None and _sha(
            claimed,
            "memory_digest",
        ) != item.digest:
            raise ContinualLearningError(
                "persisted replay memory digest mismatch"
            )
        memory.append(item)

    rounds: list[ContinualLearningRound] = []
    for raw_round in payload.get("rounds", ()):
        if not isinstance(raw_round, Mapping):
            raise ContinualLearningError(
                "round snapshot must be a mapping"
            )
        item = ContinualLearningRound(
            round_index=int(raw_round.get("round_index", 0)),
            baseline_champion_digest=str(
                raw_round.get("baseline_champion_digest", "")
            ),
            challenger_model_digest=str(
                raw_round.get("challenger_model_digest", "")
            ),
            challenger_artifact_sha256=str(
                raw_round.get("challenger_artifact_sha256", "")
            ),
            challenger_artifact_path=str(
                raw_round.get("challenger_artifact_path", "")
            ),
            optimization_digest=str(
                raw_round.get("optimization_digest", "")
            ),
            acquisition_report_digest=str(
                raw_round.get("acquisition_report_digest", "")
            ),
            retention_report_digest=str(
                raw_round.get("retention_report_digest", "")
            ),
            replay_example_digests=tuple(
                str(v)
                for v in raw_round.get("replay_example_digests", ())
            ),
            new_example_digests=tuple(
                str(v)
                for v in raw_round.get("new_example_digests", ())
            ),
            acquisition_gain=float(
                raw_round.get("acquisition_gain", 0.0)
            ),
            retention_gain=float(
                raw_round.get("retention_gain", 0.0)
            ),
            accepted=bool(raw_round.get("accepted", False)),
            reason=str(raw_round.get("reason", "")),
            policy_digest=str(raw_round.get("policy_digest", "")),
        )
        claimed = raw_round.get("round_digest")
        if claimed is not None and _sha(
            claimed,
            "round_digest",
        ) != item.digest:
            raise ContinualLearningError(
                "persisted round digest mismatch"
            )
        rounds.append(item)

    state = ContinualLearningState(
        lineage_id=str(payload.get("lineage_id", "")),
        champions=tuple(champions),
        active_champion_index=int(
            payload.get("active_champion_index", -1)
        ),
        replay_memory=tuple(memory),
        rounds=tuple(rounds),
    )
    claimed_state = _sha(
        payload.get("state_digest"),
        "state_digest",
    )
    if claimed_state != state.digest:
        raise ContinualLearningError(
            "persisted continual learning state digest mismatch"
        )
    if payload.get("production_authority") is not False:
        raise ContinualLearningError(
            "continual learning state cannot grant production authority"
        )
    if verify_active_artifact:
        state.active_champion.verify_artifact()
    return state


__all__ = [
    "ContinualLearningError",
    "ContinualLearningPolicy",
    "ContinualLearningRound",
    "ContinualLearningState",
    "DevelopmentalChampion",
    "ReplayMemoryItem",
    "initialize_continual_learning_state",
    "load_continual_learning_state",
    "rollback_developmental_champion",
    "run_continual_learning_round",
    "save_continual_learning_state",
]
