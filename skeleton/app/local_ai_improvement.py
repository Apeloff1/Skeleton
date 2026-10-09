"""Provider-free, evidence-gated incremental training for an existing native model.

No self-promotion of a model from signatures, speculative evaluation, or a
training-step counter. Each attempted improvement starts from immutable local
weights, uses a distinct held-out UTF-8 file, and creates a NEW checkpoint
only if the best tested epoch improves held-out token perplexity. No existing
weights are mutated on disk; retaining the input checkpoint is the rollback.
This does not certify general model quality or production readiness.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
from typing import Any

from skeleton.ai.model_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.artifact import write_local_model_artifact
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.app.local_ai import load_native_checkpoint
from skeleton.app.local_ai_training import (
    MAX_EPOCHS,
    MAX_TRAINING_TOKENS,
    OfflineTrainingError,
    _read_corpus,
)
from skeleton.cortex.port import tokens
from skeleton.cortex.transformer import TinyTransformer

MIN_HELDOUT_TOKENS = 4
MIN_VALIDATION_IMPROVEMENT = 1e-7


class OfflineImprovementError(OfflineTrainingError):
    """Candidate model cannot be admitted or lacks held-out improvement."""


@dataclass(frozen=True, slots=True)
class OfflineImprovementReceipt:
    parent_model_digest: str
    candidate_model_digest: str
    tokenizer_digest: str
    train_source_sha256: str
    validation_source_sha256: str
    checkpoint_sha256: str
    input_checkpoint_sha256: str
    baseline_perplexity: float
    accepted_perplexity: float
    best_epoch: int
    total_training_steps: int
    attempted_epochs: int
    validation_tokens: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "parent_model_digest": self.parent_model_digest,
            "candidate_model_digest": self.candidate_model_digest,
            "tokenizer_digest": self.tokenizer_digest,
            "train_source_sha256": self.train_source_sha256,
            "validation_source_sha256": self.validation_source_sha256,
            "input_checkpoint_sha256": self.input_checkpoint_sha256,
            "checkpoint_sha256": self.checkpoint_sha256,
            "baseline_perplexity": self.baseline_perplexity,
            "accepted_perplexity": self.accepted_perplexity,
            "heldout_perplexity_reduction": self.baseline_perplexity - self.accepted_perplexity,
            "heldout_improvement_percent": (
                (self.baseline_perplexity - self.accepted_perplexity)
                / self.baseline_perplexity * 100.0
            ),
            "best_epoch": self.best_epoch,
            "attempted_epochs": self.attempted_epochs,
            "training_steps": self.total_training_steps,
            "validation_tokens": self.validation_tokens,
            "new_checkpoint_only": True,
            "rollback_checkpoint_retained": True,
            "hosted_provider_used": False,
            "independent_quality_certification": False,
        }


def _read_lines(
    path: str | Path,
    *,
    label: str,
    vocabulary: set[str],
    minimum_tokens: int,
) -> tuple[bytes, list[str], int]:
    raw, content = _read_corpus(path)
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    usable = [line for line in lines if len(tokens(line)) >= 2]
    if len(usable) != len(lines):
        raise OfflineImprovementError(label + " has an empty or single-token line")
    observed_tokens = [token for line in usable for token in tokens(line)]
    if not minimum_tokens <= len(observed_tokens) <= MAX_TRAINING_TOKENS:
        raise OfflineImprovementError(label + " token count outside bounded admission")
    unknown = sorted(set(observed_tokens) - vocabulary)
    if unknown:
        raise OfflineImprovementError(
            label + " includes tokens missing from the checkpoint vocabulary"
        )
    return raw, usable, len(observed_tokens)


def improve_local_model(
    checkpoint: str | Path,
    training_text: str | Path,
    validation_text: str | Path,
    destination: str | Path,
    *,
    epochs: int = 1,
) -> OfflineImprovementReceipt:
    """Create a new checkpoint only after finite, positive held-out improvement."""
    if type(epochs) is not int or not 1 <= epochs <= MAX_EPOCHS:
        raise OfflineImprovementError("epochs must be 1-4")
    output = Path(destination)
    if output.exists() or output.is_symlink():
        raise OfflineImprovementError("new checkpoint must not already exist")
    if Path(training_text).resolve() == Path(validation_text).resolve():
        raise OfflineImprovementError("training and validation must be separate sources")
    original = load_native_checkpoint(checkpoint)
    original.assert_identity()
    model = original.runtime.model
    if not isinstance(model, TinyTransformer):
        raise OfflineImprovementError("native transformer weights required")
    initial_digest = original.model_digest
    checkpoint_bytes = Path(checkpoint).read_bytes()
    vocab = set(model.stoi)
    train_raw, train_lines, _ = _read_lines(
        training_text, label="training", vocabulary=vocab, minimum_tokens=2,
    )
    heldout_raw, heldout_lines, heldout_count = _read_lines(
        validation_text, label="validation", vocabulary=vocab,
        minimum_tokens=MIN_HELDOUT_TOKENS,
    )
    if hashlib.sha256(train_raw).digest() == hashlib.sha256(heldout_raw).digest():
        raise OfflineImprovementError("training and validation inputs are identical")
    if set(train_lines) & set(heldout_lines):
        raise OfflineImprovementError("held-out evaluation overlaps a training line")

    baseline = model.perplexity(heldout_lines)
    if not math.isfinite(baseline) or baseline <= 0:
        raise OfflineImprovementError("baseline held-out perplexity is invalid")

    best_score = baseline
    best_epoch = 0
    best_snapshot: dict[str, Any] | None = None
    step_count = 0
    for epoch in range(1, epochs + 1):
        step_count += model.fit(train_lines, lr=0.02, schedule="cosine")
        observed = model.perplexity(heldout_lines)
        if not math.isfinite(observed) or observed <= 0:
            raise OfflineImprovementError("candidate produced nonfinite held-out perplexity")
        if observed < best_score - MIN_VALIDATION_IMPROVEMENT:
            best_score = observed
            best_epoch = epoch
            best_snapshot = model.snapshot()

    if not best_epoch or best_snapshot is None:
        # A failed evaluation never calls the writer and cannot overwrite the
        # original model; evidence of training work alone is not promotion.
        raise OfflineImprovementError(
            "no held-out improvement; candidate refused and parent checkpoint retained"
        )
    trained = TinyTransformer.from_snapshot(best_snapshot)
    candidate = NativeRuntimeLocalModel(NativeLLMRuntime(trained))
    if candidate.model_digest == initial_digest:
        raise OfflineImprovementError("candidate weights did not change")
    if candidate.tokenizer_digest != original.tokenizer_digest:
        raise OfflineImprovementError("tokenizer identity drift after training")
    independently_rechecked = trained.perplexity(heldout_lines)
    if not math.isclose(independently_rechecked, best_score, abs_tol=1e-9, rel_tol=1e-9):
        raise OfflineImprovementError("candidate replay differs from selected held-out epoch")
    written = write_local_model_artifact(candidate, output)
    restored = load_native_checkpoint(output)
    if (
        restored.model_digest != candidate.model_digest
        or restored.tokenizer_digest != original.tokenizer_digest
    ):
        raise OfflineImprovementError("candidate on-disk identity differs after restore")
    return OfflineImprovementReceipt(
        parent_model_digest=initial_digest,
        candidate_model_digest=restored.model_digest,
        tokenizer_digest=restored.tokenizer_digest,
        train_source_sha256=hashlib.sha256(train_raw).hexdigest(),
        validation_source_sha256=hashlib.sha256(heldout_raw).hexdigest(),
        input_checkpoint_sha256=hashlib.sha256(checkpoint_bytes).hexdigest(),
        checkpoint_sha256=written.artifact_sha256,
        baseline_perplexity=baseline,
        accepted_perplexity=best_score,
        best_epoch=best_epoch,
        attempted_epochs=epochs,
        total_training_steps=step_count,
        validation_tokens=heldout_count,
    )
