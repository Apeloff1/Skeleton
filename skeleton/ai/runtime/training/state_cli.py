"""Inspect, archive and recover the existing governed local training state."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import stat
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from skeleton.storage.cas import GovernedContentStore

from .checkpoint_archive import CheckpointArchiveReceipt, TrainingCheckpointArchive
from .control import TrainingRepository, TrainingStateError, _canonical
from .data import DatasetRegistry

MAX_RECEIPT_BYTES = 65536


class GovernedTrainingStateError(TrainingStateError):
    """The operator request cannot safely access the existing state authority."""


def _safe_path(value: str | Path, *, existing: bool = False) -> Path:
    path = Path(value).expanduser().absolute()
    for component in reversed((path, *path.parents)):
        try:
            info = component.lstat()
        except FileNotFoundError:
            if component != path or existing:
                raise GovernedTrainingStateError("state path or parent does not exist") from None
            continue
        if stat.S_ISLNK(info.st_mode):
            raise GovernedTrainingStateError("state paths must not contain symlinks")
        if component != path and not stat.S_ISDIR(info.st_mode):
            raise GovernedTrainingStateError("state path parent must be a directory")
        if component == path and not stat.S_ISREG(info.st_mode):
            raise GovernedTrainingStateError("state inputs must be regular files")
    return path.resolve()


def _paths(
    state_directory: str | Path,
    *,
    recovery: bool = False,
    cas_path: str | Path | None = None,
    receipt_path: str | Path | None = None,
    receipt_exists: bool = False,
) -> tuple[Path, Path, Path | None, Path | None]:
    directory = Path(state_directory).expanduser().absolute()
    dataset = _safe_path(directory / "datasets.sqlite3", existing=True)
    training = _safe_path(directory / "training.sqlite3", existing=not recovery)
    cas = _safe_path(cas_path, existing=recovery) if cas_path is not None else None
    receipt = _safe_path(receipt_path, existing=receipt_exists) if receipt_path is not None else None
    primary = [dataset, training, *([cas] if cas is not None else [])]
    protected = {Path(str(path) + suffix) for path in primary for suffix in ("", "-wal", "-shm", "-journal")}
    if len(set(primary)) != len(primary) or (receipt is not None and receipt in protected):
        raise GovernedTrainingStateError("database and receipt paths must be distinct")
    candidates = sorted(protected | ({receipt} if receipt is not None else set()))
    present = []
    for path in candidates:
        if path.exists() or path.is_symlink():
            _safe_path(path, existing=True)
            present.append(path)
    for index, path in enumerate(present):
        if any(path.samefile(other) for other in present[index + 1 :]):
            raise GovernedTrainingStateError("database and receipt file identities must be distinct")
    return dataset, training, cas, receipt


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GovernedTrainingStateError("duplicate archive receipt field")
        result[key] = value
    return result


def _read_receipt(path: Path) -> CheckpointArchiveReceipt:
    before = path.stat()
    if not 0 < before.st_size <= MAX_RECEIPT_BYTES:
        raise GovernedTrainingStateError("archive receipt exceeds byte bounds")
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            before.st_dev,
            before.st_ino,
        ):
            raise GovernedTrainingStateError("archive receipt changed before reading")
        data = handle.read(MAX_RECEIPT_BYTES + 1)
        after = os.fstat(handle.fileno())
    signature = lambda value: (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )
    if (
        len(data) != before.st_size
        or signature(before) != signature(after)
        or signature(before) != signature(path.stat())
    ):
        raise GovernedTrainingStateError("archive receipt changed while reading")

    def invalid_constant(value):
        raise GovernedTrainingStateError("archive receipt contains nonfinite JSON")

    try:
        value = json.loads(data, object_pairs_hook=_object, parse_constant=invalid_constant)
        if not isinstance(value, dict):
            raise TypeError("receipt must contain an object")
        return CheckpointArchiveReceipt.from_dict(value)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise GovernedTrainingStateError("invalid archive receipt") from exc


def _write_receipt(path: Path, receipt: CheckpointArchiveReceipt) -> None:
    encoded = (_canonical(receipt.as_dict()) + "\n").encode("utf-8")
    if len(encoded) > MAX_RECEIPT_BYTES:
        raise GovernedTrainingStateError("archive receipt exceeds byte bounds")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".training-receipt-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def inspect_training_state(
    *,
    state_directory: str | Path,
    run_id: str,
    now: datetime | None = None,
    stall_seconds: float = 300,
    max_points: int = 128,
) -> dict:
    """Return a bounded validated snapshot, without exposing source text or weights."""
    from .observability import TrainingObserver

    dataset_path, training_path, _, _ = _paths(state_directory)
    datasets = DatasetRegistry(dataset_path)
    runs = None
    try:
        runs = TrainingRepository(training_path)
        return (
            TrainingObserver(runs, datasets)
            .snapshot(
                run_id,
                now=now if now is not None else datetime.now(UTC),
                stall_seconds=stall_seconds,
                max_points=max_points,
            )
            .as_dict()
        )
    finally:
        if runs is not None:
            runs.close()
        datasets.close()


def archive_training_state(
    *,
    state_directory: str | Path,
    run_id: str,
    cas_path: str | Path,
    receipt_output: str | Path,
    tenant_id: str,
    trust_context: str,
) -> dict:
    dataset_path, training_path, store_path, output = _paths(
        state_directory, cas_path=cas_path, receipt_path=receipt_output
    )
    datasets = DatasetRegistry(dataset_path)
    runs = store = None
    try:
        runs = TrainingRepository(training_path)
        store = GovernedContentStore(str(store_path))
        manifest = runs.manifest(run_id)
        corpus = datasets.training_corpus(manifest.dataset_digest)
        receipt = TrainingCheckpointArchive(
            runs, store, tenant_id=tenant_id, trust_context=trust_context
        ).backup(run_id, datasets, corpus)
        _write_receipt(output, receipt)
        return {
            "run_id": run_id,
            "dataset_digest": manifest.dataset_digest,
            "checkpoint_digest": receipt.checkpoint_digest,
            "archive_receipt_digest": receipt.digest,
            "receipt_output": str(output),
        }
    finally:
        if store is not None:
            store.close()
        if runs is not None:
            runs.close()
        datasets.close()


def recover_training_state(
    *,
    state_directory: str | Path,
    dataset_digest: str,
    cas_path: str | Path,
    receipt_path: str | Path,
    tenant_id: str,
    trust_context: str,
) -> dict:
    dataset_path, training_path, store_path, receipt_input = _paths(
        state_directory, recovery=True, cas_path=cas_path, receipt_path=receipt_path, receipt_exists=True
    )
    receipt = _read_receipt(receipt_input)
    datasets = DatasetRegistry(dataset_path)
    runs = store = None
    try:
        corpus = datasets.training_corpus(dataset_digest)
        runs = TrainingRepository(training_path)
        store = GovernedContentStore(str(store_path))
        archive = TrainingCheckpointArchive(runs, store, tenant_id=tenant_id, trust_context=trust_context)
        contents = archive.verify_backup(receipt, datasets, corpus)
        if contents.manifest.dataset_digest != dataset_digest:
            raise GovernedTrainingStateError("recovery dataset identity mismatch")
        runs.register_run(contents.manifest, datasets)
        runs.bind_execution(contents.manifest.run_id, contents.binding)
        checkpoint = archive.restore(receipt, datasets, corpus)
        return {
            "run_id": contents.manifest.run_id,
            "dataset_digest": dataset_digest,
            "checkpoint_digest": checkpoint.digest,
            "state": runs.state(contents.manifest.run_id),
            "worker_epoch": runs._epoch(contents.manifest.run_id),
            "archive_receipt_digest": receipt.digest,
        }
    finally:
        if store is not None:
            store.close()
        if runs is not None:
            runs.close()
        datasets.close()


def retain_training_state(
    *,
    state_directory: str | Path,
    run_id: str,
    cas_path: str | Path,
    tenant_id: str,
    trust_context: str,
    keep_newest: int = 2,
) -> dict:
    dataset_path, training_path, store_path, _ = _paths(state_directory, cas_path=cas_path)
    datasets = DatasetRegistry(dataset_path)
    runs = store = None
    try:
        runs = TrainingRepository(training_path)
        store = GovernedContentStore(str(store_path))
        manifest = runs.manifest(run_id)
        # Retention cannot silently operate on a withdrawn source authority.
        datasets.require_training_ready(manifest.dataset_digest)
        removed = TrainingCheckpointArchive(
            runs, store, tenant_id=tenant_id, trust_context=trust_context
        ).retain(run_id, keep_newest=keep_newest)
        return {
            "run_id": run_id,
            "removed_checkpoint_digests": list(removed),
            "keep_newest": keep_newest,
            "cas_blobs_retained": True,
        }
    finally:
        if store is not None:
            store.close()
        if runs is not None:
            runs.close()
        datasets.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skeleton-governed-training-state", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "archive", "recover", "retain"):
        command = commands.add_parser(name)
        command.add_argument("--state-directory", required=True)
        if name != "recover":
            command.add_argument("--run-id", required=True)
        if name == "inspect":
            command.add_argument("--stall-seconds", type=float, default=300)
            command.add_argument("--max-points", type=int, default=128)
        else:
            command.add_argument("--cas-path", required=True)
            command.add_argument("--tenant-id", required=True)
            command.add_argument("--trust-context", required=True)
        if name == "archive":
            command.add_argument("--receipt-output", required=True)
        elif name == "recover":
            command.add_argument("--dataset-digest", required=True)
            command.add_argument("--receipt-path", required=True)
        elif name == "retain":
            command.add_argument("--keep-newest", type=int, default=2)
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    handlers = {
        "inspect": inspect_training_state,
        "archive": archive_training_state,
        "recover": recover_training_state,
        "retain": retain_training_state,
    }
    try:
        result = handlers[command](**args)
    except (TrainingStateError, ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(2, f"{parser.prog}: {exc}\n")
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
