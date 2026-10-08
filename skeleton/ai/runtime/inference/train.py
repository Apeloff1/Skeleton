"""Credential-free local model training CLI.

The builder supports both the existing deterministic NumPy recurrent baseline
and Skeleton's native causal transformer.  Native-transformer builds are
candidate-only: they require explicit dataset-rights evidence, emit FLGB-07
lineage, and never grant production promotion authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

from skeleton.ai.training.native_transformer import (
    NativeTrainingError,
    NativeTransformerTrainingConfig,
    governed_dataset,
    train_native_transformer_candidate,
)

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
        if path.is_symlink():
            raise LocalModelBuildError("corpus input symlink is forbidden")
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise LocalModelBuildError(f"corpus file unavailable: {path}") from exc
        if resolved in seen:
            raise LocalModelBuildError("duplicate corpus path")
        seen.add(resolved)
        if not resolved.is_file():
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
        "runtime_kind": "numpy-recurrent",
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


def build_native_transformer_artifact(
    *,
    corpus_paths: Sequence[str | Path],
    output_path: str | Path,
    candidate_id: str,
    dataset_id: str,
    source_id: str,
    rights_evidence_digest: str,
    license_id: str | None = None,
    dim: int = 16,
    context: int = 64,
    heads: int = 2,
    layers: int = 2,
    feed_forward: int = 32,
    norm: str = "rms",
    ffn_kind: str = "swiglu",
    bpe_merges: int = 96,
    epochs: int = 1,
    learning_rate: float = 0.02,
    schedule: str = "cosine",
    seed: int = 0,
    max_steps: int = 1_000_000,
    implementation_digest: str | None = None,
) -> dict[str, object]:
    documents = _read_corpus(corpus_paths)
    try:
        dataset = governed_dataset(
            dataset_id=dataset_id,
            source_id=source_id,
            documents=documents,
            rights_evidence_digest=rights_evidence_digest,
            license_id=license_id,
        )
        config = NativeTransformerTrainingConfig(
            dim=dim,
            context=context,
            heads=heads,
            layers=layers,
            feed_forward=feed_forward,
            norm=norm,
            ffn_kind=ffn_kind,
            bpe_merges=bpe_merges,
            epochs=epochs,
            learning_rate=learning_rate,
            schedule=schedule,
            seed=seed,
            max_steps=max_steps,
        )
        receipt = train_native_transformer_candidate(
            dataset=dataset,
            output_path=output_path,
            candidate_id=candidate_id,
            config=config,
            implementation_digest=implementation_digest,
        )
    except (
        NativeTrainingError,
        LocalModelArtifactError,
        ValueError,
        TypeError,
    ) as exc:
        raise LocalModelBuildError("native transformer candidate build failed") from exc

    value: dict[str, object] = receipt.to_dict()
    value.update(
        {
            "schema_version": "skeleton.local_model_build.v2",
            "runtime_kind": "native-transformer",
            "model_id": "skeleton-native-transformer",
            "model_digest": receipt.trained_model_digest,
            "artifact_schema": "skeleton.ai.native-llm-runtime.v2",
            "output_path": str(
                Path(output_path).expanduser().resolve(strict=True)
            ),
            "corpus_digest": dataset.revision.content_digest,
            "rights_digest": dataset.rights.digest,
            "credential_free": True,
            "candidate_only": True,
        }
    )
    value["training_receipt_digest"] = receipt.digest
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skeleton-train-local-model",
        description=(
            "Train a deterministic credential-free local model candidate. "
            "Native transformers require explicit rights evidence."
        ),
    )
    parser.add_argument("corpus", nargs="+", help="UTF-8 corpus file(s)")
    parser.add_argument("--output", required=True, help="Artifact JSON output path")
    parser.add_argument(
        "--runtime",
        choices=("recurrent", "native-transformer"),
        default="recurrent",
    )
    parser.add_argument("--model-id", default="skeleton-native-local-v1")
    parser.add_argument("--hidden-size", type=int, default=48)
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--learning-rate", type=float)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--gradient-clip", type=float, default=1.0)

    parser.add_argument("--dataset-id")
    parser.add_argument("--source-id")
    parser.add_argument("--rights-evidence-digest")
    parser.add_argument("--license-id")
    parser.add_argument("--dim", type=int, default=16)
    parser.add_argument("--context", type=int, default=64)
    parser.add_argument("--heads", type=int, default=2)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--feed-forward", type=int, default=32)
    parser.add_argument("--norm", choices=("ln", "rms"), default="rms")
    parser.add_argument("--ffn-kind", choices=("gelu", "swiglu"), default="swiglu")
    parser.add_argument("--bpe-merges", type=int, default=96)
    parser.add_argument("--schedule", choices=("const", "cosine"), default="cosine")
    parser.add_argument("--max-steps", type=int, default=1_000_000)
    parser.add_argument("--implementation-digest")
    return parser


def _require_native_cli_value(value: str | None, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LocalModelBuildError(
            f"{name} is required for --runtime native-transformer"
        )
    return value.strip()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.runtime == "native-transformer":
        receipt = build_native_transformer_artifact(
            corpus_paths=args.corpus,
            output_path=args.output,
            candidate_id=args.model_id,
            dataset_id=_require_native_cli_value(args.dataset_id, "--dataset-id"),
            source_id=_require_native_cli_value(args.source_id, "--source-id"),
            rights_evidence_digest=_require_native_cli_value(
                args.rights_evidence_digest,
                "--rights-evidence-digest",
            ),
            license_id=args.license_id,
            dim=args.dim,
            context=args.context,
            heads=args.heads,
            layers=args.layers,
            feed_forward=args.feed_forward,
            norm=args.norm,
            ffn_kind=args.ffn_kind,
            bpe_merges=args.bpe_merges,
            epochs=1 if args.epochs is None else args.epochs,
            learning_rate=(
                0.02 if args.learning_rate is None else args.learning_rate
            ),
            schedule=args.schedule,
            seed=args.seed,
            max_steps=args.max_steps,
            implementation_digest=args.implementation_digest,
        )
    else:
        receipt = build_recurrent_artifact(
            corpus_paths=args.corpus,
            output_path=args.output,
            model_id=args.model_id,
            hidden_size=args.hidden_size,
            epochs=8 if args.epochs is None else args.epochs,
            learning_rate=(
                0.05 if args.learning_rate is None else args.learning_rate
            ),
            seed=args.seed,
            gradient_clip=args.gradient_clip,
        )
    print(json.dumps(receipt, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "LocalModelBuildError",
    "build_native_transformer_artifact",
    "build_recurrent_artifact",
    "main",
]
