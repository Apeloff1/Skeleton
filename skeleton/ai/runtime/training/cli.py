"""Run bounded, durable local training from observed and rights-bound bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import sqlite3
import stat
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from skeleton.ai.runtime.inference.artifact import (
    LocalModelArtifactError,
    write_local_model_artifact,
)

from .control import (
    TrainingRepository,
    TrainingRunManifest,
    TrainingStateError,
    _canonical,
    _digest,
)
from .data import DatasetRegistry, IngestEnvelope, MaterializedTrainingSource
from .trainer import ReferenceLocalTrainer, _step_count


class GovernedTrainingBuildError(RuntimeError):
    """An operator input cannot be admitted as a governed local training run."""


def _read_sources(paths: Sequence[str | Path], *, neural: bool) -> tuple[tuple[Path, bytes], ...]:
    if not paths or len(paths) > 4096:
        raise GovernedTrainingBuildError("corpus must contain between 1 and 4096 files")
    document_limit = 4096 if neural else 1024 * 1024
    corpus_limit = 1024 * 1024 if neural else 64 * 1024 * 1024
    sources: list[tuple[Path, bytes]] = []
    seen: set[tuple[int, int]] = set()
    total = 0
    for raw_path in paths:
        path = Path(raw_path).expanduser().absolute()
        try:
            for component in reversed((path, *path.parents)):
                info = component.lstat()
                if stat.S_ISLNK(info.st_mode):
                    raise GovernedTrainingBuildError("corpus symlinks are forbidden")
                if component != path and not stat.S_ISDIR(info.st_mode):
                    raise GovernedTrainingBuildError("corpus parent must be a directory")
            named_before = info
            if not stat.S_ISREG(named_before.st_mode):
                raise GovernedTrainingBuildError("corpus inputs must be regular files")
            if not 1 <= named_before.st_size <= document_limit:
                raise GovernedTrainingBuildError("corpus document violates byte bounds")
            descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as handle:
                before = os.fstat(handle.fileno())
                signature = lambda value: (
                    value.st_dev,
                    value.st_ino,
                    value.st_size,
                    value.st_mtime_ns,
                    value.st_ctime_ns,
                )
                if signature(before) != signature(named_before):
                    raise GovernedTrainingBuildError("corpus input changed before reading")
                if not stat.S_ISREG(before.st_mode):
                    raise GovernedTrainingBuildError("corpus inputs must be regular files")
                identity = (before.st_dev, before.st_ino)
                if identity in seen:
                    raise GovernedTrainingBuildError("duplicate corpus file identity")
                seen.add(identity)
                if not 1 <= before.st_size <= document_limit:
                    raise GovernedTrainingBuildError("corpus document violates byte bounds")
                payload = handle.read(document_limit + 1)
                after = os.fstat(handle.fileno())
            if (
                len(payload) != before.st_size
                or signature(before) != signature(after)
                or signature(before) != signature(path.lstat())
            ):
                raise GovernedTrainingBuildError("corpus input changed while reading")
            if len(payload) > document_limit:
                raise GovernedTrainingBuildError("corpus document violates byte bounds")
            text = payload.decode("utf-8", errors="strict")
        except (OSError, UnicodeDecodeError) as exc:
            raise GovernedTrainingBuildError("corpus must be readable regular UTF-8 files") from exc
        if not text.strip():
            raise GovernedTrainingBuildError("corpus documents must be non-empty")
        total += len(payload)
        if total > corpus_limit:
            raise GovernedTrainingBuildError("corpus violates total byte bound")
        sources.append((path, payload))
    if total + len(sources) - 1 > corpus_limit:
        raise GovernedTrainingBuildError("corpus violates total byte bound")
    return tuple(sources)


def _code_digest(algorithm: str) -> str:
    root = Path(__file__).parent
    paths = [root / name for name in ("cli.py", "control.py", "data.py", "trainer.py")]
    paths.append(root.parent / "inference" / "local.py")
    if algorithm in {"neural", "data_parallel"}:
        paths += [root / "neural_trainer.py", root.parent / "inference" / "neural.py"]
    if algorithm == "data_parallel":
        paths.append(root / "distributed_trainer.py")
    return _digest(
        {str(path.relative_to(root.parent)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    )


def _admit_request(
    path: Path, run_id: str, request: dict[str, object], *, expected_version: int
) -> tuple[str, int]:
    encoded = _canonical(request)
    if len(encoded.encode("utf-8")) > 1024 * 1024:
        raise GovernedTrainingBuildError("operator request exceeds byte bound")
    connection = sqlite3.connect(path, isolation_level=None, timeout=30)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS governed_cli_request ("
            "run_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL, "
            "request_json TEXT NOT NULL, acquired_at TEXT NOT NULL, dataset_version INTEGER NOT NULL)"
        )
        if "dataset_version" not in {
            row[1] for row in connection.execute("PRAGMA table_info(governed_cli_request)")
        }:
            connection.execute(
                "ALTER TABLE governed_cli_request ADD COLUMN dataset_version INTEGER NOT NULL DEFAULT 0"
            )
        row = connection.execute(
            "SELECT request_digest,request_json,acquired_at,dataset_version FROM governed_cli_request WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row is not None:
            if row[0] != _digest(request) or row[1] != encoded:
                raise GovernedTrainingBuildError("run identity conflicts with admitted operator request")
            datetime.fromisoformat(row[2])
            acquired_at = row[2]
            if type(row[3]) is not int or row[3] < 0:
                raise GovernedTrainingBuildError("invalid admitted dataset version")
            expected_version = row[3]
        else:
            acquired_at = datetime.now(UTC).isoformat()
            connection.execute(
                "INSERT INTO governed_cli_request VALUES (?,?,?,?,?)",
                (run_id, _digest(request), encoded, acquired_at, expected_version),
            )
        connection.commit()
        return acquired_at, expected_version
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def build_governed_artifact(
    *,
    corpus_paths: Sequence[str | Path],
    state_directory: str | Path,
    output_path: str | Path,
    run_id: str,
    dataset_id: str,
    rights_refs: Sequence[str],
    classification: str = "internal",
    algorithm: str = "neural",
    hidden_size: int = 24,
    epochs: int = 8,
    learning_rate: float = 0.05,
    gradient_clip: float = 1.0,
    order: int = 2,
    seed: int = 0,
    max_steps: int = 100_000,
    max_updates: int = 4096,
    max_training_bytes: int = 64 * 1024 * 1024,
    world_size: int | None = None,
    collective_timeout_seconds: float | None = None,
) -> dict[str, object]:
    """Materialize licensed files, resume training, and atomically export weights."""
    if algorithm not in {"reference", "neural", "data_parallel"}:
        raise GovernedTrainingBuildError("algorithm must be reference, neural or data_parallel")
    neural = algorithm in {"neural", "data_parallel"}
    if algorithm == "data_parallel":
        world_size = 2 if world_size is None else world_size
        collective_timeout_seconds = (
            60.0 if collective_timeout_seconds is None else collective_timeout_seconds
        )
        if type(world_size) is not int or not 2 <= world_size <= 4:
            raise GovernedTrainingBuildError("local parallel world_size must be between 2 and 4")
        if (
            isinstance(collective_timeout_seconds, bool)
            or not isinstance(collective_timeout_seconds, (int, float))
            or not math.isfinite(collective_timeout_seconds)
            or not 0 < collective_timeout_seconds <= 120
        ):
            raise GovernedTrainingBuildError("collective timeout must be finite and within 120 seconds")
    elif world_size is not None or collective_timeout_seconds is not None:
        raise GovernedTrainingBuildError("parallel process configuration requires data_parallel")
    if any(not isinstance(value, str) or not value.strip() for value in (run_id, dataset_id, classification)):
        raise GovernedTrainingBuildError("run, dataset and classification identities must be non-empty")
    if classification not in {"public", "internal", "confidential", "restricted"}:
        raise GovernedTrainingBuildError("unsupported dataset classification")
    if isinstance(rights_refs, (str, bytes)) or not isinstance(rights_refs, Sequence):
        raise GovernedTrainingBuildError("rights references must be an explicit ordered sequence")
    rights = tuple(rights_refs)
    if (
        not rights
        or any(not isinstance(ref, str) or not ref.strip() for ref in rights)
        or len(set(rights)) != len(rights)
    ):
        raise GovernedTrainingBuildError("explicit unique source rights references are required")
    for name, value in (
        ("seed", seed),
        ("hidden_size", hidden_size),
        ("epochs", epochs),
        ("order", order),
        ("max_steps", max_steps),
        ("max_updates", max_updates),
        ("max_training_bytes", max_training_bytes),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or (name != "seed" and value <= 0):
            raise GovernedTrainingBuildError(f"{name} must be an integer within the execution policy")
    for name, value, maximum in (
        ("learning_rate", learning_rate, 10.0),
        ("gradient_clip", gradient_clip, 1000.0),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 < value <= maximum
        ):
            raise GovernedTrainingBuildError(f"{name} must be positive and finite")
    if not 4 <= hidden_size <= 128 or not 1 <= epochs <= 1024 or not 1 <= order <= 8:
        raise GovernedTrainingBuildError("model configuration exceeds bounded execution policy")
    if neural and seed < 0:
        raise GovernedTrainingBuildError("neural initialization seed must be non-negative")
    sources = _read_sources(corpus_paths, neural=neural)
    if neural and (
        sum(len(payload) + 1 for _, payload in sources) * epochs > min(max_steps, 16_777_216)
        or len(sources) * epochs > min(max_updates, 65_536)
        or sum(len(payload) for _, payload in sources) * epochs > max_training_bytes
    ):
        raise GovernedTrainingBuildError("neural corpus/configuration exceeds cumulative execution budget")
    if algorithm == "reference" and (
        sum(_step_count(payload.decode("utf-8")) for _, payload in sources) > max_steps
        or len(sources) > max_updates
        or sum(len(payload) for _, payload in sources) + len(sources) - 1 > max_training_bytes
    ):
        raise GovernedTrainingBuildError("reference corpus exceeds execution budget")
    directory = Path(state_directory).expanduser()
    if directory.is_symlink():
        raise GovernedTrainingBuildError("state directory symlink is forbidden")
    directory.mkdir(parents=True, exist_ok=True)
    directory = directory.resolve(strict=True)
    output = Path(output_path).expanduser()
    if output.is_symlink():
        raise GovernedTrainingBuildError("artifact output symlink is forbidden")
    output = output.resolve()
    dataset_path, run_path = directory / "datasets.sqlite3", directory / "training.sqlite3"
    reserved_paths = {
        Path(str(path) + suffix)
        for path in (dataset_path, run_path)
        for suffix in ("", "-wal", "-shm", "-journal")
    }
    source_paths = {path for path, _ in sources}
    if output in source_paths or output in reserved_paths or source_paths & reserved_paths:
        raise GovernedTrainingBuildError("corpus, artifact and database paths must be distinct")
    if any(path.is_symlink() for path in (dataset_path, run_path)):
        raise GovernedTrainingBuildError("authoritative database symlinks are forbidden")
    guarded_paths = (output, *reserved_paths)
    existing = [path for path in guarded_paths if path.exists()]
    for index, path in enumerate(existing):
        if any(path.samefile(other) for other in (*source_paths, *existing[index + 1 :])):
            raise GovernedTrainingBuildError("corpus, artifact and database file identities must be distinct")
    if not output.parent.is_dir():
        raise GovernedTrainingBuildError("artifact output parent must exist")
    environment: dict[str, object] = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.system(),
        "machine": platform.machine(),
        "python_compiler": platform.python_compiler(),
    }
    if neural:
        import numpy

        from .neural_trainer import NeuralLocalTrainer

        environment["numpy"] = numpy.__version__
    if algorithm == "data_parallel":
        from .distributed_trainer import LocalDataParallelTrainer

        environment["worker_strategy"] = "local_spawned_processes"
    budget = {"max_steps": max_steps, "max_documents": max_updates, "max_training_bytes": max_training_bytes}
    if algorithm == "reference":
        budget["max_corpus_bytes"] = max_training_bytes
    parameters = {
        "algorithm": algorithm,
        "hidden_size": hidden_size,
        "epochs": epochs,
        "learning_rate": float(learning_rate),
        "gradient_clip": float(gradient_clip),
        "order": order,
    }
    if algorithm == "data_parallel":
        parameters.update(
            {"world_size": world_size, "collective_timeout_seconds": float(collective_timeout_seconds)}
        )
        budget["max_processes"] = world_size
        budget["max_barriers"] = ((len(sources) + world_size - 1) // world_size) * epochs
    code_digest, environment_digest = _code_digest(algorithm), _digest(environment)
    request = {
        "schema_version": "skeleton.governed_cli_request.v1",
        "run_id": run_id,
        "dataset_id": dataset_id,
        "sources": [
            {"path": str(path), "content_digest": hashlib.sha256(payload).hexdigest()}
            for path, payload in sources
        ],
        "rights_refs": rights,
        "classification": classification,
        "parameters": parameters,
        "seed": seed,
        "budget": budget,
        "code_digest": code_digest,
        "environment_digest": environment_digest,
    }
    datasets = DatasetRegistry(dataset_path)
    runs = None
    try:
        acquired_text, expected_version = _admit_request(
            run_path, run_id, request, expected_version=datasets.latest_materialized_version(dataset_id)
        )
        acquired_at = datetime.fromisoformat(acquired_text)
        runs = TrainingRepository(run_path)
        materialized_sources = []
        for path, payload in sources:
            envelope = IngestEnvelope.from_bytes(
                source_id=path.as_uri(),
                payload=payload,
                acquired_at=acquired_at,
                parser_version="utf8-text@1",
                classification=classification,
                rights=("training", "evaluation"),
                trusted=True,
            )
            existing = datasets.source_envelope(envelope.content_digest)
            if existing is not None:
                # Original acquisition is immutable evidence when bytes are reused.
                if (
                    existing.source_id,
                    existing.parser_version,
                    existing.classification,
                    existing.rights,
                    existing.trusted,
                    existing.quarantine_reason,
                ) != (
                    envelope.source_id,
                    envelope.parser_version,
                    envelope.classification,
                    envelope.rights,
                    envelope.trusted,
                    envelope.quarantine_reason,
                ):
                    raise GovernedTrainingBuildError(
                        "source content conflicts with its immutable ingest metadata"
                    )
                envelope = existing
            materialized_sources.append(
                MaterializedTrainingSource(
                    envelope=envelope, payload=payload, format="utf8_text", rights_refs=rights
                )
            )
        materialized = datasets.ingest_materialized(
            ingestion_id="cli:" + run_id,
            dataset_id=dataset_id,
            expected_version=expected_version,
            sources={"train": tuple(materialized_sources)},
            classification=classification,
            permitted_uses=("training", "evaluation"),
            retention_class="model-development",
        )
        corpus = datasets.training_corpus(materialized.dataset_digest)
        if neural:
            base_digest = NeuralLocalTrainer.initialize_model(
                run_id, hidden_size=hidden_size, seed=seed
            ).model_digest
            trainer = (
                LocalDataParallelTrainer(datasets, runs)
                if algorithm == "data_parallel"
                else NeuralLocalTrainer(datasets, runs)
            )
        else:
            base_digest = _digest({"kind": "untrained_reference_ngram", "order": order})
            trainer = ReferenceLocalTrainer(datasets, runs)
        manifest = TrainingRunManifest(
            run_id=run_id,
            dataset_digest=materialized.dataset_digest,
            base_model_digest=base_digest,
            code_digest=code_digest,
            environment_digest=environment_digest,
            hyperparameters=parameters,
            seed=seed,
            resource_budget=budget,
            world_size=world_size if algorithm == "data_parallel" else 1,
            parallelism="data_parallel" if algorithm == "data_parallel" else "single",
            collective_timeout_seconds=(
                float(collective_timeout_seconds) if algorithm == "data_parallel" else 60.0
            ),
        )
        if neural:
            model, training = trainer.train(
                manifest,
                corpus,
                hidden_size=hidden_size,
                epochs=epochs,
                learning_rate=learning_rate,
                gradient_clip=gradient_clip,
            )
        else:
            model, training = trainer.train(manifest, corpus, order=order, checkpoint_every_documents=1)
        binding = runs.execution_binding(run_id)
        if binding is None or "dataset_authority_epoch" not in binding:
            raise GovernedTrainingBuildError("training artifact lacks durable dataset authority binding")
        with datasets.training_authority(materialized.dataset_digest, binding["dataset_authority_epoch"]):
            artifact = write_local_model_artifact(model, output)
        receipt = {
            "schema_version": "skeleton.governed_local_model_build.v1",
            "run_id": run_id,
            "algorithm": algorithm,
            "dataset_digest": materialized.dataset_digest,
            "quality_report_digest": materialized.quality_report_digest,
            "observation_digest": materialized.observation_digest,
            "ingestion_receipt_digest": materialized.digest,
            "run_manifest_digest": manifest.digest,
            "training_receipt_digest": _digest(asdict(training)),
            "checkpoint_digest": training.checkpoint_digest,
            "model_digest": model.model_digest,
            "artifact": artifact.as_dict(),
            "output_path": str(output),
            "credential_free": True,
        }
        if neural:
            receipt.update(
                {
                    "initial_loss": training.initial_loss,
                    "final_loss": training.final_loss,
                    "update_count": training.update_count,
                }
            )
        if algorithm == "data_parallel":
            receipt.update({"world_size": world_size, "barrier_count": training.barrier_count})
        receipt["receipt_digest"] = _digest(receipt)
        return receipt
    finally:
        if runs is not None:
            runs.close()
        datasets.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skeleton-train-governed-model", description=__doc__)
    parser.add_argument("corpus", nargs="+", help="Explicit UTF-8 corpus files")
    parser.add_argument("--state-directory", required=True, help="Durable local dataset/training databases")
    parser.add_argument("--output", required=True, dest="output_path", help="Reloadable model JSON output")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--rights-ref", required=True, action="append", dest="rights_refs")
    parser.add_argument("--classification", default="internal")
    parser.add_argument("--algorithm", choices=("reference", "neural", "data_parallel"), default="neural")
    parser.add_argument("--world-size", type=int)
    parser.add_argument("--collective-timeout-seconds", type=float)
    parser.add_argument("--hidden-size", type=int, default=24)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--gradient-clip", type=float, default=1.0)
    parser.add_argument("--order", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-steps", type=int, default=100_000)
    parser.add_argument("--max-updates", type=int, default=4096)
    parser.add_argument("--max-training-bytes", type=int, default=64 * 1024 * 1024)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = vars(parser.parse_args(argv))
    args["corpus_paths"] = args.pop("corpus")
    try:
        receipt = build_governed_artifact(**args)
    except (
        GovernedTrainingBuildError,
        TrainingStateError,
        LocalModelArtifactError,
        ValueError,
        OSError,
        sqlite3.Error,
    ) as exc:
        parser.exit(2, f"{parser.prog}: {exc}\n")
    print(json.dumps(receipt, sort_keys=True, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
