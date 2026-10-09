"""Deterministic, offline preparation of small native-transformer training datasets.

This is an application-level corpus projection, not a crawler, data-governance
authority, background trainer, network downloader or model-promotion plane.
Each source is an explicitly selected regular UTF-8 text file in one bounded
directory. Document-level split prevents neighbouring lines from the same
source silently crossing the training/held-out boundary. Output is guarded
by an identity-bound manifest published only when all files are complete.

Native CPU training is deliberately small, so produced text artifacts must
fit the *actual* trainer's token and byte budgets, not an arbitrary claim of
massive dataset capacity.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any

from skeleton.app.local_ai_training import MAX_CORPUS_BYTES, MAX_TRAINING_TOKENS
from skeleton.cortex.port import tokens

DATASET_SCHEMA = "skeleton.ai.native_dataset.v1"
MAX_SOURCE_FILES = 32
MAX_SOURCE_LINES = 512
MAX_TOTAL_SOURCE_BYTES = 256 * 1024
MAX_VALIDATION_TOKENS = 512
TRAIN_FILE = "train.txt"
VALIDATION_FILE = "validation.txt"
MANIFEST_FILE = "dataset.json"


class OfflineDatasetError(ValueError):
    """Native dataset source admission, splitting or publication failed."""


@dataclass(frozen=True, slots=True)
class SourceDocument:
    name: str
    data: bytes
    lines: tuple[str, ...]
    line_tokens: tuple[tuple[str, ...], ...]
    token_count: int
    sha256: str
    device: int
    inode: int


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(data: object) -> bytes:
    return json.dumps(
        data, sort_keys=True, ensure_ascii=False, allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _read_document(path: Path) -> SourceDocument:
    if not path.name.lower().endswith(".txt"):
        raise OfflineDatasetError("only .txt source files are admitted")
    try:
        observed = path.lstat()
        if not stat.S_ISREG(observed.st_mode) or not 1 <= observed.st_size <= MAX_CORPUS_BYTES:
            raise OfflineDatasetError("source must be a bounded regular text file")
        fd = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_BINARY", 0),
        )
        with os.fdopen(fd, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (observed.st_dev, observed.st_ino)
                or opened.st_size != observed.st_size
            ):
                raise OfflineDatasetError("source changed during secure open")
            raw = handle.read(MAX_CORPUS_BYTES + 1)
            if (
                len(raw) != opened.st_size
                or os.fstat(handle.fileno()).st_size != opened.st_size
            ):
                raise OfflineDatasetError("source changed during read")
    except OSError as exc:
        raise OfflineDatasetError("could not read selected local source") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise OfflineDatasetError("source must contain UTF-8 text") from exc
    lines = tuple(line.strip() for line in text.splitlines() if line.strip())
    if not lines:
        raise OfflineDatasetError("source contains no usable text lines")
    normalized = tuple(tuple(tokens(line)) for line in lines)
    if any(len(sequence) < 2 for sequence in normalized):
        raise OfflineDatasetError("each selected line must contain at least two native tokens")
    return SourceDocument(
        name=path.name,
        data=raw,
        lines=lines,
        line_tokens=normalized,
        token_count=sum(len(line) for line in normalized),
        sha256=_digest(raw),
        device=observed.st_dev,
        inode=observed.st_ino,
    )


def _check_cross_partition_overlap(
    trained: tuple[SourceDocument, ...],
    evaluated: tuple[SourceDocument, ...],
) -> None:
    # The same normalization and contiguous-fragment rule is enforced by
    # improve_local_model. This checks it *before* publishing any dataset.
    train = [line for doc in trained for line in doc.line_tokens]
    holdout = [line for doc in evaluated for line in doc.line_tokens]

    def contains(haystack: tuple[str, ...], needle: tuple[str, ...]) -> bool:
        if len(needle) < 3 or len(haystack) < len(needle):
            return False
        return any(
            haystack[offset:offset + len(needle)] == needle
            for offset in range(len(haystack) - len(needle) + 1)
        )

    for left in train:
        for right in holdout:
            if left == right or contains(left, right) or contains(right, left):
                raise OfflineDatasetError(
                    "training and validation contain duplicate normalized passages"
                )


def _scan_sources(root: Path) -> tuple[SourceDocument, ...]:
    try:
        identity = root.lstat()
        if not stat.S_ISDIR(identity.st_mode):
            raise OfflineDatasetError("source root must be an existing real directory")
        entries = list(root.iterdir())
    except OSError as exc:
        raise OfflineDatasetError("cannot inspect selected source directory") from exc
    if not 2 <= len(entries) <= MAX_SOURCE_FILES:
        raise OfflineDatasetError("source directory requires 2-32 flat .txt files")
    if any(not entry.name.lower().endswith(".txt") for entry in entries):
        raise OfflineDatasetError("source root must contain only flat .txt documents")
    sources = tuple(
        sorted((_read_document(entry) for entry in entries), key=lambda x: x.name.casefold())
    )
    if len({s.name.casefold() for s in sources}) != len(sources):
        raise OfflineDatasetError("source filenames collide on case-insensitive systems")
    if len({(s.device, s.inode) for s in sources}) != len(sources):
        raise OfflineDatasetError("source entries share the same underlying file")
    if len({s.sha256 for s in sources}) != len(sources):
        raise OfflineDatasetError("duplicate source content is not independent evidence")
    if sum(len(s.data) for s in sources) > MAX_TOTAL_SOURCE_BYTES:
        raise OfflineDatasetError("sources exceed bounded aggregate input budget")
    if sum(len(s.lines) for s in sources) > MAX_SOURCE_LINES:
        raise OfflineDatasetError("sources exceed bounded aggregate line budget")
    normalized = set()
    for s in sources:
        for line in s.line_tokens:
            if line in normalized:
                raise OfflineDatasetError("duplicate normalized training content across files")
            normalized.add(line)
    return sources


def _write_exclusive(path: Path, data: bytes) -> None:
    if not data:
        raise OfflineDatasetError("dataset output must not be empty")
    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
        0o600,
    )
    created = os.fstat(fd)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        # A short/failed write can occur before the caller records the path
        # as published. Only unlink the exact inode this invocation created,
        # never a file substituted at that name by a competing writer.
        try:
            current = path.lstat()
            if (
                current.st_dev == created.st_dev
                and current.st_ino == created.st_ino
                and stat.S_ISREG(current.st_mode)
            ):
                path.unlink()
        except OSError:
            pass
        raise


def prepare_native_dataset(
    source_directory: str | Path,
    output_directory: str | Path,
    *,
    validation_percent: int = 25,
    seed: int = 41,
) -> dict[str, Any]:
    """Publish deterministic, disjoint, hash-bound training and validation.

    The destination must not exist and be outside the selected source root.
    The manifest is the final commit marker. Files are never silently
    overwritten; on failure, only this invocation's newly created files are
    cleaned up.
    """
    if type(seed) is not int or not 0 <= seed <= 0xFFFFFFFF:
        raise OfflineDatasetError("split seed must be uint32")
    if (
        type(validation_percent) is not int
        or not 10 <= validation_percent <= 50
    ):
        raise OfflineDatasetError("validation percent must be between 10 and 50")

    source_root = Path(source_directory)
    destination = Path(output_directory)
    if destination.exists() or destination.is_symlink():
        raise OfflineDatasetError("dataset output directory must not exist")
    if not destination.parent.is_dir():
        raise OfflineDatasetError("dataset output parent directory must exist")
    if destination.parent.resolve() == source_root.resolve():
        raise OfflineDatasetError("output may not be created inside the source directory")

    sources = _scan_sources(source_root)
    source_identity = {
        doc.name: (doc.device, doc.inode, doc.sha256)
        for doc in sources
    }
    ranking = sorted(
        sources,
        key=lambda doc: (
            _digest(
                f"{seed}:{doc.name.casefold()}:{doc.sha256}".encode("utf-8")
            ),
            doc.name.casefold(),
        ),
    )
    validation_count = max(
        1, min(len(ranking) - 1, (len(ranking) * validation_percent + 99) // 100),
    )
    evaluation = tuple(sorted(ranking[:validation_count], key=lambda d: d.name.casefold()))
    training = tuple(sorted(ranking[validation_count:], key=lambda d: d.name.casefold()))
    _check_cross_partition_overlap(training, evaluation)

    training_tokens = sum(doc.token_count for doc in training)
    validation_tokens = sum(doc.token_count for doc in evaluation)
    if not 2 <= training_tokens <= MAX_TRAINING_TOKENS:
        raise OfflineDatasetError("prepared training tokens exceed native CPU trainer budget")
    if not 4 <= validation_tokens <= MAX_VALIDATION_TOKENS:
        raise OfflineDatasetError("prepared validation tokens exceed held-out budget")

    def serialize(documents: tuple[SourceDocument, ...]) -> bytes:
        # This newline-preserving shape is the actual data fed to the
        # existing native CPU trainer (no fabricated / synthetic examples).
        return ("\n".join(line for doc in documents for line in doc.lines) + "\n").encode("utf-8")

    train_blob = serialize(training)
    validation_blob = serialize(evaluation)
    if (
        len(train_blob) > MAX_CORPUS_BYTES
        or len(validation_blob) > MAX_CORPUS_BYTES
    ):
        raise OfflineDatasetError("prepared dataset exceeds native text loader byte limits")
    metadata: dict[str, Any] = {
        "schema": DATASET_SCHEMA,
        "split_seed": seed,
        "validation_percent": validation_percent,
        "sources": [
            {
                "name": doc.name,
                "source_sha256": doc.sha256,
                "normalized_line_count": len(doc.lines),
                "token_count": doc.token_count,
                "partition": "validation" if doc in evaluation else "training",
            }
            for doc in sources
        ],
        "training": {
            "filename": TRAIN_FILE,
            "sha256": _digest(train_blob),
            "token_count": training_tokens,
            "source_count": len(training),
        },
        "validation": {
            "filename": VALIDATION_FILE,
            "sha256": _digest(validation_blob),
            "token_count": validation_tokens,
            "source_count": len(evaluation),
        },
        "operator_selected": True,
        "network_used": False,
        "model_quality_certified": False,
        "historical_data_disjointness_proven": False,
    }
    metadata["dataset_id"] = _digest(_canonical(metadata))
    output_manifest = _canonical(metadata) + b"\n"

    # Check every original again before first publication; the manifest
    # must never certify a source that changed while being prepared.
    for source in sources:
        reread = _read_document(source_root / source.name)
        if (
            (reread.device, reread.inode, reread.sha256)
            != source_identity[source.name]
        ):
            raise OfflineDatasetError("source changed during dataset preparation")

    created = False
    published: list[Path] = []
    try:
        destination.mkdir(mode=0o700, parents=False, exist_ok=False)
        created = True
        for filename, blob in (
            (TRAIN_FILE, train_blob),
            (VALIDATION_FILE, validation_blob),
            (MANIFEST_FILE, output_manifest),  # final commit marker
        ):
            target = destination / filename
            _write_exclusive(target, blob)
            published.append(target)
    except FileExistsError as exc:
        raise OfflineDatasetError("dataset destination claimed concurrently") from exc
    except OSError as exc:
        raise OfflineDatasetError("could not publish native dataset safely") from exc
    finally:
        if created and len(published) < 3:
            # Never unlink a file not created by this call; a competitor's
            # publication or user data is not ours to remove.
            for target in reversed(published):
                try:
                    target.unlink()
                except OSError:
                    pass
            try:
                destination.rmdir()
            except OSError:
                pass
    return {
        "schema": DATASET_SCHEMA,
        "dataset_id": metadata["dataset_id"],
        "source_count": len(sources),
        "training_sources": len(training),
        "validation_sources": len(evaluation),
        "training_tokens": training_tokens,
        "validation_tokens": validation_tokens,
        "training_sha256": metadata["training"]["sha256"],
        "validation_sha256": metadata["validation"]["sha256"],
        "manifest_sha256": _digest(output_manifest),
        "output_directory": str(destination),
        "train_file": str(destination / TRAIN_FILE),
        "validation_file": str(destination / VALIDATION_FILE),
        "manifest_file": str(destination / MANIFEST_FILE),
        "disjoint_document_split": True,
        "model_quality_certified": False,
    }
