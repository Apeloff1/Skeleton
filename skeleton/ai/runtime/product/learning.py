"""Fail-closed reverse learning handoff for the canonical standalone AI path.

This module closes one specific product-to-model seam:

    accepted canonical assistant turn
        -> deterministic bounded learning candidate
        -> offline local-model candidate artifact

It deliberately does *not* let runtime output mutate the active model.  Selection
is explicit, privacy classes are bounded, tool-augmented examples require an
additional opt-in, and the artifact builder refuses to overwrite the currently
activated local model path.

Promotion, evaluation-firewall checks, rollback policy, and production model
selection remain separate authorities.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Iterable, Sequence

from skeleton.contracts.conversation import (
    ConversationAuthorType,
    ConversationMessage,
)
from skeleton.persistence.conversation_repository import (
    SQLiteConversationRepository,
)
from skeleton.ai.runtime.inference.training_allocation import (
    AdaptiveMethodAllocation,
)
from skeleton.ai.runtime.inference.training_methods import (
    MethodWeight,
    TrainingEfficiencyPolicy,
    TrainingExample,
    TrainingMethod,
)


_MAX_ACCEPTED_PAIRS = 1_024
_MAX_PAIR_CHARS = 200_000
_MAX_CORPUS_CHARS = 8_000_000
_DEFAULT_ALLOWED_DATA_CLASSES = frozenset({"public", "internal"})


class CanonicalLearningHandoffError(RuntimeError):
    """A product turn cannot safely become a local-model learning candidate."""


def _stable_digest(payload: object) -> str:
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CanonicalLearningHandoffError(
            "learning candidate identity is not deterministic JSON"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _normalized_training_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CanonicalLearningHandoffError(
            f"{field} must be non-empty inline text"
        )
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    # The existing corpus reader uses blank lines as document separators.
    # Collapse them inside one accepted pair so a user/assistant example stays
    # one training document when materialized through that builder.
    normalized = re.sub(r"\n[ \t]*\n+", "\n", normalized)
    if len(normalized) > _MAX_PAIR_CHARS:
        raise CanonicalLearningHandoffError(
            f"{field} exceeds learning handoff character bound"
        )
    return normalized


def _accepted_ids(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise CanonicalLearningHandoffError(
            "accepted_assistant_message_ids must be an iterable"
        )
    result: list[str] = []
    for raw in values:
        if not isinstance(raw, str) or not raw.strip() or raw.strip() != raw:
            raise CanonicalLearningHandoffError(
                "accepted assistant message ids must be normalized non-empty text"
            )
        if raw not in result:
            result.append(raw)
        if len(result) > _MAX_ACCEPTED_PAIRS:
            raise CanonicalLearningHandoffError(
                "accepted learning pair count exceeds hard bound"
            )
    if not result:
        raise CanonicalLearningHandoffError(
            "explicit accepted assistant message ids are required"
        )
    return tuple(result)


@dataclass(frozen=True, slots=True)
class CanonicalLearningPair:
    """One explicitly accepted causal user/assistant pair."""

    thread_id: str
    branch_id: str
    user_message_id: str
    assistant_message_id: str
    operation_id: str
    ai_result_id: str
    context_id: str
    context_digest: str
    user_text: str
    assistant_text: str
    provider_receipt_refs: tuple[str, ...]
    tool_receipt_refs: tuple[str, ...]
    data_class: str

    def __post_init__(self) -> None:
        for name in (
            "thread_id",
            "branch_id",
            "user_message_id",
            "assistant_message_id",
            "operation_id",
            "ai_result_id",
            "context_id",
            "data_class",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise CanonicalLearningHandoffError(
                    f"{name} must be non-empty"
                )
        if (
            not isinstance(self.context_digest, str)
            or len(self.context_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in self.context_digest)
        ):
            raise CanonicalLearningHandoffError(
                "context_digest must be lowercase sha256"
            )
        object.__setattr__(
            self,
            "user_text",
            _normalized_training_text(self.user_text, "user_text"),
        )
        object.__setattr__(
            self,
            "assistant_text",
            _normalized_training_text(self.assistant_text, "assistant_text"),
        )
        if not self.provider_receipt_refs:
            raise CanonicalLearningHandoffError(
                "accepted assistant turn requires provider receipt lineage"
            )

    @property
    def identity_digest(self) -> str:
        return _stable_digest(
            {
                "schema_version": "skeleton.product.learning-pair.v1",
                "thread_id": self.thread_id,
                "branch_id": self.branch_id,
                "user_message_id": self.user_message_id,
                "assistant_message_id": self.assistant_message_id,
                "operation_id": self.operation_id,
                "ai_result_id": self.ai_result_id,
                "context_id": self.context_id,
                "context_digest": self.context_digest,
                "user_sha256": hashlib.sha256(
                    self.user_text.encode("utf-8")
                ).hexdigest(),
                "assistant_sha256": hashlib.sha256(
                    self.assistant_text.encode("utf-8")
                ).hexdigest(),
                "provider_receipt_refs": list(self.provider_receipt_refs),
                "tool_receipt_refs": list(self.tool_receipt_refs),
                "data_class": self.data_class,
            }
        )

    @property
    def document(self) -> str:
        return (
            "<|user|>\n"
            + self.user_text
            + "\n<|assistant|>\n"
            + self.assistant_text
        )


@dataclass(frozen=True, slots=True)
class CanonicalLearningCandidate:
    """Content-addressed, non-promoted corpus candidate."""

    pairs: tuple[CanonicalLearningPair, ...]
    allowed_data_classes: tuple[str, ...]
    tool_augmented: bool
    source_thread_version: int | None = None

    def __post_init__(self) -> None:
        if not self.pairs:
            raise CanonicalLearningHandoffError(
                "learning candidate requires at least one accepted pair"
            )
        if len(self.pairs) > _MAX_ACCEPTED_PAIRS:
            raise CanonicalLearningHandoffError(
                "learning candidate pair count exceeds hard bound"
            )
        ids = [pair.assistant_message_id for pair in self.pairs]
        if len(ids) != len(set(ids)):
            raise CanonicalLearningHandoffError(
                "learning candidate contains duplicate assistant identity"
            )
        if self.source_thread_version is not None and (
            isinstance(self.source_thread_version, bool)
            or not isinstance(self.source_thread_version, int)
            or self.source_thread_version < 1
        ):
            raise CanonicalLearningHandoffError(
                "source_thread_version must be a positive integer"
            )
        total = sum(len(pair.document) for pair in self.pairs)
        if total > _MAX_CORPUS_CHARS:
            raise CanonicalLearningHandoffError(
                "learning candidate corpus exceeds hard character bound"
            )

    @property
    def documents(self) -> tuple[str, ...]:
        return tuple(pair.document for pair in self.pairs)

    @property
    def identity_digest(self) -> str:
        return _stable_digest(
            {
                "schema_version": "skeleton.product.learning-candidate.v1",
                "pair_digests": [pair.identity_digest for pair in self.pairs],
                "allowed_data_classes": list(self.allowed_data_classes),
                "tool_augmented": self.tool_augmented,
                "source_thread_version": self.source_thread_version,
            }
        )

    @property
    def reference(self) -> str:
        return "product-learning-sha256:" + self.identity_digest

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.product.learning-candidate.v1",
            "reference": self.reference,
            "identity_digest": self.identity_digest,
            "pair_count": len(self.pairs),
            "assistant_message_ids": [
                pair.assistant_message_id for pair in self.pairs
            ],
            "allowed_data_classes": list(self.allowed_data_classes),
            "tool_augmented": self.tool_augmented,
            "source_thread_version": self.source_thread_version,
        }


def build_learning_candidate(
    messages: Sequence[ConversationMessage],
    *,
    accepted_assistant_message_ids: Iterable[str],
    allowed_data_classes: Iterable[str] = _DEFAULT_ALLOWED_DATA_CLASSES,
    allow_tool_augmented: bool = False,
    source_thread_version: int | None = None,
) -> CanonicalLearningCandidate:
    """Select explicit accepted turns and bind them to canonical lineage.

    No message is learned from merely because it exists.  Every assistant
    message must be named by the caller, must have its causal user turn present,
    must carry execution/context/provider lineage, and must satisfy the caller's
    data-class policy.
    """

    accepted = _accepted_ids(accepted_assistant_message_ids)
    if isinstance(allowed_data_classes, (str, bytes)):
        raise CanonicalLearningHandoffError(
            "allowed_data_classes must be an iterable"
        )
    classes = tuple(
        sorted(
            {
                str(value).strip().lower()
                for value in allowed_data_classes
                if str(value).strip()
            }
        )
    )
    if not classes:
        raise CanonicalLearningHandoffError(
            "at least one allowed data class is required"
        )
    unknown = set(classes) - {
        "public",
        "internal",
        "confidential",
        "restricted",
    }
    if unknown:
        raise CanonicalLearningHandoffError(
            "allowed_data_classes contains unsupported values"
        )

    by_id: dict[str, ConversationMessage] = {}
    previous_sequence: int | None = None
    thread_id: str | None = None
    for message in messages:
        if not isinstance(message, ConversationMessage):
            raise TypeError("messages must contain ConversationMessage values")
        if message.message_id in by_id:
            raise CanonicalLearningHandoffError(
                "conversation slice contains duplicate message identity"
            )
        if previous_sequence is not None and message.sequence <= previous_sequence:
            raise CanonicalLearningHandoffError(
                "conversation slice must be strictly sequence ordered"
            )
        previous_sequence = message.sequence
        if thread_id is None:
            thread_id = message.thread_id
        elif message.thread_id != thread_id:
            raise CanonicalLearningHandoffError(
                "conversation slice cannot mix thread identities"
            )
        by_id[message.message_id] = message

    selected: list[CanonicalLearningPair] = []
    for assistant_id in accepted:
        assistant = by_id.get(assistant_id)
        if assistant is None:
            raise CanonicalLearningHandoffError(
                "accepted assistant message is absent from conversation slice"
            )
        if assistant.author_type is not ConversationAuthorType.ASSISTANT:
            raise CanonicalLearningHandoffError(
                "accepted learning identity must reference an assistant message"
            )
        if assistant.content is None:
            raise CanonicalLearningHandoffError(
                "content-ref-only assistant messages require explicit materialization"
            )
        if (
            assistant.causal_user_message_id is None
            or assistant.operation_id is None
            or assistant.ai_result_id is None
            or assistant.context_id is None
            or assistant.context_digest is None
        ):
            raise CanonicalLearningHandoffError(
                "accepted assistant message lacks canonical execution/context lineage"
            )
        user = by_id.get(assistant.causal_user_message_id)
        if user is None or user.author_type is not ConversationAuthorType.USER:
            raise CanonicalLearningHandoffError(
                "accepted assistant message lacks its causal user message"
            )
        if user.content is None:
            raise CanonicalLearningHandoffError(
                "content-ref-only user messages require explicit materialization"
            )
        if user.thread_id != assistant.thread_id:
            raise CanonicalLearningHandoffError(
                "learning pair crosses conversation threads"
            )
        if user.branch_id != assistant.branch_id:
            raise CanonicalLearningHandoffError(
                "learning pair crosses conversation branches"
            )
        if assistant.parent_message_id != user.message_id:
            raise CanonicalLearningHandoffError(
                "accepted assistant message is not directly parented by its causal user"
            )
        if user.data_class != assistant.data_class:
            raise CanonicalLearningHandoffError(
                "learning pair data-class identity is inconsistent"
            )
        if assistant.data_class not in classes:
            raise CanonicalLearningHandoffError(
                "learning pair data class is not admitted"
            )
        if assistant.tool_receipt_refs and not allow_tool_augmented:
            raise CanonicalLearningHandoffError(
                "tool-augmented turns require explicit learning opt-in"
            )
        if not assistant.provider_receipt_refs:
            raise CanonicalLearningHandoffError(
                "accepted assistant message lacks provider receipt lineage"
            )

        selected.append(
            CanonicalLearningPair(
                thread_id=assistant.thread_id,
                branch_id=assistant.branch_id,
                user_message_id=user.message_id,
                assistant_message_id=assistant.message_id,
                operation_id=assistant.operation_id,
                ai_result_id=assistant.ai_result_id,
                context_id=assistant.context_id,
                context_digest=assistant.context_digest,
                user_text=user.content,
                assistant_text=assistant.content,
                provider_receipt_refs=assistant.provider_receipt_refs,
                tool_receipt_refs=assistant.tool_receipt_refs,
                data_class=assistant.data_class,
            )
        )

    selected.sort(
        key=lambda pair: by_id[pair.assistant_message_id].sequence
    )
    return CanonicalLearningCandidate(
        pairs=tuple(selected),
        allowed_data_classes=classes,
        tool_augmented=bool(allow_tool_augmented),
        source_thread_version=source_thread_version,
    )


def build_learning_candidate_from_repository(
    conversations: SQLiteConversationRepository,
    *,
    thread_id: str,
    tenant_id: str,
    owner_id: str,
    expected_thread_version: int,
    accepted_assistant_message_ids: Iterable[str],
    allowed_data_classes: Iterable[str] = _DEFAULT_ALLOWED_DATA_CLASSES,
    allow_tool_augmented: bool = False,
) -> CanonicalLearningCandidate:
    """Build from the exact active durable transcript at one thread version."""

    if not isinstance(conversations, SQLiteConversationRepository):
        raise TypeError(
            "conversations must be SQLiteConversationRepository"
        )
    if (
        isinstance(expected_thread_version, bool)
        or not isinstance(expected_thread_version, int)
        or expected_thread_version < 1
    ):
        raise CanonicalLearningHandoffError(
            "expected_thread_version must be a positive integer"
        )

    before = conversations.get_thread(
        thread_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
    )
    if before.version != expected_thread_version:
        raise CanonicalLearningHandoffError(
            "conversation version changed before learning snapshot"
        )
    if before.message_sequence > 500:
        raise CanonicalLearningHandoffError(
            "learning snapshot exceeds bounded active transcript window"
        )

    transcript = conversations.active_transcript(
        thread_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
    )
    after = conversations.get_thread(
        thread_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
    )
    if (
        after.version != before.version
        or after.message_sequence != before.message_sequence
        or after.active_branch_id != before.active_branch_id
    ):
        raise CanonicalLearningHandoffError(
            "conversation changed while learning snapshot was read"
        )

    return build_learning_candidate(
        transcript,
        accepted_assistant_message_ids=accepted_assistant_message_ids,
        allowed_data_classes=allowed_data_classes,
        allow_tool_augmented=allow_tool_augmented,
        source_thread_version=before.version,
    )


def _baseline_identity(active_raw: str) -> dict[str, object] | None:
    """Resolve the exact active local artifact identity for later comparison."""

    if not active_raw:
        return None
    from skeleton.ai.runtime.inference.artifact import (
        LocalModelArtifactError,
        load_local_model_artifact,
    )

    try:
        loaded = load_local_model_artifact(active_raw)
    except LocalModelArtifactError as exc:
        raise CanonicalLearningHandoffError(
            "active local model artifact cannot be authenticated"
        ) from exc
    return {
        "artifact_sha256": loaded.receipt.artifact_sha256,
        "model_id": loaded.receipt.model_id,
        "model_digest": loaded.receipt.model_digest,
        "schema": loaded.receipt.schema,
        "reference": loaded.receipt.reference,
    }


def build_learning_candidate_artifact(
    candidate: CanonicalLearningCandidate,
    *,
    output_path: str | Path,
    model_id: str,
    hidden_size: int = 32,
    epochs: int = 4,
    learning_rate: float = 0.05,
    max_vocab: int = 4_096,
    max_document_tokens: int = 1_024,
    seed: int = 0,
    temperature: float = 0.8,
    training_methods: Sequence[
        TrainingMethod | MethodWeight
    ] = tuple(TrainingMethod),
    efficiency_policy: TrainingEfficiencyPolicy | None = None,
    method_allocation: AdaptiveMethodAllocation | None = None,
) -> dict[str, object]:
    """Train one *candidate* artifact from an accepted canonical corpus.

    This helper refuses to overwrite the exact artifact currently selected by
    AI_LOCAL_MODEL_PATH.  Deploying/promoting the candidate is a distinct
    governed operation outside this module.
    """

    if not isinstance(candidate, CanonicalLearningCandidate):
        raise TypeError("candidate must be CanonicalLearningCandidate")

    destination = Path(str(output_path).strip()).expanduser()
    if not str(output_path).strip():
        raise CanonicalLearningHandoffError(
            "candidate output path is required"
        )
    try:
        destination_resolved = destination.resolve(strict=False)
    except OSError as exc:
        raise CanonicalLearningHandoffError(
            "candidate output path cannot be resolved"
        ) from exc

    active_raw = os.getenv("AI_LOCAL_MODEL_PATH", "").strip()
    if active_raw:
        try:
            active = Path(active_raw).expanduser().resolve(strict=False)
        except OSError as exc:
            raise CanonicalLearningHandoffError(
                "active local model path cannot be resolved"
            ) from exc
        if destination_resolved == active:
            raise CanonicalLearningHandoffError(
                "learning candidate cannot overwrite active local model artifact"
            )

    baseline = _baseline_identity(active_raw)

    parent = destination_resolved.parent
    if not parent.exists() or not parent.is_dir():
        raise CanonicalLearningHandoffError(
            "candidate output parent directory does not exist"
        )

    # Lazy import keeps NumPy out of product import-time dependencies.
    from skeleton.ai.runtime.inference.train import (
        LocalModelBuildError,
        build_multi_method_recurrent_artifact,
    )

    if method_allocation is not None:
        if not isinstance(method_allocation, AdaptiveMethodAllocation):
            raise TypeError(
                "method_allocation must be AdaptiveMethodAllocation"
            )
        training_methods = method_allocation.method_weights

    examples = tuple(
        TrainingExample(
            example_id=pair.assistant_message_id,
            prompt=pair.user_text,
            response=pair.assistant_text,
            difficulty=0.5,
            source_ref=(
                "conversation-assistant:"
                + pair.assistant_message_id
            ),
            replay=False,
        )
        for pair in candidate.pairs
    )

    try:
        receipt = build_multi_method_recurrent_artifact(
            examples=examples,
            output_path=destination_resolved,
            model_id=model_id,
            methods=training_methods,
            efficiency_policy=efficiency_policy,
            hidden_size=hidden_size,
            epochs=epochs,
            learning_rate=learning_rate,
            max_vocab=max_vocab,
            max_document_tokens=max_document_tokens,
            seed=seed,
            temperature=temperature,
        )
        from skeleton.ai.runtime.inference.artifact import (
            load_local_model_artifact,
        )
        from skeleton.ai.runtime.inference.local import (
            LocalInferenceRequest,
        )
        import threading

        loaded = load_local_model_artifact(destination_resolved)
        qualification_prompt = candidate.pairs[0].user_text
        qualification_request = LocalInferenceRequest(
            prompt=qualification_prompt,
            instructions=(
                "Offline candidate execution qualification. "
                "Do not use external services."
            ),
            max_output_tokens=16,
            seed=0,
        )
        result = loaded.model.infer(
            qualification_request,
            threading.Event(),
        )
        if (
            result.model_digest != loaded.receipt.model_digest
            or result.text is None
            or not result.text.strip()
            or not isinstance(result.response_id, str)
            or not result.response_id.strip()
        ):
            raise CanonicalLearningHandoffError(
                "local-model candidate failed executable qualification"
            )
        qualification = {
            "schema_version": "skeleton.product.learning-qualification.v1",
            "status": "executable_candidate",
            "prompt_sha256": hashlib.sha256(
                qualification_prompt.encode("utf-8")
            ).hexdigest(),
            "output_sha256": hashlib.sha256(
                result.text.encode("utf-8")
            ).hexdigest(),
            "response_id": result.response_id,
            "model_digest": result.model_digest,
        }
        qualification["receipt_digest"] = _stable_digest(qualification)
    except LocalModelBuildError as exc:
        try:
            destination_resolved.unlink(missing_ok=True)
        except OSError:
            pass
        raise CanonicalLearningHandoffError(
            "local-model candidate build failed"
        ) from exc
    except CanonicalLearningHandoffError:
        try:
            destination_resolved.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    except Exception as exc:
        try:
            destination_resolved.unlink(missing_ok=True)
        except OSError:
            pass
        raise CanonicalLearningHandoffError(
            "local-model candidate executable qualification failed"
        ) from exc
    evaluation_manifest: dict[str, object] = {
        "schema_version": "skeleton.product.learning-evaluation-input.v1",
        "learning_candidate_digest": candidate.identity_digest,
        "candidate_artifact_sha256": receipt["artifact_sha256"],
        "candidate_model_id": receipt["model_id"],
        "candidate_model_digest": receipt["model_digest"],
        "qualification_receipt_digest": qualification["receipt_digest"],
        "training_plan_digest": receipt["training_plan"]["plan_digest"],
        "training_methods": [
            item["method"]
            for item in receipt["training_plan"]["methods"]
        ],
        "method_allocation_digest": (
            None
            if method_allocation is None
            else method_allocation.allocation_digest
        ),
        "baseline": baseline,
        "promotion_authority": False,
    }
    evaluation_manifest["manifest_digest"] = _stable_digest(
        evaluation_manifest
    )

    return {
        **receipt,
        "learning_candidate_ref": candidate.reference,
        "learning_candidate_digest": candidate.identity_digest,
        "learning_pair_count": len(candidate.pairs),
        "promotion_state": "candidate_only",
        "qualification": qualification,
        "training_plan": receipt["training_plan"],
        "method_allocation": (
            None
            if method_allocation is None
            else method_allocation.as_dict()
        ),
        "evaluation_manifest": evaluation_manifest,
    }


__all__ = [
    "CanonicalLearningCandidate",
    "CanonicalLearningHandoffError",
    "CanonicalLearningPair",
    "build_learning_candidate",
    "build_learning_candidate_artifact",
    "build_learning_candidate_from_repository",
]
