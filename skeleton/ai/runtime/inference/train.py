"""Credential-free local model training CLI.

The CLI intentionally trains only the native deterministic NumPy recurrent
baseline. It creates content-addressed artifacts that can be reloaded through
Skeleton's existing local inference contract without provider credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

from .artifact import (
    LocalModelArtifactError,
    write_local_model_artifact,
)
from .neural import NeuralLMConfig, NeuralLMError, NumpyRecurrentLM


class LocalModelBuildError(RuntimeError):
    """A local model candidate could not be built reproducibly."""


def _read_corpus(paths: Sequence[str | Path]) -> tuple[str, ...]:
    documents: list[str] = []
    seen: set[Path] = set()
    for raw in paths:
        path = Path(raw).expanduser()
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise LocalModelBuildError(f"corpus file unavailable: {path}") from exc
        if resolved in seen:
            raise LocalModelBuildError("duplicate corpus path")
        seen.add(resolved)
        if resolved.is_symlink() or not resolved.is_file():
            raise LocalModelBuildError("corpus inputs must be regular files")
        try:
            text = resolved.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError) as exc:
            raise LocalModelBuildError(
                "corpus inputs must be readable UTF-8 text"
            ) from exc
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            raise LocalModelBuildError("corpus documents must be non-empty")
        documents.append(normalized)
    if not documents:
        raise LocalModelBuildError("at least one corpus path is required")
    return tuple(documents)


def build_recurrent_artifact(
    *,
    corpus_paths: Sequence[str | Path],
    output_path: str | Path,
    model_id: str,
    hidden_size: int = 48,
    epochs: int = 8,
    learning_rate: float = 0.05,
    seed: int = 0,
    gradient_clip: float = 1.0,
) -> dict[str, object]:
    documents = _read_corpus(corpus_paths)
    try:
        model = NumpyRecurrentLM(
            model_id=model_id,
            config=NeuralLMConfig(hidden_size=hidden_size, seed=seed),
        )
        training = model.train(
            documents,
            epochs=epochs,
            learning_rate=learning_rate,
            gradient_clip=gradient_clip,
        )
        artifact = write_local_model_artifact(model, output_path)
    except (NeuralLMError, LocalModelArtifactError, ValueError, TypeError) as exc:
        raise LocalModelBuildError("native local model build failed") from exc

    corpus_identity = hashlib.sha256(
        json.dumps(
            list(documents),
            sort_keys=False,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "skeleton.local_model_build.v1",
        "model_id": model.model_id,
        "model_digest": model.model_digest,
        "artifact_sha256": artifact.artifact_sha256,
        "artifact_bytes": artifact.artifact_bytes,
        "artifact_reference": artifact.reference,
        "artifact_schema": artifact.schema,
        "output_path": str(Path(output_path).expanduser().resolve(strict=True)),
        "corpus_digest": corpus_identity,
        "document_count": len(documents),
        "hidden_size": hidden_size,
        "seed": seed,
        "epochs": epochs,
        "learning_rate": float(learning_rate),
        "gradient_clip": float(gradient_clip),
        "initial_loss": training.initial_loss,
        "final_loss": training.final_loss,
        "training_receipt_digest": training.digest,
        "credential_free": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skeleton-train-local-model",
        description="Train a deterministic credential-free local recurrent model.",
    )
    parser.add_argument("corpus", nargs="+", help="UTF-8 corpus file(s)")
    parser.add_argument("--output", required=True, help="Artifact JSON output path")
    parser.add_argument("--model-id", default="skeleton-native-local-v1")
    parser.add_argument("--hidden-size", type=int, default=48)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--gradient-clip", type=float, default=1.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    receipt = build_recurrent_artifact(
        corpus_paths=args.corpus,
        output_path=args.output,
        model_id=args.model_id,
        hidden_size=args.hidden_size,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        seed=args.seed,
        gradient_clip=args.gradient_clip,
    )
    print(json.dumps(receipt, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "LocalModelBuildError",
    "build_recurrent_artifact",
    "main",
]
