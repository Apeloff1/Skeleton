"""Offline builders for content-addressed local recurrent model artifacts.

The base builder accepts plain UTF-8 corpora and keeps the legacy Elman
architecture as its compatibility default. The multi-method builder accepts
structured TrainingExample values, compiles them through the deterministic
training-method planner, and defaults to the gated recurrent backend.

Both paths converge on one atomic artifact writer and one model identity.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
from typing import Mapping, Sequence

from .artifact import load_local_model_artifact
from .gated_neural import NumpyGatedRecurrentLM
from .neural import NumpyRecurrentLM
from .training_methods import (
    DEFAULT_TEXT_METHODS,
    MethodWeight,
    MultiMethodTrainingPlan,
    TrainingEfficiencyPolicy,
    TrainingExample,
    TrainingMethod,
    TrainingMethodError,
    compile_training_plan,
)


_MAX_CORPUS_FILES = 1_024
_MAX_CORPUS_FILE_BYTES = 16 * 1024 * 1024
_MAX_CORPUS_TOTAL_BYTES = 128 * 1024 * 1024
_MAX_LOCAL_TRAINING_DOCUMENTS = 4_096


class LocalModelBuildError(RuntimeError):
    """Offline local-model construction cannot be completed safely."""


def _read_corpus(paths: Sequence[str | Path]) -> tuple[str, ...]:
    if not paths:
        raise LocalModelBuildError("at least one corpus path is required")
    if len(paths) > _MAX_CORPUS_FILES:
        raise LocalModelBuildError("corpus file count exceeds hard limit")

    documents: list[str] = []
    total = 0
    for raw_path in paths:
        raw = str(raw_path).strip()
        if not raw:
            raise LocalModelBuildError("corpus path must be non-empty")
        path = Path(raw).expanduser()
        try:
            resolved = path.resolve(strict=True)
            stat = resolved.stat()
        except OSError as exc:
            raise LocalModelBuildError(
                f"corpus file is unavailable: {raw}"
            ) from exc
        if not resolved.is_file():
            raise LocalModelBuildError(
                f"corpus path is not a regular file: {raw}"
            )
        if stat.st_size < 1 or stat.st_size > _MAX_CORPUS_FILE_BYTES:
            raise LocalModelBuildError(
                f"corpus file is outside byte bounds: {raw}"
            )
        total += int(stat.st_size)
        if total > _MAX_CORPUS_TOTAL_BYTES:
            raise LocalModelBuildError(
                "combined corpus exceeds hard byte limit"
            )
        try:
            text = resolved.read_text(
                encoding="utf-8",
                errors="strict",
            )
        except (OSError, UnicodeDecodeError) as exc:
            raise LocalModelBuildError(
                f"corpus file must be readable UTF-8: {raw}"
            ) from exc
        if not text.strip():
            raise LocalModelBuildError(
                f"corpus file contains no text: {raw}"
            )
        blocks = tuple(
            block.strip()
            for block in text.replace("\r\n", "\n").split("\n\n")
            if block.strip()
        )
        documents.extend(blocks or (text.strip(),))

    if not documents:
        raise LocalModelBuildError("corpus produced no training documents")
    return tuple(documents)


def _stable_json_bytes(payload: object) -> bytes:
    try:
        text = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise LocalModelBuildError(
            "model artifact is not deterministic JSON"
        ) from exc
    return text.encode("utf-8")


def _train_and_write(
    *,
    documents: Sequence[str],
    output_path: str | Path,
    model_id: str,
    hidden_size: int,
    epochs: int,
    learning_rate: float,
    max_vocab: int,
    max_document_tokens: int,
    seed: int,
    temperature: float,
    early_stopping_patience: int,
    min_relative_improvement: float,
    shuffle_each_epoch: bool,
    gradient_accumulation_steps: int,
    model_architecture: str,
    extra_receipt: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Train one model and atomically promote only verified bytes."""

    rows = tuple(documents)
    if not rows:
        raise LocalModelBuildError(
            "training documents must be non-empty"
        )
    if len(rows) > _MAX_LOCAL_TRAINING_DOCUMENTS:
        raise LocalModelBuildError(
            "training document count exceeds local backend hard bound"
        )
    if any(not isinstance(item, str) or not item.strip() for item in rows):
        raise LocalModelBuildError(
            "training documents must contain non-empty text"
        )

    architecture = str(model_architecture).strip().lower()
    if architecture == "elman_recurrent":
        trainer = NumpyRecurrentLM
    elif architecture == "gated_recurrent":
        trainer = NumpyGatedRecurrentLM
    else:
        raise LocalModelBuildError(
            "model_architecture must be elman_recurrent or gated_recurrent"
        )

    model = trainer.train(
        rows,
        model_id=model_id,
        hidden_size=hidden_size,
        epochs=epochs,
        learning_rate=learning_rate,
        max_vocab=max_vocab,
        max_document_tokens=max_document_tokens,
        seed=seed,
        temperature=temperature,
        early_stopping_patience=early_stopping_patience,
        min_relative_improvement=min_relative_improvement,
        shuffle_each_epoch=shuffle_each_epoch,
        gradient_accumulation_steps=gradient_accumulation_steps,
    )
    raw = _stable_json_bytes(model.to_dict())

    raw_output = str(output_path).strip()
    if not raw_output:
        raise LocalModelBuildError("output path is required")
    destination = Path(raw_output).expanduser()
    parent = destination.parent.resolve()
    if not parent.exists() or not parent.is_dir():
        raise LocalModelBuildError(
            "output parent directory does not exist"
        )

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=destination.name + ".",
            suffix=".tmp",
            dir=str(parent),
            delete=False,
        ) as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)

        os.chmod(temp_path, 0o600)
        loaded = load_local_model_artifact(temp_path)
        if (
            loaded.receipt.model_id != model.model_id
            or loaded.receipt.model_digest != model.model_digest
        ):
            raise LocalModelBuildError(
                "post-write model identity verification failed"
            )
        os.replace(temp_path, destination)
        temp_path = None
        try:
            directory_fd = os.open(str(parent), os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

        final = load_local_model_artifact(destination)
        if final.receipt.artifact_sha256 != loaded.receipt.artifact_sha256:
            raise LocalModelBuildError(
                "promoted artifact identity changed after atomic replace"
            )
        receipt: dict[str, object] = {
            **final.receipt.as_dict(),
            "output_path": str(destination.resolve()),
            "training_documents": len(rows),
            "hidden_size": model.hidden_size,
            "vocab_size": model.vocab_size,
            "epochs": int(epochs),
            "epochs_completed": int(
                getattr(model, "training_epochs_completed", epochs)
            ),
            "stopped_early": bool(
                getattr(model, "training_stopped_early", False)
            ),
            "training_loss_history": list(
                getattr(model, "training_loss_history", ())
            ),
            "training_tokens": int(
                getattr(model, "training_tokens", 0)
            ),
            "optimizer_steps": int(
                getattr(model, "training_optimizer_steps", 0)
            ),
            "model_architecture": architecture,
            "gradient_accumulation_steps": int(
                getattr(
                    model,
                    "training_gradient_accumulation_steps",
                    gradient_accumulation_steps,
                )
            ),
            "seed": int(seed),
        }
        if extra_receipt:
            for key, value in extra_receipt.items():
                if key in receipt:
                    raise LocalModelBuildError(
                        "extra receipt cannot replace canonical field"
                    )
                receipt[str(key)] = value
        return receipt
    except OSError as exc:
        raise LocalModelBuildError(
            "model artifact could not be written atomically"
        ) from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def build_recurrent_artifact(
    *,
    corpus_paths: Sequence[str | Path],
    output_path: str | Path,
    model_id: str,
    hidden_size: int = 32,
    epochs: int = 4,
    learning_rate: float = 0.05,
    max_vocab: int = 4_096,
    max_document_tokens: int = 1_024,
    seed: int = 0,
    temperature: float = 0.8,
    early_stopping_patience: int = 0,
    min_relative_improvement: float = 0.0,
    shuffle_each_epoch: bool = True,
    gradient_accumulation_steps: int = 1,
    model_architecture: str = "elman_recurrent",
) -> dict[str, object]:
    """Train, atomically write, reload, and attest one recurrent artifact."""

    documents = _read_corpus(corpus_paths)
    return _train_and_write(
        documents=documents,
        output_path=output_path,
        model_id=model_id,
        hidden_size=hidden_size,
        epochs=epochs,
        learning_rate=learning_rate,
        max_vocab=max_vocab,
        max_document_tokens=max_document_tokens,
        seed=seed,
        temperature=temperature,
        early_stopping_patience=early_stopping_patience,
        min_relative_improvement=min_relative_improvement,
        shuffle_each_epoch=shuffle_each_epoch,
        gradient_accumulation_steps=gradient_accumulation_steps,
        model_architecture=model_architecture,
        extra_receipt={"training_mode": "plain_corpus"},
    )


def build_multi_method_recurrent_artifact(
    *,
    examples: Sequence[TrainingExample],
    output_path: str | Path,
    model_id: str,
    methods: Sequence[TrainingMethod | MethodWeight] = DEFAULT_TEXT_METHODS,
    efficiency_policy: TrainingEfficiencyPolicy | None = None,
    hidden_size: int = 32,
    epochs: int = 4,
    learning_rate: float = 0.05,
    max_vocab: int = 4_096,
    max_document_tokens: int = 1_024,
    seed: int = 0,
    temperature: float = 0.8,
    early_stopping_patience: int = 2,
    min_relative_improvement: float = 1e-4,
    shuffle_each_epoch: bool = True,
    gradient_accumulation_steps: int = 4,
    model_architecture: str = "gated_recurrent",
) -> dict[str, object]:
    """Compile multiple learning families and train one bounded local artifact."""

    try:
        plan: MultiMethodTrainingPlan = compile_training_plan(
            examples,
            methods=methods,
            policy=efficiency_policy,
        )
    except TrainingMethodError as exc:
        raise LocalModelBuildError(
            "multi-method training plan could not be compiled"
        ) from exc

    if len(plan.documents) > _MAX_LOCAL_TRAINING_DOCUMENTS:
        raise LocalModelBuildError(
            "multi-method plan exceeds local backend document limit"
        )

    return _train_and_write(
        documents=plan.corpus,
        output_path=output_path,
        model_id=model_id,
        hidden_size=hidden_size,
        epochs=epochs,
        learning_rate=learning_rate,
        max_vocab=max_vocab,
        max_document_tokens=max_document_tokens,
        seed=seed,
        temperature=temperature,
        early_stopping_patience=early_stopping_patience,
        min_relative_improvement=min_relative_improvement,
        shuffle_each_epoch=shuffle_each_epoch,
        gradient_accumulation_steps=gradient_accumulation_steps,
        model_architecture=model_architecture,
        extra_receipt={
            "training_mode": "multi_method",
            "training_plan": plan.as_dict(),
        },
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skeleton-train-local-model",
        description=(
            "Train a bounded credential-free NumPy recurrent language model "
            "and emit a validated content-addressed artifact."
        ),
    )
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        dest="inputs",
        help="UTF-8 corpus file; repeat for multiple files",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Destination JSON artifact path",
    )
    parser.add_argument("--model-id", default="skeleton-local-rnn")
    parser.add_argument("--hidden-size", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--max-vocab", type=int, default=4_096)
    parser.add_argument("--max-document-tokens", type=int, default=1_024)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument(
        "--early-stopping-patience",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--min-relative-improvement",
        type=float,
        default=0.0,
    )
    parser.add_argument(
        "--no-shuffle",
        action="store_true",
        help="Disable deterministic per-epoch sequence shuffling",
    )
    parser.add_argument(
        "--gradient-accumulation-steps",
        type=int,
        default=1,
        help="Accumulate this many document gradients per optimizer update",
    )
    parser.add_argument(
        "--architecture",
        choices=("elman_recurrent", "gated_recurrent"),
        default="elman_recurrent",
        help="Local recurrent architecture to train",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    receipt = build_recurrent_artifact(
        corpus_paths=args.inputs,
        output_path=args.output,
        model_id=args.model_id,
        hidden_size=args.hidden_size,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        max_vocab=args.max_vocab,
        max_document_tokens=args.max_document_tokens,
        seed=args.seed,
        temperature=args.temperature,
        early_stopping_patience=args.early_stopping_patience,
        min_relative_improvement=args.min_relative_improvement,
        shuffle_each_epoch=not args.no_shuffle,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        model_architecture=args.architecture,
    )
    print(
        json.dumps(
            receipt,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "LocalModelBuildError",
    "build_multi_method_recurrent_artifact",
    "build_recurrent_artifact",
    "main",
]
