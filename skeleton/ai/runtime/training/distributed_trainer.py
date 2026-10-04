"""Bounded synchronous data-parallel NumPy training on one local machine.

This implements fixed local process ranks, not a remote cluster or elastic DDP.
Every active rank starts a barrier from identical weights, performs one existing
clipped document SGD update, and contributes to an ordered parameter mean.
Only the parent can commit a complete barrier to the existing training owner.
"""

from __future__ import annotations

import json
import math
import multiprocessing
import os
import platform
import queue
import sqlite3
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from multiprocessing.connection import Connection
from typing import Any, Self

import numpy as np

from skeleton.ai.runtime.inference.neural import (
    NeuralLMConfig,
    NeuralLMError,
    NumpyRecurrentLM,
)

from .control import (
    MAX_CHECKPOINT_PAYLOAD_BYTES,
    TrainingCheckpoint,
    TrainingRunManifest,
    TrainingStateError,
    TrainingTelemetry,
    WorkerLease,
    _canonical,
    _digest,
    _require_digest,
)
from .neural_trainer import NeuralLocalTrainer, NeuralTrainingArtifact
from .trainer import corpus_digest

_ALGORITHM = "numpy-recurrent-byte-synchronous-mean-sgd-v1"
_BINDING_SCHEMA = "skeleton.local_parallel_training_binding.v1"
_PAYLOAD_SCHEMA = "skeleton.local_parallel_training_resume.v1"
_STRATEGY = "local_spawned_processes"
_AGGREGATION = "rank_ordered_active_parameter_mean"
_PARAMETERS = ("embedding", "recurrent", "hidden_bias", "output", "output_bias")
_MAX_MESSAGE_BYTES = MAX_CHECKPOINT_PAYLOAD_BYTES
_BINDING_FIELDS = frozenset(
    {
        "schema_version",
        "manifest_digest",
        "dataset_digest",
        "dataset_authority_epoch",
        "split_name",
        "split_digest",
        "corpus_digest",
        "document_sequence_digest",
        "document_count",
        "document_digests",
        "document_sizes",
        "corpus_bytes",
        "document_bytes",
        "targets_per_epoch",
        "training_config",
        "initial_model_digest",
    }
)
_CONFIG_FIELDS = frozenset(
    {
        "algorithm",
        "model_id",
        "hidden_size",
        "seed",
        "dtype",
        "epochs",
        "learning_rate",
        "gradient_clip",
        "world_size",
        "collective_timeout_seconds",
        "strategy",
        "aggregation",
        "runtime",
    }
)
_RANK_FIELDS = frozenset(
    {
        "rank",
        "worker_pid",
        "worker_epoch",
        "barrier_index",
        "input_model_digest",
        "document_index",
        "document_digest",
        "targets",
        "training_bytes",
        "updated_model_digest",
        "status",
    }
)
_BARRIER_FIELDS = frozenset(
    {
        "barrier_index",
        "source_epoch",
        "source_document_index",
        "input_model_digest",
        "output_model_digest",
        "world_size",
        "worker_epoch",
        "ranks",
    }
)


def _runtime() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "platform": sys.platform,
        "machine": platform.machine(),
    }


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate local worker message key")
        result[key] = value
    return result


def _decode_message(raw: bytes) -> dict[str, Any]:
    def reject_constant(_value: str) -> None:
        raise ValueError("nonfinite local worker message")

    message = json.loads(
        raw.decode("utf-8"), object_pairs_hook=_strict_object, parse_constant=reject_constant
    )
    if not isinstance(message, dict):
        raise TypeError("local worker message must be an object")
    return message


def _message_bytes(message: Mapping[str, Any]) -> bytes:
    raw = _canonical(message).encode("utf-8")
    if len(raw) > _MAX_MESSAGE_BYTES:
        raise TrainingStateError("local rank message exceeds byte bound")
    return raw


def _rank_worker(rank: int, connection: Connection) -> None:
    """Pure numerical rank: no dataset store, lease, checkpoint or network owner."""
    try:
        connection.send_bytes(_message_bytes({"kind": "ready", "rank": rank, "worker_pid": os.getpid()}))
        while True:
            job = _decode_message(connection.recv_bytes(_MAX_MESSAGE_BYTES))
            if (
                set(job)
                != {
                    "kind",
                    "worker_epoch",
                    "barrier_index",
                    "input_model_digest",
                    "model",
                    "document",
                    "document_index",
                    "learning_rate",
                    "gradient_clip",
                }
                or job["kind"] != "train"
            ):
                raise ValueError("invalid local training job")
            model = NumpyRecurrentLM.from_dict(job["model"])
            if model.model_digest != job["input_model_digest"]:
                raise ValueError("local rank pinned weights mismatch")
            document = job["document"]
            targets = 0
            training_bytes = 0
            if document is not None:
                training_bytes = len(document.encode("utf-8"))
                if not 1 <= training_bytes <= 4096:
                    raise ValueError("local rank document byte bound")
                targets = model.train_document(
                    document, learning_rate=job["learning_rate"], gradient_clip=job["gradient_clip"]
                )
            receipt = {
                "rank": rank,
                "worker_pid": os.getpid(),
                "worker_epoch": job["worker_epoch"],
                "barrier_index": job["barrier_index"],
                "input_model_digest": job["input_model_digest"],
                "document_index": job["document_index"],
                "document_digest": None if document is None else _digest(document),
                "targets": targets,
                "training_bytes": training_bytes,
                "updated_model_digest": model.model_digest,
                "status": "idle" if document is None else "updated",
            }
            connection.send_bytes(
                _message_bytes({"kind": "result", "receipt": receipt, "model": model.to_dict()})
            )
    except EOFError:
        pass
    except Exception as exc:  # noqa: BLE001 - Report any numerical worker failure before exit.
        try:
            connection.send_bytes(
                _message_bytes({"kind": "error", "rank": rank, "error_type": type(exc).__name__})
            )
        except (OSError, ValueError):
            pass
    finally:
        connection.close()


class _RankPool:
    """Bound each IPC operation without losing cleanup on a partial pipe write."""

    def __init__(self, world_size: int, timeout: float) -> None:
        self.world_size = world_size
        self.timeout = timeout
        self.processes: list[Any] = []
        self.connections: list[Connection] = []
        self.threads: list[threading.Thread] = []
        self.pids: tuple[int, ...] = ()
        self._closed = False

    def __enter__(self) -> Self:
        context = multiprocessing.get_context("spawn")
        try:
            for rank in range(self.world_size):
                parent, child = context.Pipe(duplex=True)
                process = context.Process(
                    target=_rank_worker,
                    args=(rank, child),
                    name=f"skeleton-training-rank-{rank}",
                    daemon=True,
                )
                self.connections.append(parent)
                self.processes.append(process)
                try:
                    process.start()
                finally:
                    child.close()
            self.pids = tuple(process.pid for process in self.processes)
            ready = self._exchange(None)
            for rank, message in enumerate(ready):
                if message != {"kind": "ready", "rank": rank, "worker_pid": self.pids[rank]}:
                    raise TrainingStateError("invalid local rank startup receipt")
            if len(set(self.pids)) != self.world_size or os.getpid() in self.pids:
                raise TrainingStateError("local ranks require distinct actual worker processes")
            return self
        except BaseException:
            self.close()
            raise

    def _exchange(self, jobs: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
        deadline = time.monotonic() + self.timeout
        events: queue.Queue[tuple[str, int, Any]] = queue.Queue()
        current_threads: list[threading.Thread] = []

        def receive(rank: int, connection: Connection) -> None:
            try:
                message = _decode_message(connection.recv_bytes(_MAX_MESSAGE_BYTES))
            except Exception as exc:  # noqa: BLE001 - Transfer all bounded IPC failures to the parent.
                events.put(("error", rank, exc))
            else:
                events.put(("received", rank, message))

        def send(rank: int, connection: Connection, raw: bytes) -> None:
            try:
                connection.send_bytes(raw)
            except Exception as exc:  # noqa: BLE001 - A failed writer must abort the collective.
                events.put(("error", rank, exc))

        payloads = None if jobs is None else [_message_bytes(job) for job in jobs]
        if payloads is not None and len(payloads) != self.world_size:
            raise TrainingStateError("local barrier job membership mismatch")
        for rank, connection in enumerate(self.connections):
            receiver = threading.Thread(target=receive, args=(rank, connection), daemon=True)
            current_threads.append(receiver)
            if payloads is not None:
                sender = threading.Thread(target=send, args=(rank, connection, payloads[rank]), daemon=True)
                current_threads.append(sender)
        self.threads.extend(current_threads)
        for thread in current_threads:
            thread.start()
        results: dict[int, dict[str, Any]] = {}
        while len(results) < self.world_size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TrainingStateError("local training collective timed out")
            try:
                kind, rank, value = events.get(timeout=remaining)
            except queue.Empty as exc:
                raise TrainingStateError("local training collective timed out") from exc
            if kind == "error":
                raise TrainingStateError(f"local training rank {rank} failed") from value
            if rank in results or value.get("kind") == "error":
                raise TrainingStateError(f"local training rank {rank} returned invalid or failed work")
            results[rank] = value
        for thread in current_threads:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
            if thread.is_alive():
                raise TrainingStateError("local training collective did not finish its message transfer")
        self.threads = [thread for thread in self.threads if thread.is_alive()]
        return [results[rank] for rank in range(self.world_size)]

    def run(self, jobs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return self._exchange(jobs)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        started = [process for process in self.processes if process.pid is not None]
        for process in started:
            if process.is_alive():
                process.terminate()
        for process in started:
            process.join(timeout=0.25)
            if process.is_alive():
                process.kill()
        for process in started:
            process.join(timeout=0.5)
        for connection in self.connections:
            connection.close()
        for thread in self.threads:
            if thread.ident is not None:
                thread.join(timeout=0.5)
        if any(process.is_alive() for process in started) or any(
            thread.is_alive() for thread in self.threads
        ):
            raise TrainingStateError("local rank cleanup failed to quiesce")
        for process in self.processes:
            process.close()

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()


@dataclass(frozen=True, slots=True)
class LocalDataParallelArtifact(NeuralTrainingArtifact):
    world_size: int
    barrier_count: int
    barrier_receipt_digest: str
    strategy: str


class LocalDataParallelTrainer(NeuralLocalTrainer):
    """Use fixed local ranks and commit only complete synchronous barriers."""

    @staticmethod
    def _optimizer(config: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "algorithm": _ALGORITHM,
            "learning_rate": config["learning_rate"],
            "gradient_clip": config["gradient_clip"],
            "slots": {},
            "aggregation": _AGGREGATION,
        }

    @staticmethod
    def _usage(binding: Mapping[str, Any], epoch: int, document_index: int) -> dict[str, int]:
        config = binding["training_config"]
        count, world_size = binding["document_count"], config["world_size"]
        prefix_bytes = sum(binding["document_sizes"][:document_index])
        return {
            "steps": epoch * binding["targets_per_epoch"] + prefix_bytes + document_index,
            "documents": epoch * count + document_index,
            "training_bytes": epoch * binding["document_bytes"] + prefix_bytes,
            "epochs": epoch,
            "barriers": epoch * math.ceil(count / world_size) + document_index // world_size,
        }

    @staticmethod
    def _enforce_usage(manifest: TrainingRunManifest, usage: Mapping[str, int], *, corpus_bytes: int) -> None:
        NeuralLocalTrainer._enforce_usage(manifest, usage, corpus_bytes=corpus_bytes)
        for name, actual in (("max_barriers", usage["barriers"]), ("max_processes", manifest.world_size)):
            limit = manifest.resource_budget.get(name)
            if limit is not None and actual > limit:
                raise TrainingStateError(f"local parallel training budget exceeded: {name}")

    @staticmethod
    def _validate_binding(manifest: TrainingRunManifest, binding: Mapping[str, Any]) -> None:
        if set(binding) != _BINDING_FIELDS or binding["schema_version"] != _BINDING_SCHEMA:
            raise ValueError("invalid local parallel binding fields")
        config = binding["training_config"]
        if not isinstance(config, dict) or set(config) != _CONFIG_FIELDS:
            raise ValueError("invalid local parallel config fields")
        if (
            binding["manifest_digest"] != manifest.digest
            or binding["dataset_digest"] != manifest.dataset_digest
            or binding["initial_model_digest"] != manifest.base_model_digest
            or config["algorithm"] != _ALGORITHM
            or config["strategy"] != _STRATEGY
            or config["aggregation"] != _AGGREGATION
            or config["runtime"] != _runtime()
            or config["world_size"] != manifest.world_size
            or manifest.parallelism != "data_parallel"
            or config["collective_timeout_seconds"] != manifest.collective_timeout_seconds
            or config["seed"] != manifest.seed
            or config["dtype"] != "float64"
            or config["model_id"] != f"skeleton-local-neural:{manifest.run_id}"
        ):
            raise ValueError("local parallel immutable identity mismatch")
        for name, minimum, maximum in (("world_size", 2, 4), ("hidden_size", 4, 128), ("epochs", 1, 1024)):
            if type(config[name]) is not int or not minimum <= config[name] <= maximum:
                raise ValueError("invalid local parallel integer configuration")
        for name, maximum in (
            ("collective_timeout_seconds", 120),
            ("learning_rate", 10),
            ("gradient_clip", 1000),
        ):
            if (
                type(config[name]) not in {float, int}
                or not math.isfinite(config[name])
                or not 0 < config[name] <= maximum
            ):
                raise ValueError("invalid local parallel numeric configuration")
        if (
            type(config["seed"]) is not int
            or type(binding["dataset_authority_epoch"]) is not int
            or binding["dataset_authority_epoch"] < 0
        ):
            raise ValueError("invalid local parallel seed or authority epoch")
        for name, value in manifest.hyperparameters.items():
            if name == "algorithm":
                if value not in {"data_parallel", _ALGORITHM}:
                    raise ValueError("local parallel manifest algorithm mismatch")
            elif name in config and value != config[name]:
                raise ValueError("local parallel manifest hyperparameter mismatch")
        sizes, digests, count = (
            binding["document_sizes"],
            binding["document_digests"],
            binding["document_count"],
        )
        if (
            type(count) is not int
            or not 1 <= count <= 65536
            or not isinstance(sizes, list)
            or not isinstance(digests, list)
            or len(sizes) != count
            or len(digests) != count
            or any(type(size) is not int or not 1 <= size <= 4096 for size in sizes)
        ):
            raise ValueError("invalid local parallel document metadata")
        for digest in digests:
            _require_digest(digest, field="document identity")
        for name in ("split_digest", "corpus_digest", "document_sequence_digest"):
            _require_digest(binding[name], field=name)
        if not isinstance(binding["split_name"], str) or not binding["split_name"].strip():
            raise ValueError("invalid local parallel split name")
        for name, expected in (
            ("document_bytes", sum(sizes)),
            ("corpus_bytes", sum(sizes) + count - 1),
            ("targets_per_epoch", sum(sizes) + count),
        ):
            if type(binding[name]) is not int or binding[name] != expected:
                raise ValueError("local parallel corpus accounting mismatch")
        if binding["corpus_bytes"] > 1024 * 1024:
            raise ValueError("local parallel corpus hard bound exceeded")
        initial = NeuralLocalTrainer.initialize_model(
            manifest.run_id, hidden_size=config["hidden_size"], seed=config["seed"]
        )
        if initial.model_digest != manifest.base_model_digest:
            raise ValueError("local parallel initialized base mismatch")

    @staticmethod
    def _validate_barrier(
        binding: Mapping[str, Any],
        barrier: Mapping[str, Any],
        *,
        worker_epoch: int,
        barrier_index: int,
        source_epoch: int,
        source_index: int,
        input_digest: str | None,
        output_digest: str,
        pids: Sequence[int] | None = None,
    ) -> None:
        world_size = binding["training_config"]["world_size"]
        if not isinstance(barrier, dict) or set(barrier) != _BARRIER_FIELDS:
            raise ValueError("invalid local barrier fields")
        for field, expected in (
            ("barrier_index", barrier_index),
            ("source_epoch", source_epoch),
            ("source_document_index", source_index),
            ("world_size", world_size),
            ("worker_epoch", worker_epoch),
            ("output_model_digest", output_digest),
        ):
            if (
                barrier[field] != expected
                or isinstance(barrier[field], bool)
                or (type(expected) is int and type(barrier[field]) is not int)
            ):
                raise ValueError("local barrier identity mismatch")
        snapshot = _require_digest(barrier["input_model_digest"], field="barrier input weights")
        if input_digest is not None and snapshot != input_digest:
            raise ValueError("local barrier snapshot mismatch")
        ranks = barrier["ranks"]
        if not isinstance(ranks, list) or len(ranks) != world_size:
            raise ValueError("incomplete local barrier membership")
        actual_pids = []
        for rank, receipt in enumerate(ranks):
            if not isinstance(receipt, dict) or set(receipt) != _RANK_FIELDS:
                raise ValueError("invalid local rank receipt fields")
            expected_index = source_index + rank
            active = expected_index < binding["document_count"]
            if not active:
                expected_index = None
            expected_bytes = binding["document_sizes"][expected_index] if active else 0
            expected_document = binding["document_digests"][expected_index] if active else None
            expected = {
                "rank": rank,
                "worker_epoch": worker_epoch,
                "barrier_index": barrier_index,
                "input_model_digest": snapshot,
                "document_index": expected_index,
                "document_digest": expected_document,
                "training_bytes": expected_bytes,
                "targets": expected_bytes + 1 if active else 0,
                "status": "updated" if active else "idle",
            }
            if any(
                receipt[name] != value
                or isinstance(receipt[name], bool)
                or (type(value) is int and type(receipt[name]) is not int)
                for name, value in expected.items()
            ):
                raise ValueError("local rank assignment or usage mismatch")
            pid = receipt["worker_pid"]
            if type(pid) is not int or pid <= 0 or (pids is not None and pid != pids[rank]):
                raise ValueError("local rank process identity mismatch")
            actual_pids.append(pid)
            updated_digest = _require_digest(receipt["updated_model_digest"], field="rank updated weights")
            if not active and updated_digest != snapshot:
                raise ValueError("idle local rank changed weights")
        if len(set(actual_pids)) != world_size:
            raise ValueError("duplicate local worker process identity")

    def _barrier(
        self,
        pool: _RankPool,
        binding: Mapping[str, Any],
        lease: WorkerLease,
        model: NumpyRecurrentLM,
        cursor: Mapping[str, int],
        documents: Sequence[str],
    ) -> tuple[NumpyRecurrentLM, dict[str, Any]]:
        config = binding["training_config"]
        snapshot = model.to_dict()
        input_digest = model.model_digest
        barrier_index = cursor["barrier_count"] + 1
        jobs = []
        for rank in range(config["world_size"]):
            index = cursor["document_index"] + rank
            active = index < len(documents)
            jobs.append(
                {
                    "kind": "train",
                    "worker_epoch": lease.epoch,
                    "barrier_index": barrier_index,
                    "input_model_digest": input_digest,
                    "model": snapshot,
                    "document": documents[index] if active else None,
                    "document_index": index if active else None,
                    "learning_rate": config["learning_rate"],
                    "gradient_clip": config["gradient_clip"],
                }
            )
        results = pool.run(jobs)
        rank_models = []
        for result in results:
            if (
                not isinstance(result, dict)
                or set(result) != {"kind", "receipt", "model"}
                or result["kind"] != "result"
            ):
                raise TrainingStateError("invalid local rank result")
            try:
                rank_model = NumpyRecurrentLM.from_dict(result["model"])
                if (
                    rank_model.config != model.config
                    or rank_model.model_id != model.model_id
                    or rank_model.model_digest != result["receipt"]["updated_model_digest"]
                ):
                    raise ValueError("local rank model identity mismatch")
            except (ValueError, TypeError, KeyError, NeuralLMError) as exc:
                raise TrainingStateError("invalid local rank weights") from exc
            rank_models.append(rank_model)
        barrier = {
            "barrier_index": barrier_index,
            "source_epoch": cursor["epoch"],
            "source_document_index": cursor["document_index"],
            "input_model_digest": input_digest,
            "output_model_digest": input_digest,
            "world_size": config["world_size"],
            "worker_epoch": lease.epoch,
            "ranks": [result["receipt"] for result in results],
        }
        try:
            self._validate_barrier(
                binding,
                barrier,
                worker_epoch=lease.epoch,
                barrier_index=barrier_index,
                source_epoch=cursor["epoch"],
                source_index=cursor["document_index"],
                input_digest=input_digest,
                output_digest=input_digest,
                pids=pool.pids,
            )
        except (ValueError, TypeError, KeyError) as exc:
            raise TrainingStateError("invalid local parallel barrier receipt") from exc
        active_count = min(config["world_size"], len(documents) - cursor["document_index"])
        try:
            parameters = {}
            with np.errstate(over="raise", invalid="raise"):
                for name in _PARAMETERS:
                    total = np.zeros_like(getattr(model, name))
                    for rank in range(active_count):
                        total += getattr(rank_models[rank], name)
                    parameters[name] = total / active_count
            updated = NumpyRecurrentLM(model_id=model.model_id, config=model.config, parameters=parameters)
        except (FloatingPointError, NeuralLMError, ValueError) as exc:
            raise TrainingStateError("invalid local parallel aggregated weights") from exc
        barrier["output_model_digest"] = updated.model_digest
        return updated, barrier

    def _persist(
        self,
        manifest: TrainingRunManifest,
        binding: Mapping[str, Any],
        lease: WorkerLease,
        model: NumpyRecurrentLM,
        cursor: dict[str, int],
        usage: dict[str, int],
        initial_loss: float,
        final_loss: float | None,
        barrier: dict[str, Any] | None,
        instant: datetime,
    ) -> TrainingCheckpoint:
        with self.datasets.training_authority(binding["dataset_digest"], binding["dataset_authority_epoch"]):
            optimizer = self._optimizer(binding["training_config"])
            payload = {
                "schema_version": _PAYLOAD_SCHEMA,
                "binding_digest": _digest(binding),
                "cursor": cursor,
                "usage": usage,
                "optimizer": optimizer,
                "model": model.to_dict(),
                "initial_loss": initial_loss,
                "final_loss": final_loss,
                "finished": cursor["epoch"] == binding["training_config"]["epochs"],
                "barrier": barrier,
            }
            checkpoint = TrainingCheckpoint(
                run_id=manifest.run_id,
                manifest_digest=manifest.digest,
                step=usage["steps"],
                model_digest=model.model_digest,
                optimizer_digest=_digest(optimizer),
                rng_digest=_digest({"seed": manifest.seed, "draws_after_initialization": 0}),
                data_cursor_digest=_digest(cursor),
                worker_epoch=lease.epoch,
                created_at=instant.isoformat(),
                payload_digest=_digest(payload),
            )
            self.runs.checkpoint(checkpoint, lease, payload=payload)
            return checkpoint

    def _restore(
        self,
        manifest: TrainingRunManifest,
        binding: Mapping[str, Any],
        checkpoint: TrainingCheckpoint,
    ) -> tuple[NumpyRecurrentLM, dict[str, int], dict[str, int], float, float | None, dict[str, Any] | None]:
        try:
            self._validate_binding(manifest, binding)
        except (ValueError, TypeError, KeyError, NeuralLMError) as exc:
            raise TrainingStateError("invalid local parallel execution binding") from exc
        self._authority(binding)
        payload = self.runs.checkpoint_payload(checkpoint)
        try:
            if (
                set(payload)
                != {
                    "schema_version",
                    "binding_digest",
                    "cursor",
                    "usage",
                    "optimizer",
                    "model",
                    "initial_loss",
                    "final_loss",
                    "finished",
                    "barrier",
                }
                or payload["schema_version"] != _PAYLOAD_SCHEMA
            ):
                raise ValueError("unsupported local parallel resume schema")
            config = binding["training_config"]
            if (
                binding["schema_version"] != _BINDING_SCHEMA
                or binding["manifest_digest"] != manifest.digest
                or binding["initial_model_digest"] != manifest.base_model_digest
                or config["algorithm"] != _ALGORITHM
                or config["strategy"] != _STRATEGY
                or config["aggregation"] != _AGGREGATION
                or config["world_size"] != manifest.world_size
                or config["runtime"] != _runtime()
                or manifest.parallelism != "data_parallel"
                or not 2 <= config["world_size"] <= 4
            ):
                raise ValueError("local parallel binding identity mismatch")
            if (
                checkpoint.manifest_digest != manifest.digest
                or payload["optimizer"] != self._optimizer(config)
                or checkpoint.optimizer_digest != _digest(payload["optimizer"])
                or checkpoint.rng_digest != _digest({"seed": manifest.seed, "draws_after_initialization": 0})
            ):
                raise ValueError("local parallel optimizer/manifest mismatch")
            cursor, usage = payload["cursor"], payload["usage"]
            if (
                not isinstance(cursor, dict)
                or not isinstance(usage, dict)
                or set(cursor) != {"epoch", "document_index", "update_count", "step", "barrier_count"}
                or set(usage)
                != {
                    "steps",
                    "documents",
                    "training_bytes",
                    "epochs",
                    "barriers",
                }
                or any(type(value) is not int or value < 0 for value in (*cursor.values(), *usage.values()))
            ):
                raise ValueError("invalid local parallel cursor or usage")
            epoch, index = cursor["epoch"], cursor["document_index"]
            if (
                not 0 <= epoch <= config["epochs"]
                or not 0 <= index < binding["document_count"]
                or index % config["world_size"]
                or (epoch == config["epochs"] and index)
                or usage != self._usage(binding, epoch, index)
                or cursor["update_count"] != usage["documents"]
                or cursor["step"] != usage["steps"]
                or cursor["barrier_count"] != usage["barriers"]
                or checkpoint.step != usage["steps"]
                or checkpoint.data_cursor_digest != _digest(cursor)
                or payload["finished"] is not (epoch == config["epochs"])
            ):
                raise ValueError("local parallel checkpoint cursor mismatch")
            model = NumpyRecurrentLM.from_dict(payload["model"])
            if (
                model.model_digest != checkpoint.model_digest
                or model.model_id != config["model_id"]
                or model.config
                != NeuralLMConfig(
                    hidden_size=config["hidden_size"], seed=config["seed"], dtype=config["dtype"]
                )
            ):
                raise ValueError("local parallel model identity mismatch")
            initial_loss, final_loss = payload["initial_loss"], payload["final_loss"]
            if type(initial_loss) not in {float, int} or not math.isfinite(initial_loss) or initial_loss < 0:
                raise ValueError("invalid local parallel initial loss")
            if payload["finished"]:
                if type(final_loss) not in {float, int} or not math.isfinite(final_loss) or final_loss < 0:
                    raise ValueError("invalid local parallel final loss")
            elif final_loss is not None:
                raise ValueError("nonterminal local parallel final loss")
            barrier = payload["barrier"]
            if cursor["barrier_count"] == 0:
                if barrier is not None or model.model_digest != manifest.base_model_digest:
                    raise ValueError("local parallel initial checkpoint mismatch")
            else:
                source_epoch = epoch if index else epoch - 1
                source_index = (
                    index - config["world_size"]
                    if index
                    else ((binding["document_count"] - 1) // config["world_size"]) * config["world_size"]
                )
                self._validate_barrier(
                    binding,
                    barrier,
                    worker_epoch=checkpoint.worker_epoch,
                    barrier_index=cursor["barrier_count"],
                    source_epoch=source_epoch,
                    source_index=source_index,
                    input_digest=None,
                    output_digest=model.model_digest,
                )
                if (
                    cursor["barrier_count"] == 1
                    and barrier["input_model_digest"] != manifest.base_model_digest
                ):
                    raise ValueError("first local barrier input identity mismatch")
            self._enforce_usage(manifest, usage, corpus_bytes=binding["corpus_bytes"])
        except (ValueError, TypeError, KeyError, NeuralLMError) as exc:
            raise TrainingStateError("invalid local parallel resume payload") from exc
        return (
            model,
            cursor,
            usage,
            float(initial_loss),
            None if final_loss is None else float(final_loss),
            barrier,
        )

    @staticmethod
    def _artifact(
        manifest: TrainingRunManifest,
        binding: Mapping[str, Any],
        checkpoint: TrainingCheckpoint,
        model: NumpyRecurrentLM,
        initial_loss: float,
        final_loss: float,
        usage: Mapping[str, int],
        barrier: Mapping[str, Any],
    ) -> LocalDataParallelArtifact:
        base = NeuralLocalTrainer._artifact(
            manifest, binding, checkpoint, model, initial_loss, final_loss, usage
        )
        fields = asdict(base)
        fields["training_receipt_digest"] = _digest(
            {
                "schema_version": "skeleton.local_parallel_training_receipt.v1",
                "binding_digest": _digest(binding),
                "checkpoint_digest": checkpoint.digest,
                "model_digest": model.model_digest,
                "barrier_digest": _digest(barrier),
                "usage": dict(usage),
                "initial_loss": initial_loss,
                "final_loss": final_loss,
            }
        )
        return LocalDataParallelArtifact(
            **fields,
            world_size=binding["training_config"]["world_size"],
            barrier_count=usage["barriers"],
            barrier_receipt_digest=_digest(barrier),
            strategy=_STRATEGY,
        )

    def load_artifact(self, run_id: str) -> tuple[NumpyRecurrentLM, LocalDataParallelArtifact]:
        manifest = self.runs.manifest(run_id)
        binding, checkpoint = self.runs.execution_binding(run_id), self.runs.latest_checkpoint(run_id)
        if self.runs.state(run_id) != "completed" or binding is None or checkpoint is None:
            raise TrainingStateError("local parallel artifact requires a completed payload-backed run")
        model, cursor, usage, initial_loss, final_loss, barrier = self._restore(manifest, binding, checkpoint)
        if cursor["epoch"] != binding["training_config"]["epochs"] or final_loss is None or barrier is None:
            raise TrainingStateError("completed local parallel artifact is incomplete")
        return model, self._artifact(
            manifest, binding, checkpoint, model, initial_loss, final_loss, usage, barrier
        )

    def train(
        self,
        manifest: TrainingRunManifest,
        corpus: Sequence[str],
        *,
        split_name: str = "train",
        hidden_size: int = 24,
        epochs: int = 8,
        learning_rate: float = 0.05,
        gradient_clip: float = 1.0,
        worker_id: str = "local-data-parallel-trainer",
        now: datetime | None = None,
    ) -> tuple[NumpyRecurrentLM, LocalDataParallelArtifact]:
        instant = now or datetime.now(UTC)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if manifest.parallelism != "data_parallel" or not 2 <= manifest.world_size <= 4:
            raise TrainingStateError("local data-parallel training requires 2-4 fixed ranks")
        if not 0 < manifest.collective_timeout_seconds <= 120:
            raise TrainingStateError("local collective timeout must be in (0, 120]")
        if type(epochs) is not int or not 1 <= epochs <= 1024:
            raise TrainingStateError("local parallel epochs must be in [1, 1024]")
        for name, value, maximum in (
            ("learning_rate", learning_rate, 10.0),
            ("gradient_clip", gradient_clip, 1000.0),
        ):
            if type(value) not in {float, int} or not math.isfinite(value) or not 0 < value <= maximum:
                raise TrainingStateError(f"invalid local parallel {name}")
        config = {
            "algorithm": _ALGORITHM,
            "model_id": f"skeleton-local-neural:{manifest.run_id}",
            "hidden_size": hidden_size,
            "seed": manifest.seed,
            "dtype": "float64",
            "epochs": epochs,
            "learning_rate": float(learning_rate),
            "gradient_clip": float(gradient_clip),
            "world_size": manifest.world_size,
            "collective_timeout_seconds": float(manifest.collective_timeout_seconds),
            "strategy": _STRATEGY,
            "aggregation": _AGGREGATION,
            "runtime": _runtime(),
        }
        for name in (
            "hidden_size",
            "epochs",
            "learning_rate",
            "gradient_clip",
            "dtype",
            "world_size",
            "strategy",
            "aggregation",
        ):
            if name in manifest.hyperparameters and manifest.hyperparameters[name] != config[name]:
                raise TrainingStateError(f"local parallel {name} conflicts with immutable manifest")
        documents = tuple(corpus)
        digest = corpus_digest(documents)
        dataset = self.datasets.require_training_ready(manifest.dataset_digest)
        self.datasets.validate_training_corpus(manifest.dataset_digest, documents, split_name=split_name)
        split = next((item for item in dataset.splits if item.name == split_name), None)
        if split is None or split.digest != digest or split.record_count != len(documents):
            raise TrainingStateError("local parallel corpus does not match registered split")
        sizes = [len(item.encode("utf-8")) for item in documents]
        corpus_bytes = sum(sizes) + len(documents) - 1
        if max(sizes) > 4096 or corpus_bytes > 1024 * 1024:
            raise TrainingStateError("local parallel document/corpus byte bound exceeded")
        binding = {
            "schema_version": _BINDING_SCHEMA,
            "manifest_digest": manifest.digest,
            "dataset_digest": manifest.dataset_digest,
            "dataset_authority_epoch": self.datasets.dataset_authority_epoch(manifest.dataset_digest),
            "split_name": split_name,
            "split_digest": split.digest,
            "corpus_digest": digest,
            "document_sequence_digest": _digest(documents),
            "document_count": len(documents),
            "document_digests": [_digest(document) for document in documents],
            "document_sizes": sizes,
            "corpus_bytes": corpus_bytes,
            "document_bytes": sum(sizes),
            "targets_per_epoch": sum(sizes) + len(documents),
            "training_config": config,
            "initial_model_digest": manifest.base_model_digest,
        }
        self._enforce_usage(manifest, self._usage(binding, epochs, 0), corpus_bytes=corpus_bytes)
        try:
            self._validate_binding(manifest, binding)
        except (ValueError, TypeError, KeyError, NeuralLMError) as exc:
            raise TrainingStateError("invalid local parallel execution binding") from exc
        model = self.initialize_model(manifest.run_id, hidden_size=hidden_size, seed=manifest.seed)
        if model.model_digest != manifest.base_model_digest:
            raise TrainingStateError("local parallel base model digest does not match manifest")
        self.runs.register_run(manifest, self.datasets, created_at=instant)
        self.runs.bind_execution(manifest.run_id, binding)
        state, checkpoint = self.runs.state(manifest.run_id), self.runs.latest_checkpoint(manifest.run_id)
        usage = self._usage(binding, 0, 0)
        cursor = {"epoch": 0, "document_index": 0, "update_count": 0, "step": 0, "barrier_count": 0}
        initial_loss, final_loss, barrier = None, None, None
        if checkpoint is not None:
            model, cursor, usage, initial_loss, final_loss, barrier = self._restore(
                manifest, binding, checkpoint
            )
        if state == "completed":
            return self.load_artifact(manifest.run_id)
        if state in {"running", "failed"}:
            checkpoint = self.runs.recover(manifest.run_id, allow_empty=True)
            if checkpoint is not None:
                model, cursor, usage, initial_loss, final_loss, barrier = self._restore(
                    manifest, binding, checkpoint
                )
            state = "recovering"
        if state not in {"registered", "recovering"}:
            raise TrainingStateError(f"local parallel run cannot execute from {state}")
        self.runs.start(manifest.run_id)
        lease = self.runs.lease_worker(manifest.run_id, worker_id, issued_at=instant)
        try:
            if checkpoint is None:
                self._authority(binding)
                initial_loss = model.loss(documents)
                if not math.isfinite(initial_loss):
                    raise TrainingStateError("nonfinite local parallel initial loss")
                checkpoint = self._persist(
                    manifest, binding, lease, model, cursor, usage, initial_loss, None, None, instant
                )
            if cursor["epoch"] < epochs:
                with _RankPool(manifest.world_size, float(manifest.collective_timeout_seconds)) as pool:
                    while cursor["epoch"] < epochs:
                        self.runs.assert_worker_current(lease)
                        self._authority(binding)
                        epoch = cursor["epoch"]
                        next_index = min(len(documents), cursor["document_index"] + manifest.world_size)
                        if next_index == len(documents):
                            epoch, next_index = epoch + 1, 0
                        next_usage = self._usage(binding, epoch, next_index)
                        self._enforce_usage(manifest, next_usage, corpus_bytes=corpus_bytes)
                        updated, barrier = self._barrier(pool, binding, lease, model, cursor, documents)
                        next_cursor = {
                            "epoch": epoch,
                            "document_index": next_index,
                            "update_count": next_usage["documents"],
                            "step": next_usage["steps"],
                            "barrier_count": next_usage["barriers"],
                        }
                        if epoch == epochs:
                            final_loss = updated.loss(documents)
                            if not math.isfinite(final_loss):
                                raise TrainingStateError("nonfinite local parallel final loss")
                        checkpoint = self._persist(
                            manifest,
                            binding,
                            lease,
                            updated,
                            next_cursor,
                            next_usage,
                            initial_loss,
                            final_loss,
                            barrier,
                            instant,
                        )
                        model, cursor, usage = updated, next_cursor, next_usage
                        self.runs.record_telemetry(
                            TrainingTelemetry(
                                manifest.run_id,
                                checkpoint.step,
                                {
                                    "barriers": float(usage["barriers"]),
                                    "document_updates": float(usage["documents"]),
                                    "active_ranks": float(
                                        sum(rank["status"] == "updated" for rank in barrier["ranks"])
                                    ),
                                    "world_size": float(manifest.world_size),
                                    "checkpoint_written": 1.0,
                                },
                                instant.isoformat(),
                            ),
                            lease,
                        )
            with self.datasets.training_authority(
                binding["dataset_digest"], binding["dataset_authority_epoch"]
            ):
                terminal = self.runs.complete(manifest.run_id, lease)
            if terminal.digest != checkpoint.digest:
                raise TrainingStateError("local parallel terminal checkpoint identity drift")
        except Exception:
            try:
                self.runs.fail(manifest.run_id, lease)
            except (TrainingStateError, sqlite3.Error):
                pass
            raise
        if initial_loss is None or final_loss is None or barrier is None:
            raise TrainingStateError("local parallel training evidence is incomplete")
        return model, self._artifact(
            manifest, binding, checkpoint, model, initial_loss, final_loss, usage, barrier
        )
