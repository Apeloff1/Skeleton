"""Bounded offline native-transformer training in Skeleton's existing model plane.

This is a controlled CPU bootstrap for personal experiments, NOT foundation
model training, general intelligence, or enterprise model promotion. The
result is a genuine content-addressed checkpoint and can be served by the
canonical NativeRuntimeLocalModel after the normal integrity checks.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import stat

from skeleton.ai.model_runtime import NativeLLMRuntime
from skeleton.ai.runtime.inference.artifact import write_local_model_artifact
from skeleton.cortex.port import tokens
from skeleton.cortex.transformer import TinyTransformer
from skeleton.app.local_ai import load_native_checkpoint


MAX_CORPUS_BYTES = 32 * 1024
MAX_TRAINING_TOKENS = 512
MAX_VOCABULARY = 256
MAX_EPOCHS = 4


class OfflineTrainingError(ValueError):
    """Local training admission or checkpoint verification failed."""


@dataclass(frozen=True, slots=True)
class OfflineTrainingReceipt:
    source_sha256: str
    model_digest: str
    tokenizer_digest: str
    checkpoint_sha256: str
    vocabulary_size: int
    training_tokens: int
    training_steps: int
    epochs: int
    initial_perplexity: float
    final_perplexity: float

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "source_sha256": self.source_sha256,
            "model_digest": self.model_digest,
            "tokenizer_digest": self.tokenizer_digest,
            "checkpoint_sha256": self.checkpoint_sha256,
            "vocabulary_size": self.vocabulary_size,
            "training_tokens": self.training_tokens,
            "training_steps": self.training_steps,
            "epochs": self.epochs,
            "initial_perplexity": self.initial_perplexity,
            "final_perplexity": self.final_perplexity,
            "training_loss_improved": self.final_perplexity < self.initial_perplexity,
            "provider_credentials_required": False,
            "network_required": False,
            "foundation_model": False,
            "model_quality_certified": False,
        }


def _read_corpus(path: str | Path) -> tuple[bytes, str]:
    target = Path(path)
    try:
        identity = target.lstat()
        if not stat.S_ISREG(identity.st_mode) or identity.st_size > MAX_CORPUS_BYTES:
            raise OfflineTrainingError("training source must be a bounded regular text file")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        fd = os.open(target, flags)
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (
                opened.st_dev, opened.st_ino
            ) != (identity.st_dev, identity.st_ino):
                raise OfflineTrainingError("training source identity changed")
            if opened.st_size > MAX_CORPUS_BYTES:
                raise OfflineTrainingError("training source exceeds 32 KiB")
            data = stream.read(MAX_CORPUS_BYTES + 1)
            if len(data) != opened.st_size:
                raise OfflineTrainingError("training source changed while reading")
    except OSError as exc:
        raise OfflineTrainingError("cannot read local training source") from exc
    try:
        content = data.decode("utf-8")
    except UnicodeError as exc:
        raise OfflineTrainingError("training source must be UTF-8 text") from exc
    if not content.strip():
        raise OfflineTrainingError("training source must not be empty")
    return data, content


def train_local_text(
    source: str | Path,
    checkpoint: str | Path,
    *,
    epochs: int = 1,
    seed: int = 41,
) -> OfflineTrainingReceipt:
    """Train bounded native causal weights and verify their on-disk identity.

    Single-host CPU execution, finite token/step limits, no network, no
    arbitrary command execution, no implicit checkpoint overwrite.
    """
    if type(epochs) is not int or not 1 <= epochs <= MAX_EPOCHS:
        raise OfflineTrainingError("epochs must be in [1, 4]")
    if type(seed) is not int or not 0 <= seed <= 0xFFFFFFFF:
        raise OfflineTrainingError("seed must be a uint32")
    output = Path(checkpoint)
    if output.exists() or output.is_symlink():
        raise OfflineTrainingError("checkpoint target already exists; choose a new filename")
    source_bytes, content = _read_corpus(source)
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        raise OfflineTrainingError("training source has no usable lines")
    corpus = [line for line in lines if len(tokens(line)) >= 2]
    normalized = [token for line in corpus for token in tokens(line)]
    if not normalized or len(normalized) < 2:
        raise OfflineTrainingError("training requires at least two meaningful text tokens")
    if len(normalized) > MAX_TRAINING_TOKENS:
        raise OfflineTrainingError("training corpus exceeds 512 tokens; divide into smaller text files")
    vocabulary = tuple(sorted(set(normalized) | {"user:", "assistant:", "system:"}))
    if len(vocabulary) > MAX_VOCABULARY:
        raise OfflineTrainingError("training vocabulary exceeds 256 tokens")
    # All hyperparameters are fixed to prevent CLI resource amplification. The
    # corpus is deliberately small; this is a bootstrap, not capable foundation
    # language-model weights.
    model = TinyTransformer(
        vocab=vocabulary, dim=16, ctx=96, seed=seed, n_heads=2,
        n_layers=1, d_ff=32,
    )
    initial_perplexity = model.perplexity(corpus)
    steps = 0
    for _ in range(epochs):
        steps += model.fit(corpus, lr=0.025, schedule="cosine")
    final_perplexity = model.perplexity(corpus)
    if not math.isfinite(initial_perplexity) or not math.isfinite(final_perplexity):
        raise OfflineTrainingError("native training produced non-finite quality diagnostics")
    if steps < 1:
        raise OfflineTrainingError("training produced no gradient steps")
    native = NativeLLMRuntime(model)
    from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel

    backend = NativeRuntimeLocalModel(native)
    record = write_local_model_artifact(backend, output)
    restored = load_native_checkpoint(output)
    if (
        restored.model_digest != backend.model_digest
        or restored.tokenizer_digest != backend.tokenizer_digest
    ):
        raise OfflineTrainingError("trained native model checkpoint failed identity round-trip")
    return OfflineTrainingReceipt(
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        model_digest=restored.model_digest,
        tokenizer_digest=restored.tokenizer_digest,
        checkpoint_sha256=record.artifact_sha256,
        vocabulary_size=len(vocabulary),
        training_tokens=len(normalized),
        training_steps=steps,
        epochs=epochs,
        initial_perplexity=initial_perplexity,
        final_perplexity=final_perplexity,
    )
