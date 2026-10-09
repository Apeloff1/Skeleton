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
from skeleton.ai.runtime.inference.artifact import load_local_model_artifact
from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
from skeleton.app.local_ai import load_native_checkpoint
from skeleton.app.local_ai_training import (
    MAX_EPOCHS,
    MAX_TRAINING_TOKENS,
    OfflineTrainingError,
    _read_corpus,
    publish_native_checkpoint_no_replace,
)
from skeleton.cortex.port import tokens
from skeleton.cortex.transformer import TinyTransformer

MIN_HELDOUT_TOKENS = 4
MIN_VALIDATION_IMPROVEMENT = 1e-7

def _token_weighted_perplexity(model: TinyTransformer, lines: list[str]) -> float:
    """Exponentiate total token negative log-likelihood, not mean line score.

    TinyTransformer.logprob(text) returns the mean log probability per
    predicted token for that individual text. Weight each line by its true
    prediction count before exponentiating. Variable-length evaluation lines
    must not have equal voting power.
    """
    if not lines:
        raise OfflineImprovementError("evaluation requires non-empty text")
    prediction_count = 0
    weighted_log_probability = 0.0
    for line in lines:
        count = len(model._ids(line)) - 1
        if count < 1:
            raise OfflineImprovementError("evaluation line has no predictable token")
        mean_log_probability = model.logprob(line)
        if not math.isfinite(mean_log_probability) or mean_log_probability > 1e-9:
            raise OfflineImprovementError("non-finite or positive model log probability")
        weighted_log_probability += mean_log_probability * count
        prediction_count += count
    if prediction_count < 1 or not math.isfinite(weighted_log_probability):
        raise OfflineImprovementError("held-out likelihood has invalid totals")
    try:
        result = math.exp(-weighted_log_probability / prediction_count)
    except OverflowError as exc:
        raise OfflineImprovementError("held-out perplexity overflow") from exc
    if not math.isfinite(result) or result <= 0:
        raise OfflineImprovementError("held-out perplexity is invalid")
    return result



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
    protected_suite_digest: str | None = None
    protected_suite_passed: bool = False
    protected_suite_cases: int = 0

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
            "protected_suite_digest": self.protected_suite_digest,
            "protected_suite_passed": self.protected_suite_passed,
            "protected_suite_cases": self.protected_suite_cases,
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
    protected_suite: str | Path | None = None,
) -> OfflineImprovementReceipt:
    """Create a new checkpoint only after finite, positive held-out improvement."""
    if type(epochs) is not int or not 1 <= epochs <= MAX_EPOCHS:
        raise OfflineImprovementError("epochs must be 1-4")
    output = Path(destination)
    if output.exists() or output.is_symlink():
        raise OfflineImprovementError("new checkpoint must not already exist")
    if Path(training_text).resolve() == Path(validation_text).resolve():
        raise OfflineImprovementError("training and validation must be separate sources")
    loaded = load_local_model_artifact(checkpoint)
    original = loaded.model
    if not isinstance(original, NativeRuntimeLocalModel):
        raise OfflineImprovementError("only native transformer checkpoints can be improved")
    original.assert_identity()
    source_model = original.runtime.model
    if not isinstance(source_model, TinyTransformer):
        raise OfflineImprovementError("native transformer weights required")
    initial_digest = original.model_digest

    # CPU fitting must NEVER mutate the original identity-bound runtime.
    # Protected category evaluations, source receipts and rollback all
    # depend on immutable baseline weights. Snapshot-clone into an isolated
    # training model before taking any gradient steps.
    model = TinyTransformer.from_snapshot(source_model.snapshot())
    if NativeRuntimeLocalModel(NativeLLMRuntime(model)).model_digest != initial_digest:
        raise OfflineImprovementError(
            "training clone differs from the admitted parent checkpoint"
        )
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
    # Raw-line comparison misses capitalization, punctuation and whitespace
    # aliases that become identical through the *actual* canonical tokenizer.
    # Prevent the same token sequence from acting as both training and
    # supposed held-out validation evidence.
    if {tuple(tokens(line)) for line in train_lines} & {
        tuple(tokens(line)) for line in heldout_lines
    }:
        raise OfflineImprovementError("held-out evaluation overlaps normalized training tokens")

    protected_evidence = None
    protected_baseline = None
    if protected_suite is not None:
        # A third explicit source protects capabilities beyond the scalar
        # epoch-selection corpus. Reject overlaps with either the training
        # or epoch-selection data before *any* SGD mutates in-memory weights.
        from skeleton.app.local_ai_benchmark import (
            _evaluate_backend, _exclude_leaked_training_cases,
            load_benchmark_suite,
        )

        protected_evidence = load_benchmark_suite(protected_suite, backend=original)
        _exclude_leaked_training_cases(
            protected_evidence, checkpoint=original, source=training_text,
        )
        _exclude_leaked_training_cases(
            protected_evidence, checkpoint=original, source=validation_text,
        )
        protected_baseline = _evaluate_backend(protected_evidence, original)

    baseline = _token_weighted_perplexity(model, heldout_lines)
    if not math.isfinite(baseline) or baseline <= 0:
        raise OfflineImprovementError("baseline held-out perplexity is invalid")

    best_score = baseline
    best_epoch = 0
    best_snapshot: dict[str, Any] | None = None
    step_count = 0
    for epoch in range(1, epochs + 1):
        step_count += model.fit(train_lines, lr=0.02, schedule="cosine")
        observed = _token_weighted_perplexity(model, heldout_lines)
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
    independently_rechecked = _token_weighted_perplexity(trained, heldout_lines)
    if not math.isclose(independently_rechecked, best_score, abs_tol=1e-9, rel_tol=1e-9):
        raise OfflineImprovementError("candidate replay differs from selected held-out epoch")
    if protected_evidence is not None:
        from skeleton.app.local_ai_benchmark import (
            _evaluate_backend, compare_benchmark_results,
        )

        guarded_result = _evaluate_backend(protected_evidence, candidate)
        guarded_verdict = compare_benchmark_results(
            protected_baseline, guarded_result,
        )
        if not guarded_verdict["passes_local_regression_gate"]:
            raise OfflineImprovementError(
                "protected benchmark category regression: candidate not published"
            )
    # Protect the pre-publication evidence boundary against data or model
    # edits during multi-epoch CPU execution. The recorded digests must still
    # describe the actual files selected by the operator.
    current_train, _ = _read_corpus(training_text)
    current_holdout, _ = _read_corpus(validation_text)
    if current_train != train_raw or current_holdout != heldout_raw:
        raise OfflineImprovementError(
            "training or validation source changed during execution"
        )
    latest_parent = load_local_model_artifact(checkpoint)
    if (
        latest_parent.receipt.artifact_sha256 != loaded.receipt.artifact_sha256
        or getattr(latest_parent.model, "model_digest", None) != initial_digest
    ):
        raise OfflineImprovementError(
            "original checkpoint changed during execution; candidate not published"
        )
    if protected_evidence is not None:
        from skeleton.app.local_ai_benchmark import load_benchmark_suite

        latest_suite = load_benchmark_suite(protected_suite, backend=original)
        if latest_suite.suite_digest != protected_evidence.suite_digest:
            raise OfflineImprovementError(
                "protected benchmark source changed during execution"
            )
    written = publish_native_checkpoint_no_replace(candidate, output)
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
        input_checkpoint_sha256=loaded.receipt.artifact_sha256,
        checkpoint_sha256=written.artifact_sha256,
        baseline_perplexity=baseline,
        accepted_perplexity=best_score,
        best_epoch=best_epoch,
        attempted_epochs=epochs,
        total_training_steps=step_count,
        validation_tokens=heldout_count,
        protected_suite_digest=(
            protected_evidence.suite_digest if protected_evidence else None
        ),
        protected_suite_passed=protected_evidence is not None,
        protected_suite_cases=(
            len(protected_evidence.cases) if protected_evidence else 0
        ),
    )


@dataclass(frozen=True, slots=True)
class OfflineComparisonReceipt:
    """Independent held-out comparison without training or model promotion."""
    baseline_model_digest: str
    candidate_model_digest: str
    tokenizer_digest: str
    validation_source_sha256: str
    validation_tokens: int
    baseline_perplexity: float
    candidate_perplexity: float
    improves: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "baseline_model_digest": self.baseline_model_digest,
            "candidate_model_digest": self.candidate_model_digest,
            "tokenizer_digest": self.tokenizer_digest,
            "validation_source_sha256": self.validation_source_sha256,
            "validation_tokens": self.validation_tokens,
            "baseline_perplexity": self.baseline_perplexity,
            "candidate_perplexity": self.candidate_perplexity,
            "improves": self.improves,
            "candidate_promoted": False,
            "independent_quality_certification": False,
        }


def compare_local_models(
    baseline: str | Path,
    candidate: str | Path,
    validation_text: str | Path,
) -> OfflineComparisonReceipt:
    """Read-only, same-tokenizer checkpoint comparison on explicit local text.

    Unlike a signed promotion certificate, this proves only bounded corpus
    perplexity for two immutable local model artifacts. Distinct checkpoint
    identities are required; neither file is modified.
    """
    parent = load_native_checkpoint(baseline)
    improved = load_native_checkpoint(candidate)
    if parent.model_digest == improved.model_digest:
        raise OfflineImprovementError("comparison requires distinct model weights")
    if parent.tokenizer_digest != improved.tokenizer_digest:
        raise OfflineImprovementError("comparison requires identical tokenizer identity")
    if parent.runtime.model.itos != improved.runtime.model.itos:
        raise OfflineImprovementError("comparison models have different vocabulary ordering")
    raw, lines, count = _read_lines(
        validation_text, label="validation",
        vocabulary=set(parent.runtime.model.stoi), minimum_tokens=MIN_HELDOUT_TOKENS,
    )
    baseline_ppl = _token_weighted_perplexity(parent.runtime.model, lines)
    candidate_ppl = _token_weighted_perplexity(improved.runtime.model, lines)
    if any(not math.isfinite(v) or v <= 0 for v in (baseline_ppl, candidate_ppl)):
        raise OfflineImprovementError("held-out comparison yielded invalid perplexity")
    return OfflineComparisonReceipt(
        baseline_model_digest=parent.model_digest,
        candidate_model_digest=improved.model_digest,
        tokenizer_digest=parent.tokenizer_digest,
        validation_source_sha256=hashlib.sha256(raw).hexdigest(),
        validation_tokens=count,
        baseline_perplexity=baseline_ppl,
        candidate_perplexity=candidate_ppl,
        improves=candidate_ppl < baseline_ppl - MIN_VALIDATION_IMPROVEMENT,
    )
