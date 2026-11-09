"""Restartable local process membership with immutable logical-rank numerics.

A physical process may execute several logical ranks, always from the same
pinned barrier snapshot. Only placement changes across fenced attempts; the
logical document sequence, clipped SGD updates and ordered mean stay fixed.
"""

from __future__ import annotations

import math
import os
import threading
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from multiprocessing.connection import Connection
from typing import Any

from skeleton.ai.runtime.inference.neural import NumpyRecurrentLM

from .control import (
    TrainingCheckpoint,
    TrainingRunManifest,
    TrainingStateError,
    WorkerLease,
    _digest,
    _require_digest,
)
from .distributed_trainer import (
    _ALGORITHM,
    _BARRIER_FIELDS,
    _CONFIG_FIELDS,
    _MAX_MESSAGE_BYTES,
    LocalDataParallelArtifact,
    LocalDataParallelTrainer,
    _decode_message,
    _message_bytes,
    _rank_update,
    _RankPool,
)
from .neural_trainer import NeuralLocalTrainer

_MEMBERSHIP_SCHEMA = "skeleton.local_elastic_membership.v1"
_MEMBERSHIP_FIELDS = frozenset(
    {
        "schema_version",
        "worker_epoch",
        "logical_ranks",
        "physical_workers",
        "worker_pids",
        "rank_to_worker",
        "previous_membership_digest",
        "previous_worker_epoch",
        "previous_physical_workers",
        "previous_resize_count",
        "previous_worker_pids",
        "resize_count",
        "barrier_index",
        "consumed_documents_before",
        "consumed_targets_before",
    }
)


def _elastic_worker(slot: int, connection: Connection) -> None:
    """Numerical process only; it never accesses a durable owner."""
    try:
        connection.send_bytes(_message_bytes({"kind": "ready", "rank": slot, "worker_pid": os.getpid()}))
        while True:
            bundle = _decode_message(connection.recv_bytes(_MAX_MESSAGE_BYTES))
            if (
                set(bundle) != {"kind", "jobs"}
                or bundle["kind"] != "logical_barrier"
                or not isinstance(bundle["jobs"], list)
                or len(bundle["jobs"]) > 4
            ):
                raise ValueError("invalid elastic physical work bundle")
            results = []
            previous_rank = -1
            for entry in bundle["jobs"]:
                if (
                    not isinstance(entry, dict)
                    or set(entry) != {"rank", "job"}
                    or type(entry["rank"]) is not int
                    or not previous_rank < entry["rank"] < 4
                ):
                    raise ValueError("invalid elastic logical rank assignment")
                previous_rank = entry["rank"]
                results.append(_rank_update(entry["rank"], entry["job"]))
            connection.send_bytes(
                _message_bytes(
                    {"kind": "logical_results", "slot": slot, "worker_pid": os.getpid(), "results": results}
                )
            )
    except EOFError:
        pass
    except Exception as exc:  # noqa: BLE001 - Transfer numerical failures to bounded parent IPC.
        try:
            connection.send_bytes(
                _message_bytes({"kind": "error", "rank": slot, "error_type": type(exc).__name__})
            )
        except (OSError, ValueError):
            pass
    finally:
        connection.close()


class _ElasticPool(_RankPool):
    _worker_target = staticmethod(_elastic_worker)

    def __init__(self, logical_ranks: int, physical_workers: int, timeout: float) -> None:
        super().__init__(physical_workers, timeout)
        self.logical_ranks = logical_ranks

    def run(self, jobs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        if len(jobs) != self.logical_ranks:
            raise TrainingStateError("elastic logical job membership mismatch")
        assignments = [
            [rank for rank in range(self.logical_ranks) if rank % self.world_size == slot]
            for slot in range(self.world_size)
        ]
        bundles = [
            {"kind": "logical_barrier", "jobs": [{"rank": rank, "job": jobs[rank]} for rank in ranks]}
            for ranks in assignments
        ]
        responses = super().run(bundles)
        results: dict[int, dict[str, Any]] = {}
        for slot, response in enumerate(responses):
            if (
                not isinstance(response, dict)
                or set(response) != {"kind", "slot", "worker_pid", "results"}
                or response["kind"] != "logical_results"
                or type(response["slot"]) is not int
                or response["slot"] != slot
                or type(response["worker_pid"]) is not int
                or response["worker_pid"] != self.pids[slot]
                or not isinstance(response["results"], list)
                or len(response["results"]) != len(assignments[slot])
            ):
                raise TrainingStateError("invalid elastic physical worker result")
            for rank, result in zip(assignments[slot], response["results"], strict=True):
                if (
                    not isinstance(result, dict)
                    or not isinstance(result.get("receipt"), dict)
                    or type(result["receipt"].get("rank")) is not int
                    or result["receipt"]["rank"] != rank
                    or result["receipt"].get("worker_pid") != self.pids[slot]
                ):
                    raise TrainingStateError("invalid elastic logical worker result")
                results[rank] = result
        if set(results) != set(range(self.logical_ranks)):
            raise TrainingStateError("incomplete elastic logical barrier")
        return [results[rank] for rank in range(self.logical_ranks)]


@dataclass(frozen=True, slots=True)
class ElasticTrainingArtifact(LocalDataParallelArtifact):
    physical_workers: int
    membership_change_count: int
    membership_receipt_digest: str


class ElasticLocalTrainer(LocalDataParallelTrainer):
    """Resize physical local processes only when starting a fenced attempt."""

    _binding_schema = "skeleton.local_elastic_training_binding.v1"
    _payload_schema = "skeleton.local_elastic_training_resume.v1"
    _strategy = "local_elastic_spawned_processes"
    _config_fields = _CONFIG_FIELDS | {"max_physical_workers"}
    _operator_algorithms = frozenset(("elastic", _ALGORITHM))
    _receipt_schema = "skeleton.local_elastic_training_receipt.v1"

    def __init__(self, datasets, runs) -> None:
        super().__init__(datasets, runs)
        self._attempt_lock = threading.Lock()
        self._physical_workers: int | None = None

    @staticmethod
    def _maximum_physical_workers(manifest: TrainingRunManifest) -> int:
        limit = manifest.resource_budget.get("max_processes", 4)
        if type(limit) not in {int, float} or not math.isfinite(limit) or limit < 1:
            raise TrainingStateError("elastic max_processes budget must admit at least one physical worker")
        return min(4, math.floor(limit))

    def _training_config(self, manifest: TrainingRunManifest, config: dict[str, Any]) -> dict[str, Any]:
        return {**config, "max_physical_workers": self._maximum_physical_workers(manifest)}

    @classmethod
    def _validate_binding(cls, manifest: TrainingRunManifest, binding: Mapping[str, Any]) -> None:
        super()._validate_binding(manifest, binding)
        maximum = binding["training_config"]["max_physical_workers"]
        if type(maximum) is not int or maximum != cls._maximum_physical_workers(manifest):
            raise ValueError("elastic physical worker admission mismatch")

    @staticmethod
    def _enforce_usage(manifest: TrainingRunManifest, usage: Mapping[str, int], *, corpus_bytes: int) -> None:
        NeuralLocalTrainer._enforce_usage(manifest, usage, corpus_bytes=corpus_bytes)
        limit = manifest.resource_budget.get("max_barriers")
        if limit is not None and usage["barriers"] > limit:
            raise TrainingStateError("elastic training budget exceeded: max_barriers")

    def _pool(self, manifest: TrainingRunManifest) -> _ElasticPool:
        if self._physical_workers is None:
            raise TrainingStateError("elastic execution has no selected physical membership")
        return _ElasticPool(
            manifest.world_size, self._physical_workers, float(manifest.collective_timeout_seconds)
        )

    def _barrier_metadata(
        self,
        pool: _RankPool,
        binding: Mapping[str, Any],
        lease: WorkerLease,
        cursor: Mapping[str, int],
        barrier: dict[str, Any],
    ) -> dict[str, Any]:
        self.runs.assert_worker_current(lease)
        checkpoint = self.runs.latest_checkpoint(lease.run_id)
        if checkpoint is None or checkpoint.model_digest != barrier["input_model_digest"]:
            raise TrainingStateError("elastic barrier prior checkpoint identity mismatch")
        previous_payload = self.runs.checkpoint_payload(checkpoint)
        if previous_payload["cursor"] != cursor:
            raise TrainingStateError("elastic barrier prior data cursor mismatch")
        previous_barrier = previous_payload["barrier"]
        previous = None if previous_barrier is None else previous_barrier["membership"]
        physical_workers = pool.world_size
        membership = {
            "schema_version": _MEMBERSHIP_SCHEMA,
            "worker_epoch": lease.epoch,
            "logical_ranks": binding["training_config"]["world_size"],
            "physical_workers": physical_workers,
            "worker_pids": list(pool.pids),
            "rank_to_worker": [
                rank % physical_workers for rank in range(binding["training_config"]["world_size"])
            ],
            "previous_membership_digest": None if previous is None else _digest(previous),
            "previous_worker_epoch": None if previous is None else previous["worker_epoch"],
            "previous_physical_workers": None if previous is None else previous["physical_workers"],
            "previous_resize_count": None if previous is None else previous["resize_count"],
            "previous_worker_pids": None if previous is None else previous["worker_pids"],
            "resize_count": (
                0
                if previous is None
                else previous["resize_count"] + int(previous["physical_workers"] != physical_workers)
            ),
            "barrier_index": barrier["barrier_index"],
            "consumed_documents_before": cursor["update_count"],
            "consumed_targets_before": cursor["step"],
        }
        return {**barrier, "membership": membership}

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
        if not isinstance(barrier, dict) or set(barrier) != _BARRIER_FIELDS | {"membership"}:
            raise ValueError("invalid elastic barrier fields")
        membership = barrier["membership"]
        if (
            not isinstance(membership, dict)
            or set(membership) != _MEMBERSHIP_FIELDS
            or membership["schema_version"] != _MEMBERSHIP_SCHEMA
        ):
            raise ValueError("invalid elastic membership fields")
        config = binding["training_config"]
        count = membership["physical_workers"]
        if type(count) is not int or not 1 <= count <= config["max_physical_workers"]:
            raise ValueError("invalid elastic physical worker count")
        roster = membership["worker_pids"]
        if (
            not isinstance(roster, list)
            or len(roster) != count
            or any(type(pid) is not int or pid <= 0 for pid in roster)
            or len(set(roster)) != count
            or (pids is not None and list(pids) != roster)
        ):
            raise ValueError("invalid elastic physical process roster")
        assignment = [rank % count for rank in range(config["world_size"])]
        if (
            not isinstance(membership["rank_to_worker"], list)
            or any(type(slot) is not int for slot in membership["rank_to_worker"])
            or membership["rank_to_worker"] != assignment
        ):
            raise ValueError("invalid elastic logical placement")
        source_usage = LocalDataParallelTrainer._usage(binding, source_epoch, source_index)
        expected = {
            "worker_epoch": worker_epoch,
            "logical_ranks": config["world_size"],
            "barrier_index": barrier_index,
            "consumed_documents_before": source_usage["documents"],
            "consumed_targets_before": source_usage["steps"],
        }
        if (
            any(
                type(membership[name]) is not int or membership[name] != value
                for name, value in expected.items()
            )
            or type(membership["resize_count"]) is not int
            or not 0 <= membership["resize_count"] < barrier_index
        ):
            raise ValueError("elastic membership epoch or consumed position mismatch")
        previous_fields = (
            "previous_membership_digest",
            "previous_worker_epoch",
            "previous_physical_workers",
            "previous_resize_count",
            "previous_worker_pids",
        )
        if barrier_index == 1:
            if any(membership[name] is not None for name in previous_fields) or membership["resize_count"]:
                raise ValueError("invalid initial elastic membership lineage")
        else:
            _require_digest(membership["previous_membership_digest"], field="previous elastic membership")
            previous_epoch, previous_count, previous_resize, previous_roster = (
                membership[name] for name in previous_fields[1:]
            )
            if (
                type(previous_epoch) is not int
                or not 0 <= previous_epoch <= worker_epoch
                or type(previous_count) is not int
                or not 1 <= previous_count <= config["max_physical_workers"]
                or type(previous_resize) is not int
                or not 0 <= previous_resize < barrier_index - 1
                or not isinstance(previous_roster, list)
                or len(previous_roster) != previous_count
                or any(type(pid) is not int or pid <= 0 for pid in previous_roster)
                or len(set(previous_roster)) != previous_count
            ):
                raise ValueError("invalid previous elastic membership identity")
            if membership["resize_count"] != previous_resize + int(previous_count != count):
                raise ValueError("elastic resize counter mismatch")
            if previous_epoch == worker_epoch and (previous_count != count or previous_roster != roster):
                raise ValueError("elastic physical roster changed without recovery fence")
        fixed_barrier = {name: barrier[name] for name in _BARRIER_FIELDS}
        LocalDataParallelTrainer._validate_barrier(
            binding,
            fixed_barrier,
            worker_epoch=worker_epoch,
            barrier_index=barrier_index,
            source_epoch=source_epoch,
            source_index=source_index,
            input_digest=input_digest,
            output_digest=output_digest,
            pids=[roster[slot] for slot in assignment],
            require_distinct_processes=False,
        )

    @classmethod
    def _artifact(
        cls,
        manifest: TrainingRunManifest,
        binding: Mapping[str, Any],
        checkpoint: TrainingCheckpoint,
        model: NumpyRecurrentLM,
        initial_loss: float,
        final_loss: float,
        usage: Mapping[str, int],
        barrier: Mapping[str, Any],
    ) -> ElasticTrainingArtifact:
        base = super()._artifact(
            manifest, binding, checkpoint, model, initial_loss, final_loss, usage, barrier
        )
        membership = barrier["membership"]
        return ElasticTrainingArtifact(
            **asdict(base),
            physical_workers=membership["physical_workers"],
            membership_change_count=membership["resize_count"],
            membership_receipt_digest=_digest(membership),
        )

    def train(
        self,
        manifest: TrainingRunManifest,
        corpus: Sequence[str],
        *,
        physical_workers: int | None = None,
        split_name: str = "train",
        hidden_size: int = 24,
        epochs: int = 8,
        learning_rate: float = 0.05,
        gradient_clip: float = 1.0,
        worker_id: str = "local-elastic-trainer",
        now: datetime | None = None,
    ) -> tuple[NumpyRecurrentLM, ElasticTrainingArtifact]:
        selected = manifest.world_size if physical_workers is None else physical_workers
        if type(selected) is not int or not 1 <= selected <= self._maximum_physical_workers(manifest):
            raise TrainingStateError("elastic physical_workers exceeds immutable max_processes admission")
        if not self._attempt_lock.acquire(blocking=False):
            raise TrainingStateError("elastic trainer already has an active execution attempt")
        try:
            self._physical_workers = selected
            return super().train(
                manifest,
                corpus,
                split_name=split_name,
                hidden_size=hidden_size,
                epochs=epochs,
                learning_rate=learning_rate,
                gradient_clip=gradient_clip,
                worker_id=worker_id,
                now=now,
            )
        finally:
            self._physical_workers = None
            self._attempt_lock.release()
