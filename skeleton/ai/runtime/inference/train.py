"""Offline builder for content-addressed local recurrent model artifacts."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
from typing import Sequence

from .artifact import load_local_model_artifact
from .neural import NumpyRecurrentLM


_MAX_CORPUS_FILES = 1_024
_MAX_CORPUS_FILE_BYTES = 16 * 1024 * 1024
_MAX_CORPUS_TOTAL_BYTES = 128 * 1024 * 1024


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
        # Blank-line blocks are independent training documents. This keeps
        # unrelated files/sections from being concatenated into false sequences.
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
) -> dict[str, object]:
    """Train, atomically write, reload, and attest one recurrent artifact."""

    documents = _read_corpus(corpus_paths)
    model = NumpyRecurrentLM.train(
        documents,
        model_id=model_id,
        hidden_size=hidden_size,
        epochs=epochs,
        learning_rate=learning_rate,
        max_vocab=max_vocab,
        max_document_tokens=max_document_tokens,
        seed=seed,
        temperature=temperature,
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
        # Validate the exact bytes that will be promoted before replacement.
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
            directory_fd = os.open(
                str(parent),
                os.O_RDONLY,
            )
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
        return {
            **final.receipt.as_dict(),
            "output_path": str(destination.resolve()),
            "training_documents": len(documents),
            "hidden_size": model.hidden_size,
            "vocab_size": model.vocab_size,
            "epochs": int(epochs),
            "seed": int(seed),
        }
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
    parser.add_argument(
        "--model-id",
        default="skeleton-local-rnn",
    )
    parser.add_argument(
        "--hidden-size",
        type=int,
        default=32,
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=4,
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.05,
    )
    parser.add_argument(
        "--max-vocab",
        type=int,
        default=4_096,
    )
    parser.add_argument(
        "--max-document-tokens",
        type=int,
        default=1_024,
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.8,
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
    "build_recurrent_artifact",
    "main",
]
