"""Bounded, read-only observations of committed native training evidence.

Training timestamps currently record admission/checkpoint identity, not measured
compute duration. They support operational age alerts, never throughput estimates.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .control import (
    TrainingCheckpoint,
    TrainingRepository,
    TrainingRunManifest,
    TrainingStateError,
    TrainingTelemetry,
    WorkerLease,
    _canonical,
    _digest,
)
from .data import DatasetRegistry

MAX_POINTS = 4096
MAX_WORKERS = 64
MAX_METADATA_BYTES = 256 * 1024
MAX_EVENT_BYTES = 64 * 1024
MAX_PAYLOAD_BYTES = 16 * 1024 * 1024
MAX_SELECTED_PAYLOAD_BYTES = 64 * 1024 * 1024


class TrainingObservationError(TrainingStateError):
    """Committed evidence is inconsistent or exceeds observation bounds."""


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TrainingObservationError("stored counter must be a nonnegative integer")
    return value


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise TrainingObservationError("stored timestamp must be text")
    instant = datetime.fromisoformat(value)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise TrainingObservationError("stored timestamp must be timezone-aware")
    return instant.astimezone(UTC)


def _object(encoded: str, limit: int) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise TrainingObservationError("duplicate JSON evidence field")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise TrainingObservationError("nonfinite JSON evidence")

    if not isinstance(encoded, str) or len(encoded.encode("utf-8")) > limit:
        raise TrainingObservationError("stored evidence exceeds byte bounds")
    value = json.loads(encoded, object_pairs_hook=pairs, parse_constant=invalid_constant)
    if not isinstance(value, dict):
        raise TrainingObservationError("stored evidence must be a JSON object")
    _canonical(value)
    return value


def _same(actual: dict[str, Any], expected: dict[str, Any]) -> None:
    if _canonical(actual) != _canonical(expected):
        raise TrainingObservationError("stored evidence fields or numeric types drifted")


@dataclass(frozen=True, slots=True)
class TrainingObservationReport:
    """An immutable informational report; it grants no training authority."""

    _encoded: str

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._encoded)

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


class TrainingObserver:
    def __init__(self, runs: TrainingRepository, datasets: DatasetRegistry) -> None:
        self.runs = runs
        self.datasets = datasets

    def snapshot(
        self,
        run_id: str,
        *,
        now: datetime,
        stall_seconds: float = 300,
        max_points: int = 128,
        expected_code_digest: str | None = None,
        expected_environment_digest: str | None = None,
    ) -> TrainingObservationReport:
        if not isinstance(run_id, str) or not run_id.strip() or len(run_id.encode()) > 256:
            raise ValueError("run_id must be nonempty and bounded")
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be an aware datetime")
        if isinstance(stall_seconds, bool) or not isinstance(stall_seconds, (int, float)):
            raise TypeError("stall_seconds must be numeric, not boolean")
        try:
            stall_interval = float(stall_seconds)
        except OverflowError as exc:
            raise ValueError("stall_seconds must be positive and finite") from exc
        if not math.isfinite(stall_interval) or stall_interval <= 0:
            raise ValueError("stall_seconds must be positive and finite")
        if (
            isinstance(max_points, bool)
            or not isinstance(max_points, int)
            or not 1 <= max_points <= MAX_POINTS
        ):
            raise ValueError("max_points outside observation bounds")
        instant = now.astimezone(UTC)
        # Trainers publish under dataset admission and then take the run lock.
        # Follow the same order; a reversed inspector can deadlock a checkpoint.
        with self.datasets._lock, self.runs._lock:
            if self.runs._db.in_transaction:
                raise TrainingObservationError("observation requires committed repository state")
            self.runs._db.execute("BEGIN")
            try:
                result = self._snapshot(
                    run_id,
                    instant,
                    stall_interval,
                    max_points,
                    expected_code_digest,
                    expected_environment_digest,
                )
                return TrainingObservationReport(_canonical(result))
            except TrainingObservationError:
                raise
            except (
                ValueError,
                TypeError,
                KeyError,
                RuntimeError,
                OSError,
                OverflowError,
                RecursionError,
            ) as exc:
                raise TrainingObservationError("training observation evidence validation failed") from exc
            finally:
                self.runs._db.rollback()

    def _check_dimensions(self, table: str, column: str, run_id: str, limit: int) -> int:
        # Table/column identifiers are fixed internal constants, never caller input.
        count, maximum = self.runs._db.execute(
            f"SELECT count(*),max(length(CAST({column} AS BLOB))) FROM {table} WHERE run_id=?", (run_id,)
        ).fetchone()
        if maximum is not None and maximum > limit:
            raise TrainingObservationError("stored evidence exceeds byte bounds before read")
        return count

    def _snapshot(
        self,
        run_id: str,
        now: datetime,
        stall_seconds: float,
        max_points: int,
        expected_code: str | None,
        expected_environment: str | None,
    ) -> dict[str, Any]:
        if self._check_dimensions("training_run", "manifest_json", run_id, MAX_METADATA_BYTES) != 1:
            raise TrainingObservationError("training run not found")
        digest, encoded, state, epoch, registered = self.runs._db.execute(
            "SELECT manifest_digest,manifest_json,state,worker_epoch,created_at FROM training_run WHERE run_id=?",
            (run_id,),
        ).fetchone()
        raw = _object(encoded, MAX_METADATA_BYTES)
        manifest = TrainingRunManifest.from_dict(raw)
        _same(raw, manifest.as_dict())
        if manifest.run_id != run_id or manifest.digest != digest:
            raise TrainingObservationError("run manifest identity mismatch")
        if state not in {"registered", "running", "failed", "recovering", "completed"}:
            raise TrainingObservationError("unknown run state")
        epoch = _integer(epoch)
        created = _timestamp(registered)
        if created > now:
            raise TrainingObservationError("registration is after observation time")
        for expected, actual in (
            (expected_code, manifest.code_digest),
            (expected_environment, manifest.environment_digest),
        ):
            if expected is not None and expected != actual:
                raise TrainingObservationError("expected code/environment identity mismatch")
        dataset = self.datasets.require_training_ready(manifest.dataset_digest)
        self._check_dimensions("training_execution_binding", "binding_json", run_id, MAX_METADATA_BYTES)
        binding_row = self.runs._db.execute(
            "SELECT binding_digest,binding_json FROM training_execution_binding WHERE run_id=?", (run_id,)
        ).fetchone()
        binding = None if binding_row is None else _object(binding_row[1], MAX_METADATA_BYTES)
        documents = None
        authority_epoch = self.datasets.dataset_authority_epoch(manifest.dataset_digest)
        if binding is not None:
            if _digest(binding) != binding_row[0] or binding.get("manifest_digest") != manifest.digest:
                raise TrainingObservationError("execution binding identity mismatch")
            if binding.get("dataset_digest") != manifest.dataset_digest:
                raise TrainingObservationError("execution dataset identity mismatch")
            if binding.get("schema_version") not in {
                "skeleton.reference_training_binding.v1",
                "skeleton.neural_training_binding.v1",
                "skeleton.local_parallel_training_binding.v1",
                "skeleton.local_elastic_training_binding.v1",
                "skeleton.preference_training_binding.v1",
            }:
                raise TrainingObservationError("unsupported executable observation binding")
            authority_epoch = _integer(binding["dataset_authority_epoch"])
            self.datasets.assert_dataset_authority(manifest.dataset_digest, authority_epoch)
            if dataset.materialization_digest is not None:
                documents = self.datasets.training_corpus(
                    manifest.dataset_digest, split_name=binding["split_name"]
                )
                if _digest(documents) != binding["document_sequence_digest"]:
                    raise TrainingObservationError("bound exact document sequence mismatch")
                self.datasets.validate_training_corpus(
                    manifest.dataset_digest, documents, split_name=binding["split_name"]
                )
                self._validate_corpus_binding(manifest, binding, documents)
        checkpoint_count = self._check_dimensions(
            "training_checkpoint", "checkpoint_json", run_id, MAX_METADATA_BYTES
        )
        event_count = self._check_dimensions("training_telemetry", "telemetry_json", run_id, MAX_EVENT_BYTES)
        worker_count = self._check_dimensions("worker_lease", "lease_json", run_id, MAX_METADATA_BYTES)
        if worker_count > MAX_WORKERS:
            raise TrainingObservationError("worker observation count exceeded")
        rows = self.runs._db.execute(
            "SELECT checkpoint_digest,step,checkpoint_json FROM training_checkpoint WHERE run_id=? ORDER BY rowid DESC LIMIT ?",
            (run_id, max_points + 1),
        ).fetchall()[::-1]
        predecessor = rows.pop(0) if len(rows) > max_points else None
        selected_bytes = 0
        for checkpoint_digest, _, _ in rows:
            sizes = self.runs._db.execute(
                "SELECT length(CAST(payload_json AS BLOB)) FROM training_checkpoint_payload WHERE checkpoint_digest=?",
                (checkpoint_digest,),
            ).fetchone()
            if sizes is not None:
                if sizes[0] > MAX_PAYLOAD_BYTES:
                    raise TrainingObservationError(
                        "checkpoint payload exceeds observation bounds before read"
                    )
                selected_bytes += sizes[0]
        if selected_bytes > MAX_SELECTED_PAYLOAD_BYTES:
            raise TrainingObservationError("selected checkpoint payload aggregate exceeds observation bounds")
        if binding is not None and binding["schema_version"] == "skeleton.preference_training_binding.v1":
            parent_id = binding["parent"]["run_id"]
            for table, column in (
                ("training_run", "manifest_json"),
                ("training_execution_binding", "binding_json"),
                ("training_checkpoint", "checkpoint_json"),
            ):
                self._check_dimensions(table, column, parent_id, MAX_METADATA_BYTES)
            parent_size = self.runs._db.execute(
                "SELECT length(CAST(p.payload_json AS BLOB)) FROM training_checkpoint c "
                "JOIN training_checkpoint_payload p USING(checkpoint_digest) WHERE c.run_id=? ORDER BY c.step DESC LIMIT 1",
                (parent_id,),
            ).fetchone()
            if parent_size is not None and (
                parent_size[0] > MAX_PAYLOAD_BYTES
                or parent_size[0] + selected_bytes > MAX_SELECTED_PAYLOAD_BYTES
            ):
                raise TrainingObservationError(
                    "preference parent payload exceeds observation bounds before read"
                )
        checkpoints: list[dict[str, Any]] = []
        prior_time, prior_epoch, prior_step = created, 0, -1
        if predecessor is not None:
            predecessor_digest, predecessor_step, predecessor_json = predecessor
            raw = _object(predecessor_json, MAX_METADATA_BYTES)
            previous = TrainingCheckpoint.from_dict(raw)
            _same(raw, previous.as_dict())
            if (
                previous.digest != predecessor_digest
                or previous.step != _integer(predecessor_step)
                or previous.run_id != run_id
                or previous.manifest_digest != manifest.digest
                or previous.worker_epoch > epoch
                or not created <= _timestamp(previous.created_at) <= now
            ):
                raise TrainingObservationError("checkpoint window predecessor identity mismatch")
            prior_time, prior_epoch, prior_step = (
                _timestamp(previous.created_at),
                previous.worker_epoch,
                previous.step,
            )
        prior_usage: dict[str, int] = {}
        for checkpoint_digest, step, checkpoint_json in rows:
            raw = _object(checkpoint_json, MAX_METADATA_BYTES)
            checkpoint = TrainingCheckpoint.from_dict(raw)
            _same(raw, checkpoint.as_dict())
            timestamp = _timestamp(checkpoint.created_at)
            if (
                checkpoint.digest != checkpoint_digest
                or checkpoint.run_id != run_id
                or checkpoint.manifest_digest != manifest.digest
                or checkpoint.step != _integer(step)
                or step <= prior_step
                or not prior_time <= timestamp <= now
                or not prior_epoch <= checkpoint.worker_epoch <= epoch
            ):
                raise TrainingObservationError("checkpoint identity or committed timeline mismatch")
            point = self._checkpoint(manifest, binding, checkpoint, documents)
            usage = point["usage"] or {}
            if any(value < prior_usage.get(key, 0) for key, value in usage.items()):
                raise TrainingObservationError("cumulative checkpoint usage regressed")
            prior_usage = usage
            prior_time, prior_epoch, prior_step = timestamp, checkpoint.worker_epoch, checkpoint.step
            checkpoints.append(point)
        if state == "completed" and not checkpoints:
            raise TrainingObservationError("completed run has no committed checkpoint")
        if state == "completed" and checkpoints[-1]["finished"] is False:
            raise TrainingObservationError("completed run has incomplete checkpoint")
        events = self._events(run_id, manifest, created, now, max_points, checkpoints)
        workers = self._workers(run_id, epoch, state, created, now)
        last_progress = max([created, *[_timestamp(point["created_at"]) for point in checkpoints]])
        last_event = max([created, *[_timestamp(event["emitted_at"]) for event in events]])
        alerts: list[dict[str, str]] = []

        def alert(kind: str, detail: str) -> None:
            alerts.append(
                {"kind": kind, "detail": detail, "runbook": "runbook:training-observability/" + kind}
            )

        if state == "running" and (now - last_progress).total_seconds() >= stall_seconds:
            alert(
                "training_stalled",
                "No recent durable checkpoint; inspect the worker before requesting fenced recovery.",
            )
        if any(worker["epoch_status"] == "stale" for worker in workers):
            alert(
                "worker_epoch_stale",
                "An obsolete epoch lease remains recorded; stale writes must be rejected.",
            )
        if state == "recovering" or (
            state != "completed" and checkpoints and checkpoints[-1]["worker_epoch"] < epoch
        ):
            alert(
                "recovery_pending",
                "Resume only through the existing fenced trainer and checkpoint authority.",
            )
        if state == "failed":
            alert("training_failed", "Inspect failure evidence and immutable configuration before retry.")
        latest = checkpoints[-1] if checkpoints else None
        if (
            latest
            and latest["loss"]["final"] is not None
            and latest["loss"]["final"] > latest["loss"]["initial"]
        ):
            alert(
                "loss_increased",
                "Measured final corpus loss increased; held-out evaluation is required to assess quality.",
            )
        budgets = self._budgets(manifest, binding, latest)
        self.datasets.assert_dataset_authority(manifest.dataset_digest, authority_epoch)
        if binding is not None and binding["schema_version"] == "skeleton.preference_training_binding.v1":
            parent = binding["parent"]
            self.datasets.assert_dataset_authority(
                parent["dataset_digest"], parent["dataset_authority_epoch"]
            )
        return {
            "schema_version": "skeleton.training_observation.v1",
            "observed_at": now.isoformat(),
            "run_id": run_id,
            "manifest_digest": manifest.digest,
            "dataset_digest": manifest.dataset_digest,
            "code_digest": manifest.code_digest,
            "environment_digest": manifest.environment_digest,
            "code_identity_checked": expected_code is not None,
            "environment_identity_checked": expected_environment is not None,
            "state": state,
            "worker_epoch": epoch,
            "registered_at": created.isoformat(),
            "binding_digest": None if binding is None else _digest(binding),
            "binding_schema": None if binding is None else binding["schema_version"],
            "source": {
                "authority_epoch": authority_epoch,
                "current_training_admission": True,
                "exact_materialized_corpus": documents is not None,
            },
            "checkpoints": checkpoints,
            "events": events,
            "workers": workers,
            "budgets": budgets,
            "window": {
                "max_points": max_points,
                "live_checkpoint_count": checkpoint_count,
                "event_count": event_count,
                "selected_checkpoint_count": len(checkpoints),
                "selected_event_count": len(events),
                "all_live_checkpoints_selected": checkpoint_count == len(checkpoints),
                "all_events_selected": event_count == len(events),
                "archived_history_verified": False,
            },
            "activity": {
                "last_checkpoint_at": None if latest is None else latest["created_at"],
                "checkpoint_idle_seconds": (now - last_progress).total_seconds(),
                "last_event_at": None if not events else last_event.isoformat(),
                "stall_threshold_seconds": stall_seconds,
                "lease_expiry_available": False,
                "heartbeat_available": False,
                "recovery_transition_history_available": False,
            },
            "throughput": {
                "available": False,
                "documents_per_second": None,
                "bytes_per_second": None,
                "reason": "No canonical measured compute duration is persisted; checkpoint timestamps are operational identities.",
            },
            "alerts": alerts,
            "promotion_authority": False,
        }

    @staticmethod
    def _validate_corpus_binding(
        manifest: TrainingRunManifest, binding: dict[str, Any], documents: tuple[str, ...]
    ) -> None:
        from .trainer import corpus_digest

        digest = corpus_digest(documents)
        sizes = [len(document.encode("utf-8")) for document in documents]
        expected = {
            "split_digest": digest,
            "corpus_digest": digest,
            "document_sequence_digest": _digest(documents),
            "document_count": len(documents),
            "corpus_bytes": sum(sizes) + len(documents) - 1,
        }
        _same({key: binding[key] for key in expected}, expected)
        shared = {
            "schema_version",
            "manifest_digest",
            "dataset_digest",
            "dataset_authority_epoch",
            "split_name",
            *expected,
        }
        schema = binding["schema_version"]
        if schema == "skeleton.reference_training_binding.v1":
            from .trainer import _ESTIMATOR, ReferenceLocalTrainer, _step_count

            if set(binding) != shared | {"token_count", "model_config"}:
                raise TrainingObservationError("reference observation binding fields drifted")
            config = binding["model_config"]
            order = _integer(config["order"])
            if not 1 <= order <= 8:
                raise TrainingObservationError("reference observation model order is unbounded")
            _same(
                config,
                {
                    "kind": "reference_ngram",
                    "model_id": "skeleton-local-trained:" + manifest.run_id,
                    "order": order,
                    "estimator": _ESTIMATOR,
                },
            )
            if binding["token_count"] != sum(_step_count(document) for document in documents):
                raise TrainingObservationError("reference observation token geometry mismatch")
            _integer(binding["token_count"])
            ReferenceLocalTrainer._enforce_execution_boundary(manifest, documents)
        elif schema == "skeleton.neural_training_binding.v1":
            from .neural_trainer import _ALGORITHM, _MAX_EPOCHS, _MAX_HIDDEN_SIZE

            if set(binding) != shared | {
                "document_bytes",
                "targets_per_epoch",
                "training_config",
                "initial_model_digest",
            }:
                raise TrainingObservationError("neural observation binding fields drifted")
            _same(
                {key: binding[key] for key in ("document_bytes", "targets_per_epoch")},
                {"document_bytes": sum(sizes), "targets_per_epoch": sum(sizes) + len(documents)},
            )
            config = binding["training_config"]
            if set(config) != {
                "algorithm",
                "model_id",
                "hidden_size",
                "seed",
                "dtype",
                "epochs",
                "learning_rate",
                "gradient_clip",
            }:
                raise TrainingObservationError("neural observation configuration fields drifted")
            if (
                config["algorithm"] != _ALGORITHM
                or config["seed"] != manifest.seed
                or type(config["seed"]) is not int
                or config["dtype"] != "float64"
                or config["model_id"] != "skeleton-local-neural:" + manifest.run_id
                or not 4 <= _integer(config["hidden_size"]) <= _MAX_HIDDEN_SIZE
                or not 1 <= _integer(config["epochs"]) <= _MAX_EPOCHS
                or binding["initial_model_digest"] != manifest.base_model_digest
            ):
                raise TrainingObservationError("neural observation configuration identity mismatch")
            for key, maximum in (("learning_rate", 10), ("gradient_clip", 1000)):
                value = config[key]
                if type(value) not in {int, float} or not math.isfinite(value) or not 0 < value <= maximum:
                    raise TrainingObservationError("neural observation configuration is unbounded")
            for key in ("hidden_size", "epochs", "learning_rate", "gradient_clip", "dtype"):
                if key in manifest.hyperparameters and manifest.hyperparameters[key] != config[key]:
                    raise TrainingObservationError("neural configuration conflicts with manifest")
        elif schema in {
            "skeleton.local_parallel_training_binding.v1",
            "skeleton.local_elastic_training_binding.v1",
        }:
            expected_parallel = {
                "document_bytes": sum(sizes),
                "targets_per_epoch": sum(sizes) + len(documents),
                "document_sizes": sizes,
                "document_digests": [_digest(document) for document in documents],
            }
            _same({key: binding[key] for key in expected_parallel}, expected_parallel)

    def _checkpoint(
        self,
        manifest: TrainingRunManifest,
        binding: dict[str, Any] | None,
        checkpoint: TrainingCheckpoint,
        documents: tuple[str, ...] | None,
    ) -> dict[str, Any]:
        point = {
            **checkpoint.as_dict(),
            "checkpoint_digest": checkpoint.digest,
            "cursor": None,
            "usage": None,
            "finished": None,
            "semantic_validation": "unavailable_legacy_metadata",
            "numerical_health": "unavailable",
            "loss": {"initial": None, "final": None, "available": False, "kind": None},
            "preference_observations": None,
            "barrier": None,
        }
        if checkpoint.payload_digest is None:
            return point
        if binding is None:
            raise TrainingObservationError("resumable checkpoint lacks execution binding")
        payload_row = self.runs._db.execute(
            "SELECT payload_digest,payload_json FROM training_checkpoint_payload WHERE checkpoint_digest=?",
            (checkpoint.digest,),
        ).fetchone()
        if payload_row is None:
            raise TrainingObservationError("resumable checkpoint payload is missing")
        payload = _object(payload_row[1], MAX_PAYLOAD_BYTES)
        if (
            _digest(payload) != payload_row[0]
            or payload_row[0] != checkpoint.payload_digest
            or payload.get("binding_digest") != _digest(binding)
        ):
            raise TrainingObservationError("resumable checkpoint payload identity mismatch")
        if documents is None:
            # Legacy declarations cannot prove prefix work; do not publish their
            # caller-supplied usage/loss as measured operational evidence.
            point["semantic_validation"] = "unavailable_legacy_corpus_bytes"
            return point
        schema = binding["schema_version"]
        if schema == "skeleton.reference_training_binding.v1":
            from .trainer import ReferenceLocalTrainer

            ReferenceLocalTrainer(self.datasets, self.runs)._restore(manifest, binding, checkpoint, documents)
        elif schema == "skeleton.neural_training_binding.v1":
            from .neural_trainer import NeuralLocalTrainer

            NeuralLocalTrainer(self.datasets, self.runs)._restore(manifest, binding, checkpoint, documents)
        elif schema == "skeleton.local_parallel_training_binding.v1":
            from .distributed_trainer import LocalDataParallelTrainer

            LocalDataParallelTrainer(self.datasets, self.runs)._restore(manifest, binding, checkpoint)
        elif schema == "skeleton.local_elastic_training_binding.v1":
            from .elastic_trainer import ElasticLocalTrainer

            ElasticLocalTrainer(self.datasets, self.runs)._restore(manifest, binding, checkpoint)
        elif schema == "skeleton.preference_training_binding.v1":
            from .preference_trainer import PreferenceLocalTrainer

            PreferenceLocalTrainer(
                self.datasets, self.runs, parent_run_id=binding["parent"]["run_id"]
            )._restore(manifest, binding, checkpoint, documents)
        else:
            raise TrainingObservationError("unsupported executable observation binding")
        point.update(
            cursor=payload["cursor"],
            usage=payload["usage"],
            finished=payload["finished"],
            semantic_validation="verified_exact_corpus",
            numerical_health="finite_committed_model",
        )
        if schema == "skeleton.reference_training_binding.v1" and payload["model"] is None:
            point["numerical_health"] = "no_trained_model"
        if "initial_loss" in payload:
            point["loss"] = {
                "initial": payload["initial_loss"],
                "final": payload["final_loss"],
                "available": True,
                "kind": "byte_corpus_cross_entropy",
            }
        if schema == "skeleton.preference_training_binding.v1":
            initial, final = payload["observations"]["initial"], payload["observations"]["final"]
            point["loss"] = {
                "initial": initial["loss"],
                "final": None if final is None else final["loss"],
                "available": True,
                "kind": "dpo_logistic_preference",
            }
            point["preference_observations"] = {
                "initial": initial,
                "final": final,
                "parent_run_id": binding["parent"]["run_id"],
                "reference_model_digest": binding["parent"]["model_digest"],
            }
        barrier = payload.get("barrier")
        if barrier is not None:
            point["barrier"] = {
                "digest": _digest(barrier),
                "index": barrier["barrier_index"],
                "worker_epoch": barrier["worker_epoch"],
                "world_size": barrier["world_size"],
                "ranks": [
                    {
                        key: rank[key]
                        for key in ("rank", "worker_pid", "worker_epoch", "status", "document_index")
                    }
                    for rank in barrier["ranks"]
                ],
            }
            membership = barrier.get("membership")
            if membership is not None:
                point["barrier"]["membership"] = {
                    "digest": _digest(membership),
                    "physical_workers": membership["physical_workers"],
                    "resize_count": membership["resize_count"],
                }
        return point

    def _events(
        self,
        run_id: str,
        manifest: TrainingRunManifest,
        created: datetime,
        now: datetime,
        max_points: int,
        checkpoints: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows = self.runs._db.execute(
            "SELECT telemetry_digest,step,telemetry_json FROM training_telemetry WHERE run_id=? ORDER BY rowid DESC LIMIT ?",
            (run_id, max_points + 1),
        ).fetchall()[::-1]
        points = {point["step"]: point for point in checkpoints}
        maximum_step = max(points, default=-1)
        events: list[dict[str, Any]] = []
        prior_time, prior_step = created, -1
        for digest, step, encoded in rows:
            raw = _object(encoded, MAX_EVENT_BYTES)
            metrics = raw.get("metrics")
            if (
                not isinstance(metrics, dict)
                or not metrics
                or len(metrics) > 128
                or any(
                    not key
                    or len(key.encode()) > 256
                    or isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    for key, value in metrics.items()
                )
            ):
                raise TrainingObservationError("telemetry numeric evidence is invalid")
            event = TrainingTelemetry(**raw)
            _same(raw, event.as_dict())
            timestamp = _timestamp(event.emitted_at)
            if event.digest != digest or event.run_id != run_id or event.step != _integer(step):
                raise TrainingObservationError("telemetry identity mismatch")
            if not prior_time <= timestamp <= now or step < prior_step or step > maximum_step:
                raise TrainingObservationError("telemetry committed timeline or checkpoint step mismatch")
            point = points.get(step)
            if point is not None and _timestamp(point["created_at"]) > timestamp:
                raise TrainingObservationError("telemetry precedes its checkpoint")
            live = (
                self.runs._db.execute(
                    "SELECT 1 FROM training_checkpoint WHERE run_id=? AND step=?", (run_id, step)
                ).fetchone()
                is not None
            )
            if not live:
                # Retention can remove old payloads while preserving their events.
                # No remaining step receipt proves which archive held this event.
                archive_table = self.runs._db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='training_checkpoint_archive'"
                ).fetchone()
                archived = (
                    archive_table is not None
                    and self.runs._db.execute(
                        "SELECT 1 FROM training_checkpoint_archive WHERE run_id=? LIMIT 1", (run_id,)
                    ).fetchone()
                    is not None
                )
                if not archived or not checkpoints:
                    raise TrainingObservationError("telemetry has no committed checkpoint association")
            verified: dict[str, float] = {}
            if point is not None and point["usage"] is not None:
                usage, cursor = point["usage"], point["cursor"]
                expected = {"checkpoint_written": 1, "world_size": manifest.world_size}
                for key, dimension in (
                    ("documents", "documents"),
                    ("resumed_documents", "documents"),
                    ("sgd_updates", "documents"),
                    ("document_updates", "documents"),
                    ("batches", "batches"),
                    ("barriers", "barriers"),
                    ("preference_updates", "pairs"),
                ):
                    if dimension in usage:
                        expected[key] = usage[dimension]
                if "epoch" in cursor:
                    expected["epoch"] = cursor["epoch"]
                if point["barrier"] is not None:
                    expected["active_ranks"] = sum(
                        rank["status"] == "updated" for rank in point["barrier"]["ranks"]
                    )
                for key, value in metrics.items():
                    if key in expected:
                        if value != expected[key]:
                            raise TrainingObservationError(
                                "telemetry counter disagrees with committed checkpoint"
                            )
                        verified[key] = value
            events.append(
                {
                    **event.as_dict(),
                    "telemetry_digest": digest,
                    "checkpoint_digest": None if point is None else point["checkpoint_digest"],
                    "checkpoint_association": (
                        "selected_live"
                        if point
                        else "outside_selected_window" if live else "unavailable_missing_live_checkpoint"
                    ),
                    "verified_counters": verified,
                    "unverified_metric_names": sorted(set(metrics) - set(verified)),
                    "worker_epoch": None,
                }
            )
            prior_time, prior_step = timestamp, step
        return events[-max_points:]

    def _workers(
        self, run_id: str, epoch: int, state: str, created: datetime, now: datetime
    ) -> list[dict[str, Any]]:
        workers = []
        for worker_id, stored_epoch, encoded in self.runs._db.execute(
            "SELECT worker_id,epoch,lease_json FROM worker_lease WHERE run_id=? ORDER BY worker_id", (run_id,)
        ).fetchall():
            raw = _object(encoded, MAX_METADATA_BYTES)
            lease = WorkerLease(**raw)
            _same(raw, lease.as_dict())
            if (
                lease.run_id != run_id
                or lease.worker_id != worker_id
                or lease.epoch != _integer(stored_epoch)
                or lease.epoch > epoch
            ):
                raise TrainingObservationError("worker lease identity mismatch")
            timestamp = _timestamp(lease.issued_at)
            if not created <= timestamp <= now:
                raise TrainingObservationError("worker lease timeline mismatch")
            workers.append(
                {
                    **lease.as_dict(),
                    "lease_digest": lease.token,
                    "epoch_status": "current" if lease.epoch == epoch else "stale",
                    "write_state_eligible": state == "running" and lease.epoch == epoch,
                    "age_seconds": (now - timestamp).total_seconds(),
                    "expiry_available": False,
                }
            )
        return workers

    @staticmethod
    def _budgets(
        manifest: TrainingRunManifest, binding: dict[str, Any] | None, latest: dict[str, Any] | None
    ) -> list[dict[str, Any]]:
        usage = {} if latest is None or latest["usage"] is None else latest["usage"]
        dimensions = {
            "max_steps": "steps",
            "max_tokens": "steps",
            "max_documents": "documents",
            "max_updates": "documents",
            "max_batches": "batches",
            "max_training_bytes": "training_bytes",
            "max_epochs": "epochs",
            "max_barriers": "barriers",
            "max_corpus_bytes": "corpus_bytes",
        }
        result = []
        for name, limit in sorted(manifest.resource_budget.items()):
            actual = usage.get(dimensions.get(name, ""))
            if binding is not None and latest is not None and latest["usage"] is not None:
                if "pairs" in usage and name in {"max_pairs", "max_updates", "max_documents"}:
                    actual = usage["pairs"]
                if name == "max_corpus_bytes" and "training_config" in binding:
                    actual = binding["corpus_bytes"]
                if name == "max_processes":
                    membership = (latest["barrier"] or {}).get("membership")
                    if binding["schema_version"] == "skeleton.local_elastic_training_binding.v1":
                        actual = None if membership is None else membership["physical_workers"]
                    else:
                        actual = manifest.world_size
            if actual is not None and actual > limit:
                raise TrainingObservationError("committed training usage exceeds admitted budget")
            result.append(
                {
                    "name": name,
                    "limit": limit,
                    "used": actual,
                    "fraction": None if actual is None or limit == 0 else actual / limit,
                    "available": actual is not None,
                }
            )
        return result
