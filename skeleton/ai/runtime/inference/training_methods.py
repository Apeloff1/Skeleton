"""Deterministic multi-method corpus compilation for local AI training.

The local recurrent backend consumes text sequences.  This module lets one
bounded trainer exercise the major learning families without inventing a second
model authority.  Each method is compiled into explicit text supervision with a
content-addressed plan receipt.

This is intentionally an execution substrate, not a promotion system.  It owns
no production activation, evaluation holdout, network, tool or policy authority.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
from typing import Mapping, Sequence

from .multiview import CameraCoverageSelection
from .visual_learning import VisualTrainingObservation


_MAX_EXAMPLES = 4_096
_MAX_TEXT = 200_000
_MAX_OUTPUT_DOCUMENTS = 16_384
_MAX_OUTPUT_CHARS = 32_000_000
_TOKEN = re.compile(r"\S+", re.UNICODE)
_CAMERA_VIEW_REF = re.compile(r"^camera-view-sha256:[0-9a-f]{64}$")


class TrainingMethodError(RuntimeError):
    """A multi-method training plan cannot be compiled safely."""


class TrainingMethod(str, Enum):
    """Canonical learning families that can feed the local text trainer."""

    CAUSAL_LANGUAGE_MODELING = "causal_language_modeling"
    SUPERVISED_INSTRUCTION = "supervised_instruction"
    SELF_SUPERVISED_SPAN = "self_supervised_span"
    PREFERENCE = "preference"
    DISTILLATION = "distillation"
    CONTRASTIVE = "contrastive"
    REPLAY = "replay"
    CURRICULUM = "curriculum"
    ADVERSARIAL_ROBUSTNESS = "adversarial_robustness"
    MULTIVIEW_GROUNDING = "multiview_grounding"
    DENOISING_AUTOENCODING = "denoising_autoencoding"
    SEQUENCE_TO_SEQUENCE = "sequence_to_sequence"
    REWARD_MODELING = "reward_modeling"
    REINFORCEMENT_TRACE = "reinforcement_trace"
    IMITATION = "imitation"
    RETRIEVAL_AUGMENTED = "retrieval_augmented"
    PSEUDO_LABEL = "pseudo_label"
    MULTITASK = "multitask"
    ACTIVE_LEARNING = "active_learning"
    CROSS_VIEW_CONSISTENCY = "cross_view_consistency"


DEFAULT_TEXT_METHODS = (
    TrainingMethod.SUPERVISED_INSTRUCTION,
    TrainingMethod.CAUSAL_LANGUAGE_MODELING,
    TrainingMethod.SELF_SUPERVISED_SPAN,
)


def _stable_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise TrainingMethodError(
            "training method state is not deterministic JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _clean_text(
    value: str | None,
    field: str,
    *,
    required: bool = False,
) -> str | None:
    if value is None:
        if required:
            raise TrainingMethodError(f"{field} is required")
        return None
    if not isinstance(value, str):
        raise TrainingMethodError(f"{field} must be text")
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    normalized = re.sub(r"[ \t]+", " ", normalized)
    if not normalized:
        if required:
            raise TrainingMethodError(f"{field} must be non-empty")
        return None
    if len(normalized) > _MAX_TEXT:
        raise TrainingMethodError(f"{field} exceeds hard character bound")
    return normalized


def _finite(
    value: object,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TrainingMethodError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise TrainingMethodError(f"{field} must be finite")
    if minimum is not None and result < minimum:
        raise TrainingMethodError(f"{field} is below minimum")
    if maximum is not None and result > maximum:
        raise TrainingMethodError(f"{field} exceeds maximum")
    return result


@dataclass(frozen=True, slots=True)
class TrainingExample:
    """One source example from which multiple learning views may be compiled."""

    example_id: str
    prompt: str
    response: str
    rejected_response: str | None = None
    teacher_response: str | None = None
    positive_text: str | None = None
    negative_text: str | None = None
    retrieval_context: str | None = None
    trajectory: str | None = None
    pseudo_label: str | None = None
    task_id: str | None = None
    reward: float | None = None
    difficulty: float = 0.5
    source_ref: str = "source:unspecified"
    replay: bool = False
    camera_view_refs: tuple[str, ...] = ()
    camera_coverage_digest: str | None = None
    camera_selection: CameraCoverageSelection | None = None
    visual_observations: tuple[VisualTrainingObservation, ...] = ()
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        example_id = _clean_text(
            self.example_id,
            "example_id",
            required=True,
        )
        prompt = _clean_text(self.prompt, "prompt", required=True)
        response = _clean_text(self.response, "response", required=True)
        source_ref = _clean_text(
            self.source_ref,
            "source_ref",
            required=True,
        )
        object.__setattr__(self, "example_id", example_id)
        object.__setattr__(self, "prompt", prompt)
        object.__setattr__(self, "response", response)
        object.__setattr__(
            self,
            "rejected_response",
            _clean_text(self.rejected_response, "rejected_response"),
        )
        object.__setattr__(
            self,
            "teacher_response",
            _clean_text(self.teacher_response, "teacher_response"),
        )
        object.__setattr__(
            self,
            "positive_text",
            _clean_text(self.positive_text, "positive_text"),
        )
        object.__setattr__(
            self,
            "negative_text",
            _clean_text(self.negative_text, "negative_text"),
        )
        object.__setattr__(
            self,
            "retrieval_context",
            _clean_text(self.retrieval_context, "retrieval_context"),
        )
        object.__setattr__(
            self,
            "trajectory",
            _clean_text(self.trajectory, "trajectory"),
        )
        object.__setattr__(
            self,
            "pseudo_label",
            _clean_text(self.pseudo_label, "pseudo_label"),
        )
        object.__setattr__(
            self,
            "task_id",
            _clean_text(self.task_id, "task_id"),
        )
        if self.reward is not None:
            object.__setattr__(
                self,
                "reward",
                _finite(
                    self.reward,
                    "reward",
                    minimum=-1_000_000.0,
                    maximum=1_000_000.0,
                ),
            )
        object.__setattr__(
            self,
            "difficulty",
            _finite(
                self.difficulty,
                "difficulty",
                minimum=0.0,
                maximum=1.0,
            ),
        )
        selection = self.camera_selection
        if selection is not None:
            if not isinstance(selection, CameraCoverageSelection):
                raise TypeError(
                    "camera_selection must be CameraCoverageSelection"
                )
            if (
                self.camera_coverage_digest is not None
                and self.camera_coverage_digest
                != selection.coverage_digest
            ):
                raise TrainingMethodError(
                    "camera selection coverage differs from example coverage"
                )
            object.__setattr__(
                self,
                "camera_coverage_digest",
                selection.coverage_digest,
            )

        observations = tuple(self.visual_observations)
        if any(
            not isinstance(item, VisualTrainingObservation)
            for item in observations
        ):
            raise TypeError(
                "visual_observations must contain VisualTrainingObservation values"
            )
        observation_refs = tuple(item.camera_view_ref for item in observations)
        if observations and selection is None:
            raise TrainingMethodError(
                "visual observations require authenticated camera selection"
            )
        if selection is not None:
            selected = set(selection.view_refs)
            if any(ref not in selected for ref in observation_refs):
                raise TrainingMethodError(
                    "visual observation camera view is outside authenticated selection"
                )
        if len(observation_refs) != len(set(observation_refs)):
            raise TrainingMethodError(
                "visual observations must have unique camera views"
            )
        if len(observations) > 2_048:
            raise TrainingMethodError(
                "visual_observations exceeds hard bound"
            )
        object.__setattr__(self, "visual_observations", observations)
        views = tuple(
            dict.fromkeys(
                [
                    *(str(item).strip() for item in self.camera_view_refs),
                    *observation_refs,
                ]
            )
        )
        if any(not item for item in views):
            raise TrainingMethodError(
                "camera_view_refs must be non-empty normalized strings"
            )
        if any(_CAMERA_VIEW_REF.fullmatch(item) is None for item in views):
            raise TrainingMethodError(
                "camera_view_refs must use canonical camera-view-sha256 identity"
            )
        if len(views) > 2_048:
            raise TrainingMethodError(
                "camera_view_refs exceeds hard bound"
            )
        object.__setattr__(self, "camera_view_refs", views)
        if views and self.camera_coverage_digest is None:
            raise TrainingMethodError(
                "camera_view_refs require camera_coverage_digest"
            )
        if not views and self.camera_coverage_digest is not None:
            raise TrainingMethodError(
                "camera_coverage_digest requires camera_view_refs"
            )
        if self.camera_coverage_digest is not None:
            coverage_digest = str(self.camera_coverage_digest).strip().lower()
            if (
                len(coverage_digest) != 64
                or any(ch not in "0123456789abcdef" for ch in coverage_digest)
            ):
                raise TrainingMethodError(
                    "camera_coverage_digest must be lowercase sha256"
                )
            object.__setattr__(
                self,
                "camera_coverage_digest",
                coverage_digest,
            )
        tags = tuple(
            sorted(
                {
                    str(item).strip().lower()
                    for item in self.tags
                    if str(item).strip()
                }
            )
        )
        if len(tags) > 128:
            raise TrainingMethodError("tags exceeds hard bound")
        object.__setattr__(self, "tags", tags)
        object.__setattr__(self, "source_ref", source_ref)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "example_id": self.example_id,
                "prompt": self.prompt,
                "response": self.response,
                "rejected_response": self.rejected_response,
                "teacher_response": self.teacher_response,
                "positive_text": self.positive_text,
                "negative_text": self.negative_text,
                "retrieval_context": self.retrieval_context,
                "trajectory": self.trajectory,
                "pseudo_label": self.pseudo_label,
                "task_id": self.task_id,
                "reward": self.reward,
                "difficulty": self.difficulty,
                "source_ref": self.source_ref,
                "replay": self.replay,
                "camera_view_refs": list(self.camera_view_refs),
                "camera_coverage_digest": self.camera_coverage_digest,
                "camera_selection_digest": (
                    None
                    if self.camera_selection is None
                    else self.camera_selection.digest
                ),
                "visual_observation_digests": [
                    item.feature_digest for item in self.visual_observations
                ],
                "tags": list(self.tags),
            }
        )


@dataclass(frozen=True, slots=True)
class TrainingEfficiencyPolicy:
    """Hard resource and ordering policy for corpus materialization."""

    max_documents: int = 4_096
    max_total_chars: int = 16_000_000
    max_document_chars: int = 64_000
    length_bucket_chars: int = 1_024
    deduplicate: bool = True
    curriculum_easy_first: bool = True
    replay_repeat: int = 2
    method_repeat_cap: int = 4
    span_mask_ratio: float = 0.15
    max_camera_views_per_example: int = 64

    def __post_init__(self) -> None:
        integer_bounds = (
            ("max_documents", self.max_documents, 1, _MAX_OUTPUT_DOCUMENTS),
            ("max_total_chars", self.max_total_chars, 1, _MAX_OUTPUT_CHARS),
            ("max_document_chars", self.max_document_chars, 64, _MAX_TEXT),
            ("length_bucket_chars", self.length_bucket_chars, 32, _MAX_TEXT),
            ("replay_repeat", self.replay_repeat, 1, 16),
            ("method_repeat_cap", self.method_repeat_cap, 1, 16),
            (
                "max_camera_views_per_example",
                self.max_camera_views_per_example,
                1,
                2_048,
            ),
        )
        for name, value, lower, upper in integer_bounds:
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not lower <= value <= upper
            ):
                raise TrainingMethodError(
                    f"{name} must be in [{lower}, {upper}]"
                )
        object.__setattr__(
            self,
            "span_mask_ratio",
            _finite(
                self.span_mask_ratio,
                "span_mask_ratio",
                minimum=0.05,
                maximum=0.5,
            ),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "max_documents": self.max_documents,
                "max_total_chars": self.max_total_chars,
                "max_document_chars": self.max_document_chars,
                "length_bucket_chars": self.length_bucket_chars,
                "deduplicate": self.deduplicate,
                "curriculum_easy_first": self.curriculum_easy_first,
                "replay_repeat": self.replay_repeat,
                "method_repeat_cap": self.method_repeat_cap,
                "span_mask_ratio": self.span_mask_ratio,
                "max_camera_views_per_example": (
                    self.max_camera_views_per_example
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class MethodWeight:
    method: TrainingMethod
    repeat: int = 1

    def __post_init__(self) -> None:
        try:
            method = TrainingMethod(self.method)
        except ValueError as exc:
            raise TrainingMethodError("unsupported training method") from exc
        if (
            isinstance(self.repeat, bool)
            or not isinstance(self.repeat, int)
            or not 1 <= self.repeat <= 16
        ):
            raise TrainingMethodError("method repeat must be in [1, 16]")
        object.__setattr__(self, "method", method)


@dataclass(frozen=True, slots=True)
class CompiledTrainingDocument:
    document_id: str
    example_id: str
    method: TrainingMethod
    text: str
    difficulty: float
    source_ref: str
    repeat_ordinal: int
    metadata: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.document_id.startswith("train-doc:"):
            raise TrainingMethodError(
                "document_id must use train-doc identity"
            )
        text = _clean_text(self.text, "compiled text", required=True)
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def content_digest(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class MultiMethodTrainingPlan:
    documents: tuple[CompiledTrainingDocument, ...]
    methods: tuple[MethodWeight, ...]
    source_example_digests: tuple[str, ...]
    camera_coverage_digests: tuple[str, ...]
    visual_observation_digests: tuple[str, ...]
    efficiency_policy_digest: str
    dropped_duplicate_count: int
    dropped_budget_count: int
    method_counts: Mapping[str, int]
    total_chars: int
    plan_digest: str

    def __post_init__(self) -> None:
        if not self.documents:
            raise TrainingMethodError(
                "compiled training plan produced no documents"
            )
        if len(self.documents) > _MAX_OUTPUT_DOCUMENTS:
            raise TrainingMethodError(
                "compiled document count exceeds hard bound"
            )
        object.__setattr__(self, "method_counts", dict(self.method_counts))

    @property
    def corpus(self) -> tuple[str, ...]:
        return tuple(item.text for item in self.documents)

    @property
    def corpus_digest(self) -> str:
        return _digest(
            {
                "schema_version": "skeleton.multi_method_corpus.v1",
                "documents": [
                    {
                        "document_id": item.document_id,
                        "content_digest": item.content_digest,
                    }
                    for item in self.documents
                ],
            }
        )

    @property
    def materialized_methods(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                method
                for method, count in self.method_counts.items()
                if count > 0
            )
        )

    @property
    def skipped_methods(self) -> tuple[str, ...]:
        materialized = set(self.materialized_methods)
        return tuple(
            item.method.value
            for item in self.methods
            if item.method.value not in materialized
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.multi_method_training_plan.v1",
            "plan_digest": self.plan_digest,
            "methods": [
                {
                    "method": item.method.value,
                    "repeat": item.repeat,
                }
                for item in self.methods
            ],
            "source_example_digests": list(self.source_example_digests),
            "camera_coverage_digests": list(self.camera_coverage_digests),
            "visual_observation_digests": list(
                self.visual_observation_digests
            ),
            "document_ids": [item.document_id for item in self.documents],
            "document_count": len(self.documents),
            "corpus_digest": self.corpus_digest,
            "method_counts": dict(self.method_counts),
            "materialized_methods": list(self.materialized_methods),
            "skipped_methods": list(self.skipped_methods),
            "total_chars": self.total_chars,
            "dropped_duplicate_count": self.dropped_duplicate_count,
            "dropped_budget_count": self.dropped_budget_count,
            "efficiency_policy_digest": self.efficiency_policy_digest,
        }


def _supervised(example: TrainingExample) -> str:
    return (
        "<|user|>\n"
        + example.prompt
        + "\n<|assistant|>\n"
        + example.response
    )


def _causal(example: TrainingExample) -> str:
    return (
        "<|dialogue|>\n"
        + example.prompt
        + "\n"
        + example.response
    )


def _span(example: TrainingExample, ratio: float) -> str:
    source = f"{example.prompt}\n{example.response}"
    tokens = list(_TOKEN.findall(source))
    if len(tokens) < 4:
        return (
            "<|reconstruct|>\n<mask>\n<|target|>\n"
            + source
        )
    target_count = max(1, int(round(len(tokens) * ratio)))
    seed = int(example.digest[:16], 16)
    start = seed % max(1, len(tokens) - target_count + 1)
    target = " ".join(tokens[start : start + target_count])
    corrupted = list(tokens)
    corrupted[start : start + target_count] = ["<mask>"]
    return (
        "<|reconstruct|>\n"
        + " ".join(corrupted)
        + "\n<|target|>\n"
        + target
    )


def _preference(example: TrainingExample) -> str | None:
    if example.rejected_response is None:
        return None
    return (
        "<|preference_prompt|>\n"
        + example.prompt
        + "\n<|chosen|>\n"
        + example.response
        + "\n<|rejected|>\n"
        + example.rejected_response
        + "\n<|decision|>\nprefer chosen"
    )


def _distillation(example: TrainingExample) -> str | None:
    if example.teacher_response is None:
        return None
    return (
        "<|user|>\n"
        + example.prompt
        + "\n<|teacher|>\n"
        + example.teacher_response
        + "\n<|student_target|>\n"
        + example.response
    )


def _contrastive(example: TrainingExample) -> str | None:
    if example.positive_text is None or example.negative_text is None:
        return None
    return (
        "<|anchor|>\n"
        + example.prompt
        + "\n<|positive|>\n"
        + example.positive_text
        + "\n<|negative|>\n"
        + example.negative_text
        + "\n<|relation|>\npositive matches anchor"
    )


def _replay(example: TrainingExample) -> str | None:
    if not example.replay:
        return None
    return "<|replay|>\n" + _supervised(example)


def _curriculum(example: TrainingExample) -> str:
    return (
        "<|curriculum difficulty="
        + f"{example.difficulty:.6f}"
        + "|>\n"
        + _supervised(example)
    )


def _adversarial(example: TrainingExample) -> str:
    prompt = example.prompt
    variant = " ".join(prompt.split())
    if variant.endswith("?"):
        variant = variant[:-1] + " ?"
    return (
        "<|robustness_input|>\n"
        + variant
        + "\n<|stable_target|>\n"
        + example.response
    )


def _denoising(
    example: TrainingExample,
    ratio: float,
) -> str:
    source = f"{example.prompt}\n{example.response}"
    tokens = list(_TOKEN.findall(source))
    if not tokens:
        return "<|denoise_input|>\n<mask>\n<|clean_target|>\n" + source
    span = max(1, int(round(len(tokens) * ratio)))
    seed = int(example.digest[16:32], 16)
    start = seed % max(1, len(tokens) - span + 1)
    corrupted = list(tokens)
    corrupted[start : start + span] = ["<noise>"]
    return (
        "<|denoise_input|>\n"
        + " ".join(corrupted)
        + "\n<|clean_target|>\n"
        + source
    )


def _seq2seq(example: TrainingExample) -> str:
    return (
        "<|source|>\n"
        + example.prompt
        + "\n<|target|>\n"
        + example.response
    )


def _reward_modeling(example: TrainingExample) -> str | None:
    if example.reward is None:
        return None
    rejected = (
        ""
        if example.rejected_response is None
        else "\n<|rejected|>\n" + example.rejected_response
    )
    return (
        "<|reward_prompt|>\n"
        + example.prompt
        + "\n<|candidate|>\n"
        + example.response
        + rejected
        + "\n<|reward|>\n"
        + f"{example.reward:.9g}"
    )


def _reinforcement(example: TrainingExample) -> str | None:
    if example.trajectory is None or example.reward is None:
        return None
    return (
        "<|state|>\n"
        + example.prompt
        + "\n<|trajectory|>\n"
        + example.trajectory
        + "\n<|reward|>\n"
        + f"{example.reward:.9g}"
        + "\n<|improved_target|>\n"
        + example.response
    )


def _imitation(example: TrainingExample) -> str:
    demonstration = (
        example.trajectory
        if example.trajectory is not None
        else example.response
    )
    return (
        "<|observation|>\n"
        + example.prompt
        + "\n<|demonstration|>\n"
        + demonstration
        + "\n<|behavior_target|>\n"
        + example.response
    )


def _retrieval(example: TrainingExample) -> str | None:
    if example.retrieval_context is None:
        return None
    return (
        "<|retrieved_evidence|>\n"
        + example.retrieval_context
        + "\n<|question|>\n"
        + example.prompt
        + "\n<|grounded_answer|>\n"
        + example.response
    )


def _pseudo_label(example: TrainingExample) -> str | None:
    label = (
        example.pseudo_label
        if example.pseudo_label is not None
        else example.teacher_response
    )
    if label is None:
        return None
    return (
        "<|unlabeled_input|>\n"
        + example.prompt
        + "\n<|pseudo_label|>\n"
        + label
        + "\n<|verified_target|>\n"
        + example.response
    )


def _multitask(example: TrainingExample) -> str | None:
    task = example.task_id
    if task is None and example.tags:
        task = ",".join(example.tags)
    if task is None:
        return None
    return (
        "<|task|>\n"
        + task
        + "\n<|input|>\n"
        + example.prompt
        + "\n<|output|>\n"
        + example.response
    )


def _active_learning(example: TrainingExample) -> str:
    return (
        "<|active_learning difficulty="
        + f"{example.difficulty:.6f}"
        + "|>\n"
        + _supervised(example)
    )


def _multiview(
    example: TrainingExample,
    *,
    limit: int,
) -> tuple[tuple[str, Mapping[str, object]], ...]:
    if not example.camera_view_refs:
        return ()
    observations = {
        item.camera_view_ref: item
        for item in example.visual_observations
    }
    rows: list[tuple[str, Mapping[str, object]]] = []
    for view_ref in example.camera_view_refs[:limit]:
        observation = observations.get(view_ref)
        visual_text = (
            ""
            if observation is None
            else observation.training_text() + "\n"
        )
        metadata: dict[str, object] = {
            "camera_view_ref": view_ref,
        }
        if observation is not None:
            metadata.update(
                {
                    "visual_observation_ref": observation.reference,
                    "visual_feature_digest": observation.feature_digest,
                    "visual_asset_digest": observation.asset_digest,
                }
            )
        rows.append(
            (
                "<|camera_view|>\n"
                + view_ref
                + "\n"
                + visual_text
                + "<|user|>\n"
                + example.prompt
                + "\n<|grounded_target|>\n"
                + example.response,
                metadata,
            )
        )
    return tuple(rows)


def _cross_view_consistency(
    example: TrainingExample,
    *,
    limit: int,
) -> tuple[tuple[str, Mapping[str, object]], ...]:
    observations = example.visual_observations[:limit]
    if len(observations) < 2:
        return ()
    text_parts = [
        "<|cross_view_consistency|>",
        "<|shared_identity_target|>",
        example.response,
        "<|question|>",
        example.prompt,
    ]
    refs: list[str] = []
    asset_digests: list[str] = []
    for ordinal, observation in enumerate(observations):
        text_parts.extend(
            (
                f"<|view_{ordinal}|>",
                observation.camera_view_ref,
                observation.training_text(),
            )
        )
        refs.append(observation.reference)
        asset_digests.append(observation.asset_digest)
    text_parts.extend(
        (
            "<|invariance_rule|>",
            "preserve shared object and scene identity across camera views",
        )
    )
    return (
        (
            "\n".join(text_parts),
            {
                "visual_observation_refs": refs,
                "visual_asset_digests": asset_digests,
                "camera_view_refs": [
                    item.camera_view_ref for item in observations
                ],
                "camera_coverage_digest": example.camera_coverage_digest,
                "view_count": len(observations),
            },
        ),
    )


def _method_rows(
    example: TrainingExample,
    method: TrainingMethod,
    *,
    policy: TrainingEfficiencyPolicy,
) -> tuple[tuple[str, Mapping[str, object]], ...]:
    if method is TrainingMethod.CAUSAL_LANGUAGE_MODELING:
        return ((_causal(example), {}),)
    if method is TrainingMethod.SUPERVISED_INSTRUCTION:
        return ((_supervised(example), {}),)
    if method is TrainingMethod.SELF_SUPERVISED_SPAN:
        return ((_span(example, policy.span_mask_ratio), {}),)
    if method is TrainingMethod.PREFERENCE:
        value = _preference(example)
        return () if value is None else ((value, {}),)
    if method is TrainingMethod.DISTILLATION:
        value = _distillation(example)
        return () if value is None else ((value, {}),)
    if method is TrainingMethod.CONTRASTIVE:
        value = _contrastive(example)
        return () if value is None else ((value, {}),)
    if method is TrainingMethod.REPLAY:
        value = _replay(example)
        return () if value is None else ((value, {}),)
    if method is TrainingMethod.CURRICULUM:
        return ((_curriculum(example), {}),)
    if method is TrainingMethod.ADVERSARIAL_ROBUSTNESS:
        return ((_adversarial(example), {}),)
    if method is TrainingMethod.MULTIVIEW_GROUNDING:
        return _multiview(
            example,
            limit=policy.max_camera_views_per_example,
        )
    if method is TrainingMethod.DENOISING_AUTOENCODING:
        return ((_denoising(example, policy.span_mask_ratio), {}),)
    if method is TrainingMethod.SEQUENCE_TO_SEQUENCE:
        return ((_seq2seq(example), {}),)
    if method is TrainingMethod.REWARD_MODELING:
        value = _reward_modeling(example)
        return () if value is None else ((value, {}),)
    if method is TrainingMethod.REINFORCEMENT_TRACE:
        value = _reinforcement(example)
        return () if value is None else ((value, {}),)
    if method is TrainingMethod.IMITATION:
        return ((_imitation(example), {}),)
    if method is TrainingMethod.RETRIEVAL_AUGMENTED:
        value = _retrieval(example)
        return () if value is None else ((value, {}),)
    if method is TrainingMethod.PSEUDO_LABEL:
        value = _pseudo_label(example)
        return () if value is None else ((value, {}),)
    if method is TrainingMethod.MULTITASK:
        value = _multitask(example)
        return () if value is None else ((value, {}),)
    if method is TrainingMethod.ACTIVE_LEARNING:
        return ((_active_learning(example), {}),)
    if method is TrainingMethod.CROSS_VIEW_CONSISTENCY:
        return _cross_view_consistency(
            example,
            limit=policy.max_camera_views_per_example,
        )
    raise TrainingMethodError("unsupported training method")


def _normalized_methods(
    methods: Sequence[TrainingMethod | MethodWeight],
    *,
    policy: TrainingEfficiencyPolicy,
) -> tuple[MethodWeight, ...]:
    if not methods:
        raise TrainingMethodError("at least one training method is required")
    result: list[MethodWeight] = []
    seen: set[TrainingMethod] = set()
    for raw in methods:
        item = (
            raw
            if isinstance(raw, MethodWeight)
            else MethodWeight(TrainingMethod(raw))
        )
        if item.method in seen:
            raise TrainingMethodError(
                "training method cannot be configured twice"
            )
        if item.repeat > policy.method_repeat_cap:
            raise TrainingMethodError(
                "method repeat exceeds efficiency policy cap"
            )
        seen.add(item.method)
        result.append(item)
    return tuple(result)


def compatible_training_methods(
    examples: Sequence[TrainingExample],
) -> tuple[TrainingMethod, ...]:
    """Return methods that can materialize from the supplied signal inventory."""

    rows = tuple(examples)
    if not rows:
        raise TrainingMethodError("training examples must be non-empty")
    if any(not isinstance(item, TrainingExample) for item in rows):
        raise TypeError("examples must contain TrainingExample values")

    result: list[TrainingMethod] = []
    for method in TrainingMethod:
        supported = False
        for example in rows:
            if method in {
                TrainingMethod.CAUSAL_LANGUAGE_MODELING,
                TrainingMethod.SUPERVISED_INSTRUCTION,
                TrainingMethod.SELF_SUPERVISED_SPAN,
                TrainingMethod.CURRICULUM,
                TrainingMethod.ADVERSARIAL_ROBUSTNESS,
                TrainingMethod.DENOISING_AUTOENCODING,
                TrainingMethod.SEQUENCE_TO_SEQUENCE,
                TrainingMethod.IMITATION,
                TrainingMethod.ACTIVE_LEARNING,
            }:
                supported = True
            elif (
                method is TrainingMethod.PREFERENCE
                and example.rejected_response is not None
            ):
                supported = True
            elif (
                method is TrainingMethod.DISTILLATION
                and example.teacher_response is not None
            ):
                supported = True
            elif (
                method is TrainingMethod.CONTRASTIVE
                and example.positive_text is not None
                and example.negative_text is not None
            ):
                supported = True
            elif method is TrainingMethod.REPLAY and example.replay:
                supported = True
            elif (
                method is TrainingMethod.MULTIVIEW_GROUNDING
                and bool(example.camera_view_refs)
            ):
                supported = True
            elif (
                method is TrainingMethod.REWARD_MODELING
                and example.reward is not None
            ):
                supported = True
            elif (
                method is TrainingMethod.REINFORCEMENT_TRACE
                and example.trajectory is not None
                and example.reward is not None
            ):
                supported = True
            elif (
                method is TrainingMethod.RETRIEVAL_AUGMENTED
                and example.retrieval_context is not None
            ):
                supported = True
            elif (
                method is TrainingMethod.PSEUDO_LABEL
                and (
                    example.pseudo_label is not None
                    or example.teacher_response is not None
                )
            ):
                supported = True
            elif (
                method is TrainingMethod.MULTITASK
                and (
                    example.task_id is not None
                    or bool(example.tags)
                )
            ):
                supported = True
            elif (
                method is TrainingMethod.CROSS_VIEW_CONSISTENCY
                and len(example.visual_observations) >= 2
            ):
                supported = True
            if supported:
                result.append(method)
                break
    return tuple(result)


def compile_training_plan(
    examples: Sequence[TrainingExample],
    *,
    methods: Sequence[TrainingMethod | MethodWeight] = DEFAULT_TEXT_METHODS,
    policy: TrainingEfficiencyPolicy | None = None,
) -> MultiMethodTrainingPlan:
    """Compile examples into one bounded deterministic multi-method corpus."""

    actual = policy or TrainingEfficiencyPolicy()
    rows = tuple(examples)
    if not rows:
        raise TrainingMethodError("training examples must be non-empty")
    if len(rows) > _MAX_EXAMPLES:
        raise TrainingMethodError(
            "training examples exceeds hard count bound"
        )
    if any(not isinstance(item, TrainingExample) for item in rows):
        raise TypeError("examples must contain TrainingExample values")
    ids = [item.example_id for item in rows]
    if len(ids) != len(set(ids)):
        raise TrainingMethodError(
            "training example ids must be unique"
        )

    configured = _normalized_methods(methods, policy=actual)
    ordered_examples = sorted(
        rows,
        key=lambda item: (
            item.difficulty
            if actual.curriculum_easy_first
            else -item.difficulty,
            item.example_id,
        ),
    )

    emitted: list[CompiledTrainingDocument] = []
    seen_content: set[str] = set()
    dropped_duplicate = 0
    dropped_budget = 0
    total_chars = 0
    method_counts: Counter[str] = Counter()

    for example in ordered_examples:
        for method_weight in configured:
            base_rows = _method_rows(
                example,
                method_weight.method,
                policy=actual,
            )
            if not base_rows:
                continue
            repeat = method_weight.repeat
            if (
                method_weight.method is TrainingMethod.REPLAY
                and example.replay
            ):
                repeat = min(
                    actual.method_repeat_cap,
                    repeat * actual.replay_repeat,
                )
            for base_text, metadata in base_rows:
                text = base_text[: actual.max_document_chars]
                for ordinal in range(repeat):
                    identity_payload = {
                        "schema_version": "skeleton.training_document.v1",
                        "example_digest": example.digest,
                        "method": method_weight.method.value,
                        "text_sha256": hashlib.sha256(
                            text.encode("utf-8")
                        ).hexdigest(),
                        "repeat_ordinal": ordinal,
                        "metadata": dict(metadata),
                    }
                    content_key = identity_payload["text_sha256"]
                    if (
                        actual.deduplicate
                        and ordinal == 0
                        and content_key in seen_content
                    ):
                        dropped_duplicate += 1
                        continue
                    if (
                        len(emitted) >= actual.max_documents
                        or total_chars + len(text) > actual.max_total_chars
                    ):
                        dropped_budget += 1
                        continue
                    if ordinal == 0:
                        seen_content.add(str(content_key))
                    document_id = (
                        "train-doc:" + _digest(identity_payload)
                    )
                    emitted.append(
                        CompiledTrainingDocument(
                            document_id=document_id,
                            example_id=example.example_id,
                            method=method_weight.method,
                            text=text,
                            difficulty=example.difficulty,
                            source_ref=example.source_ref,
                            repeat_ordinal=ordinal,
                            metadata=metadata,
                        )
                    )
                    total_chars += len(text)
                    method_counts[method_weight.method.value] += 1

    if not emitted:
        raise TrainingMethodError(
            "training methods produced no admissible documents"
        )

    emitted.sort(
        key=lambda item: (
            len(item.text) // actual.length_bucket_chars,
            item.difficulty
            if actual.curriculum_easy_first
            else -item.difficulty,
            item.method.value,
            item.repeat_ordinal,
            item.document_id,
        )
    )
    source_digests = tuple(sorted(item.digest for item in rows))
    camera_coverage_digests = tuple(
        sorted(
            {
                item.camera_coverage_digest
                for item in rows
                if item.camera_coverage_digest is not None
            }
        )
    )
    visual_observation_digests = tuple(
        sorted(
            {
                observation.feature_digest
                for item in rows
                for observation in item.visual_observations
            }
        )
    )
    plan_payload = {
        "schema_version": "skeleton.multi_method_training_plan.v1",
        "methods": [
            {
                "method": item.method.value,
                "repeat": item.repeat,
            }
            for item in configured
        ],
        "source_example_digests": list(source_digests),
        "camera_coverage_digests": list(camera_coverage_digests),
        "visual_observation_digests": list(
            visual_observation_digests
        ),
        "efficiency_policy_digest": actual.digest,
        "document_ids": [item.document_id for item in emitted],
        "corpus_digest": _digest(
            {
                "schema_version": "skeleton.multi_method_corpus.v1",
                "documents": [
                    {
                        "document_id": item.document_id,
                        "content_digest": item.content_digest,
                    }
                    for item in emitted
                ],
            }
        ),
        "method_counts": dict(sorted(method_counts.items())),
        "total_chars": total_chars,
        "dropped_duplicate_count": dropped_duplicate,
        "dropped_budget_count": dropped_budget,
    }
    return MultiMethodTrainingPlan(
        documents=tuple(emitted),
        methods=configured,
        source_example_digests=source_digests,
        camera_coverage_digests=camera_coverage_digests,
        visual_observation_digests=visual_observation_digests,
        efficiency_policy_digest=actual.digest,
        dropped_duplicate_count=dropped_duplicate,
        dropped_budget_count=dropped_budget,
        method_counts=dict(sorted(method_counts.items())),
        total_chars=total_chars,
        plan_digest=_digest(plan_payload),
    )


__all__ = [
    "CompiledTrainingDocument",
    "DEFAULT_TEXT_METHODS",
    "MethodWeight",
    "MultiMethodTrainingPlan",
    "TrainingEfficiencyPolicy",
    "TrainingExample",
    "TrainingMethod",
    "TrainingMethodError",
    "compile_training_plan",
    "compatible_training_methods",
]
