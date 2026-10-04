"""Bounded CAS backup and recovery helpers for the existing training authority."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from skeleton.storage.cas import (
    AddressedObject,
    GovernedContentStore,
    StorageContractError,
)

from .control import (
    MAX_CHECKPOINT_PAYLOAD_BYTES,
    TrainingCheckpoint,
    TrainingRepository,
    TrainingRunManifest,
    TrainingStateError,
    WorkerLease,
    _canonical,
    _digest,
    _require_utc_timestamp,
)
from .data import DatasetRegistry
from .trainer import ReferenceLocalTrainer, corpus_digest

ARCHIVE_SCHEMA = "skeleton.training_checkpoint_archive.v1"
MAX_ARCHIVE_BYTES = MAX_CHECKPOINT_PAYLOAD_BYTES + 2 * 1024 * 1024
MAX_RETAINED_COUNT = 1024
_SCHEMA_PAIRS = {
    "skeleton.reference_training_resume.v1": "skeleton.reference_training_binding.v1",
    "skeleton.neural_training_resume.v1": "skeleton.neural_training_binding.v1",
    "skeleton.local_parallel_training_resume.v1": "skeleton.local_parallel_training_binding.v1",
}


class CheckpointArchiveError(TrainingStateError):
    """A backup cannot be trusted or its requested mutation is unsafe."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class CheckpointArchiveReceipt:
    tenant_id: str
    logical_id: str
    version: int
    trust_context: str
    content_algorithm: str
    content_digest: str
    archive_sha256: str
    size_bytes: int
    run_id: str
    manifest_digest: str
    binding_digest: str
    checkpoint_digest: str
    payload_digest: str
    payload_schema: str

    def as_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> CheckpointArchiveReceipt:
        if set(value) != set(cls.__dataclass_fields__):
            raise CheckpointArchiveError("invalid archive receipt fields")
        return cls(**value)


@dataclass(frozen=True, slots=True)
class CheckpointArchiveContents:
    """Verified backup inputs; reading them does not register or authorize a run."""

    manifest: TrainingRunManifest
    binding: Mapping[str, Any]
    checkpoint: TrainingCheckpoint
    payload: Mapping[str, Any]
    operator_request: Mapping[str, Any] | None


class _PayloadView:
    """Read-only input to the existing trainers' semantic restore validators."""

    def __init__(self, checkpoint: TrainingCheckpoint, payload: dict[str, Any]) -> None:
        self.checkpoint = checkpoint
        self.payload = payload

    def checkpoint_payload(self, checkpoint: TrainingCheckpoint) -> dict[str, Any]:
        if checkpoint != self.checkpoint:
            raise CheckpointArchiveError("validation checkpoint substitution")
        return self.payload


class TrainingCheckpointArchive:
    """Store immutable backups in CAS; retain authority in TrainingRepository.

    The additive receipt/reference tables use the repository's writer transaction.
    They do not authorize datasets, manufacture manifests, or remove CAS objects.
    """

    def __init__(
        self,
        runs: TrainingRepository,
        store: GovernedContentStore,
        *,
        tenant_id: str,
        trust_context: str,
    ) -> None:
        for name, value in (("tenant_id", tenant_id), ("trust_context", trust_context)):
            if not isinstance(value, str) or not value.strip() or len(value.encode()) > 256:
                raise ValueError(f"{name} must be non-empty and bounded")
        self.runs = runs
        self.store = store
        self.tenant_id = tenant_id
        self.trust_context = trust_context
        with runs._write():
            runs._db.execute("""CREATE TABLE IF NOT EXISTS training_checkpoint_archive (
                    checkpoint_digest TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    receipt_digest TEXT NOT NULL,
                    receipt_json TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES training_run(run_id)
                )""")
            runs._db.execute("""CREATE TABLE IF NOT EXISTS training_checkpoint_reference (
                    run_id TEXT NOT NULL,
                    reference_id TEXT NOT NULL,
                    checkpoint_digest TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    PRIMARY KEY(run_id, reference_id),
                    FOREIGN KEY(run_id) REFERENCES training_run(run_id),
                    FOREIGN KEY(checkpoint_digest) REFERENCES training_checkpoint(checkpoint_digest)
                )""")

    def _receipt(self, run_id: str, checkpoint_digest: str) -> CheckpointArchiveReceipt:
        row = self.runs._db.execute(
            "SELECT receipt_digest,receipt_json FROM training_checkpoint_archive "
            "WHERE run_id=? AND checkpoint_digest=?",
            (run_id, checkpoint_digest),
        ).fetchone()
        if row is None:
            raise CheckpointArchiveError("checkpoint has no committed backup receipt")
        try:
            value = json.loads(row[1])
            receipt = CheckpointArchiveReceipt.from_dict(value)
            if (
                receipt.digest != row[0]
                or receipt.run_id != run_id
                or receipt.checkpoint_digest != checkpoint_digest
            ):
                raise ValueError("receipt identity mismatch")
        except (ValueError, TypeError, KeyError) as exc:
            raise CheckpointArchiveError("stored archive receipt identity mismatch") from exc
        return receipt

    @staticmethod
    def _validate_operator(
        snapshot: dict[str, Any] | None,
        manifest: TrainingRunManifest,
        datasets: DatasetRegistry | None = None,
    ) -> None:
        if snapshot is None:
            return
        try:
            if not isinstance(snapshot, dict) or set(snapshot) != {
                "run_id",
                "request_digest",
                "request",
                "acquired_at",
                "dataset_version",
            }:
                raise ValueError("invalid operator snapshot fields")
            request = snapshot["request"]
            if (
                not isinstance(request, dict)
                or set(request)
                != {
                    "schema_version",
                    "run_id",
                    "dataset_id",
                    "sources",
                    "rights_refs",
                    "classification",
                    "parameters",
                    "seed",
                    "budget",
                    "code_digest",
                    "environment_digest",
                }
                or request["schema_version"] != "skeleton.governed_cli_request.v1"
                or len(_canonical(request).encode()) > 1024 * 1024
                or snapshot["request_digest"] != _digest(request)
                or snapshot["run_id"] != manifest.run_id
                or request["run_id"] != manifest.run_id
                or request["code_digest"] != manifest.code_digest
                or request["environment_digest"] != manifest.environment_digest
                or request["seed"] != manifest.seed
                or request["parameters"] != dict(manifest.hyperparameters)
                or request["budget"] != dict(manifest.resource_budget)
                or type(snapshot["dataset_version"]) is not int
                or snapshot["dataset_version"] < 0
            ):
                raise ValueError("operator request identity mismatch")
            if (
                not isinstance(snapshot["acquired_at"], str)
                or _require_utc_timestamp(snapshot["acquired_at"], field="acquired_at")
                != snapshot["acquired_at"]
            ):
                raise ValueError("operator acquisition must use canonical UTC")
            if datasets is not None:
                dataset = datasets.require_training_ready(manifest.dataset_digest)
                ingestion = datasets.materialized_ingestion("cli:" + manifest.run_id)
                if (
                    ingestion is None
                    or ingestion.dataset_digest != manifest.dataset_digest
                    or request["dataset_id"] != dataset.dataset_id
                    or request["classification"] != dataset.classification
                    or int(dataset.version) != snapshot["dataset_version"] + 1
                ):
                    raise ValueError("operator ingestion/version identity mismatch")
                sources = datasets.materialized_sources(manifest.dataset_digest)
                if not isinstance(request["sources"], list) or len(request["sources"]) != len(sources):
                    raise ValueError("operator source count mismatch")
                for requested, source in zip(request["sources"], sources, strict=True):
                    if (
                        not isinstance(requested, dict)
                        or set(requested) != {"path", "content_digest"}
                        or Path(requested["path"]).as_uri() != source.envelope.source_id
                        or requested["content_digest"] != source.envelope.content_digest
                        or tuple(request["rights_refs"]) != source.rights_refs
                    ):
                        raise ValueError("operator source/rights identity mismatch")
        except (ValueError, TypeError, KeyError) as exc:
            raise CheckpointArchiveError("invalid governed CLI recovery snapshot") from exc

    def _operator_snapshot(self, manifest: TrainingRunManifest) -> dict[str, Any] | None:
        exists = self.runs._db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='governed_cli_request'"
        ).fetchone()
        if exists is None:
            return None
        row = self.runs._db.execute(
            "SELECT request_digest,request_json,acquired_at,dataset_version FROM governed_cli_request WHERE run_id=?",
            (manifest.run_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            request = json.loads(row[1])
            if _canonical(request) != row[1]:
                raise ValueError("noncanonical admitted request")
            snapshot = {
                "run_id": manifest.run_id,
                "request_digest": row[0],
                "request": request,
                "acquired_at": row[2],
                "dataset_version": row[3],
            }
            self._validate_operator(snapshot, manifest)
            return snapshot
        except (ValueError, TypeError, KeyError) as exc:
            raise CheckpointArchiveError("corrupt admitted governed CLI request") from exc

    def _restore_operator(self, snapshot: dict[str, Any] | None) -> None:
        if snapshot is None:
            return
        self.runs._db.execute(
            "CREATE TABLE IF NOT EXISTS governed_cli_request ("
            "run_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL, "
            "request_json TEXT NOT NULL, acquired_at TEXT NOT NULL, dataset_version INTEGER NOT NULL)"
        )
        encoded = _canonical(snapshot["request"])
        row = self.runs._db.execute(
            "SELECT request_digest,request_json,acquired_at,dataset_version FROM governed_cli_request WHERE run_id=?",
            (snapshot["run_id"],),
        ).fetchone()
        expected = (snapshot["request_digest"], encoded, snapshot["acquired_at"], snapshot["dataset_version"])
        if row is not None:
            if row != expected:
                raise CheckpointArchiveError("restore conflicts with admitted governed CLI request")
            return
        self.runs._db.execute(
            "INSERT INTO governed_cli_request(run_id,request_digest,request_json,acquired_at,dataset_version) "
            "VALUES (?,?,?,?,?)",
            (snapshot["run_id"], *expected),
        )

    @staticmethod
    def _decode(
        data: bytes,
    ) -> tuple[
        TrainingRunManifest, dict[str, Any], TrainingCheckpoint, dict[str, Any], dict[str, Any] | None
    ]:
        try:
            if len(data) > MAX_ARCHIVE_BYTES:
                raise ValueError("archive byte limit exceeded")
            value = json.loads(data)
            if (
                not isinstance(value, dict)
                or set(value)
                != {"schema_version", "manifest", "binding", "checkpoint", "payload", "operator_request"}
                or value["schema_version"] != ARCHIVE_SCHEMA
                or _canonical(value).encode() != data
            ):
                raise ValueError("unsupported or noncanonical archive envelope")
            manifest = TrainingRunManifest.from_dict(value["manifest"])
            checkpoint = TrainingCheckpoint.from_dict(value["checkpoint"])
            binding, payload = value["binding"], value["payload"]
            if (
                manifest.as_dict() != value["manifest"]
                or checkpoint.as_dict() != value["checkpoint"]
                or not isinstance(binding, dict)
                or not isinstance(payload, dict)
                or len(_canonical(payload).encode()) > MAX_CHECKPOINT_PAYLOAD_BYTES
                or payload.get("schema_version") not in _SCHEMA_PAIRS
                or binding.get("schema_version") != _SCHEMA_PAIRS[payload["schema_version"]]
                or binding.get("manifest_digest") != manifest.digest
                or binding.get("dataset_digest") != manifest.dataset_digest
                or checkpoint.run_id != manifest.run_id
                or checkpoint.manifest_digest != manifest.digest
                or checkpoint.payload_digest != _digest(payload)
                or payload.get("binding_digest") != _digest(binding)
            ):
                raise ValueError("archive schema or identity mismatch")
            TrainingCheckpointArchive._validate_operator(value["operator_request"], manifest)
            return manifest, binding, checkpoint, payload, value["operator_request"]
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise CheckpointArchiveError("invalid checkpoint archive envelope") from exc

    @staticmethod
    def _validate_model(
        datasets: DatasetRegistry,
        manifest: TrainingRunManifest,
        binding: dict[str, Any],
        checkpoint: TrainingCheckpoint,
        payload: dict[str, Any],
        corpus: Sequence[str],
    ) -> None:
        try:
            documents = tuple(corpus)
            datasets.validate_training_corpus(
                manifest.dataset_digest, documents, split_name=binding["split_name"]
            )
            if (
                binding["corpus_digest"] != corpus_digest(documents)
                or binding["document_sequence_digest"] != _digest(documents)
                or binding["document_count"] != len(documents)
                or binding["split_digest"] != corpus_digest(documents)
            ):
                raise ValueError("archive corpus identity mismatch")
            # Reuse the executable trainer validators without installing untrusted
            # bytes in the authoritative database merely to validate them.
            view = cast(TrainingRepository, _PayloadView(checkpoint, payload))
            if payload["schema_version"] == "skeleton.reference_training_resume.v1":
                ReferenceLocalTrainer(datasets, view)._restore(manifest, binding, checkpoint, documents)
            elif payload["schema_version"] == "skeleton.neural_training_resume.v1":
                from .neural_trainer import NeuralLocalTrainer

                NeuralLocalTrainer(datasets, view)._restore(manifest, binding, checkpoint, documents)
            elif payload["schema_version"] == "skeleton.local_parallel_training_resume.v1":
                from .distributed_trainer import LocalDataParallelTrainer

                LocalDataParallelTrainer(datasets, view)._restore(manifest, binding, checkpoint)
            else:
                raise ValueError("unsupported archive payload schema")
        except (ValueError, TypeError, KeyError, TrainingStateError) as exc:
            raise CheckpointArchiveError("archive model or resume compatibility failed") from exc

    def _read(
        self, receipt: CheckpointArchiveReceipt, *, require_commit: bool = True
    ) -> tuple[
        TrainingRunManifest, dict[str, Any], TrainingCheckpoint, dict[str, Any], dict[str, Any] | None
    ]:
        try:
            if receipt.tenant_id != self.tenant_id or receipt.trust_context != self.trust_context:
                raise ValueError("archive tenant or trust-context mismatch")
            if (
                isinstance(receipt.version, bool)
                or receipt.version != 1
                or receipt.logical_id != f"training-checkpoint:{receipt.checkpoint_digest}"
                or isinstance(receipt.size_bytes, bool)
                or not isinstance(receipt.size_bytes, int)
                or not 0 < receipt.size_bytes <= MAX_ARCHIVE_BYTES
            ):
                raise ValueError("archive logical identity mismatch")
            addressed, data = self.store.get(
                tenant_id=receipt.tenant_id, logical_id=receipt.logical_id, version=receipt.version
            )
            if (
                addressed.tenant_id != receipt.tenant_id
                or addressed.logical_id != receipt.logical_id
                or addressed.version != receipt.version
                or addressed.trust_context != receipt.trust_context
                or addressed.size_bytes != receipt.size_bytes
                or len(data) != receipt.size_bytes
                or _sha256(data) != receipt.archive_sha256
                or hashlib.new(addressed.digest.algorithm, data).hexdigest() != addressed.digest.value
                or hashlib.new(receipt.content_algorithm, data).hexdigest() != receipt.content_digest
                or receipt.content_algorithm not in self.store.digest_policy.accepted_algorithms
                or addressed.digest.algorithm not in self.store.digest_policy.accepted_algorithms
            ):
                raise ValueError("archive content address or bytes mismatch")
            manifest, binding, checkpoint, payload, operator = self._decode(data)
            if (
                manifest.run_id != receipt.run_id
                or manifest.digest != receipt.manifest_digest
                or _digest(binding) != receipt.binding_digest
                or checkpoint.digest != receipt.checkpoint_digest
                or checkpoint.payload_digest != receipt.payload_digest
                or payload["schema_version"] != receipt.payload_schema
            ):
                raise ValueError("archive receipt/envelope identity mismatch")
            if require_commit:
                self._verify_commit(receipt)
            return manifest, binding, checkpoint, payload, operator
        except (ValueError, TypeError, KeyError, StorageContractError) as exc:
            raise CheckpointArchiveError("checkpoint archive bytes are unavailable or corrupt") from exc

    @staticmethod
    def _commit_bytes(receipt: CheckpointArchiveReceipt) -> bytes:
        return _canonical(
            {
                "schema_version": "skeleton.training_checkpoint_backup_commit.v1",
                "receipt_digest": receipt.digest,
                "receipt": receipt.as_dict(),
            }
        ).encode()

    def _verify_commit(self, receipt: CheckpointArchiveReceipt) -> None:
        logical_id = f"training-checkpoint-commit:{receipt.checkpoint_digest}"
        addressed, data = self.store.get(
            tenant_id=receipt.tenant_id,
            logical_id=logical_id,
            version=1,
        )
        if (
            addressed.tenant_id != receipt.tenant_id
            or addressed.logical_id != logical_id
            or addressed.version != 1
            or addressed.size_bytes != len(data)
            or addressed.trust_context != receipt.trust_context
            or data != self._commit_bytes(receipt)
            or addressed.digest.algorithm not in self.store.digest_policy.accepted_algorithms
            or hashlib.new(addressed.digest.algorithm, data).hexdigest() != addressed.digest.value
        ):
            raise CheckpointArchiveError("backup commit proof identity mismatch")

    def _publish_commit(self, receipt: CheckpointArchiveReceipt) -> None:
        # The caller reaches this only after the TrainingRepository transaction
        # has committed. Trusted CAS writer authority publishes the transfer
        # proof; it is an operational receipt, not a cryptographic signature.
        with self.runs._lock:
            if self._receipt(receipt.run_id, receipt.checkpoint_digest) != receipt:
                raise CheckpointArchiveError("backup receipt was not committed")
        self.store.put(
            tenant_id=receipt.tenant_id,
            logical_id=f"training-checkpoint-commit:{receipt.checkpoint_digest}",
            version=1,
            trust_context=receipt.trust_context,
            payload=self._commit_bytes(receipt),
        )
        self._verify_commit(receipt)

    @staticmethod
    def _make_receipt(
        addressed: AddressedObject,
        data: bytes,
        manifest: TrainingRunManifest,
        binding: dict[str, Any],
        checkpoint: TrainingCheckpoint,
        payload: dict[str, Any],
    ) -> CheckpointArchiveReceipt:
        return CheckpointArchiveReceipt(
            tenant_id=addressed.tenant_id,
            logical_id=addressed.logical_id,
            version=addressed.version,
            trust_context=addressed.trust_context,
            content_algorithm=addressed.digest.algorithm,
            content_digest=addressed.digest.value,
            archive_sha256=_sha256(data),
            size_bytes=len(data),
            run_id=manifest.run_id,
            manifest_digest=manifest.digest,
            binding_digest=_digest(binding),
            checkpoint_digest=checkpoint.digest,
            payload_digest=cast(str, checkpoint.payload_digest),
            payload_schema=payload["schema_version"],
        )

    def backup(
        self,
        run_id: str,
        datasets: DatasetRegistry,
        corpus: Sequence[str],
        *,
        checkpoint_digest: str | None = None,
    ) -> CheckpointArchiveReceipt:
        # Follow the trainers' dataset -> training lock order. Holding the
        # training writer while waiting for dataset revocation would deadlock
        # an update which already owns the dataset authority guard.
        with self.runs._lock:
            manifest = self.runs.manifest(run_id)
            binding = self.runs.execution_binding(run_id)
        if binding is None:
            raise CheckpointArchiveError("backup requires a bound executable run")
        with (
            datasets.training_authority(manifest.dataset_digest, binding["dataset_authority_epoch"]),
            self.runs._write(),
        ):
            checkpoints = self.runs.checkpoints(run_id)
            checkpoint = next(
                (
                    item
                    for item in checkpoints
                    if checkpoint_digest is None or item.digest == checkpoint_digest
                ),
                None,
            )
            if checkpoint is None:
                raise CheckpointArchiveError("backup requires a durable checkpoint")
            payload = self.runs.checkpoint_payload(checkpoint)
            operator = self._operator_snapshot(manifest)
            self._validate_operator(operator, manifest, datasets)
            data = _canonical(
                {
                    "schema_version": ARCHIVE_SCHEMA,
                    "manifest": manifest.as_dict(),
                    "binding": binding,
                    "checkpoint": checkpoint.as_dict(),
                    "payload": payload,
                    "operator_request": operator,
                }
            ).encode()
            self._decode(data)
            self._validate_model(datasets, manifest, binding, checkpoint, payload, corpus)
            addressed = self.store.put(
                tenant_id=self.tenant_id,
                logical_id=f"training-checkpoint:{checkpoint.digest}",
                version=1,
                trust_context=self.trust_context,
                payload=data,
            )
            receipt = self._make_receipt(addressed, data, manifest, binding, checkpoint, payload)
            self._read(receipt, require_commit=False)
            existing = self.runs._db.execute(
                "SELECT receipt_digest FROM training_checkpoint_archive WHERE checkpoint_digest=?",
                (checkpoint.digest,),
            ).fetchone()
            if existing is not None:
                previous = self._receipt(run_id, checkpoint.digest)
                self._read(previous, require_commit=False)
                # CAS may have migrated its current digest alias. Preserve the
                # already committed backup identity after validating both.
                receipt = previous
            else:
                self.runs._db.execute(
                    "INSERT INTO training_checkpoint_archive VALUES (?,?,?,?)",
                    (checkpoint.digest, run_id, receipt.digest, _canonical(receipt.as_dict())),
                )
        self._publish_commit(receipt)
        return receipt

    def receipts(self, run_id: str) -> tuple[CheckpointArchiveReceipt, ...]:
        with self.runs._lock:
            self.runs.manifest(run_id)
            rows = self.runs._db.execute(
                "SELECT checkpoint_digest FROM training_checkpoint_archive WHERE run_id=? ORDER BY checkpoint_digest",
                (run_id,),
            ).fetchall()
            return tuple(self._receipt(run_id, row[0]) for row in rows)

    def verify_backup(
        self, receipt: CheckpointArchiveReceipt, datasets: DatasetRegistry, corpus: Sequence[str]
    ) -> CheckpointArchiveContents:
        """Recover exact registration inputs from CAS without writing training state."""
        manifest, binding, checkpoint, payload, operator = self._read(receipt)
        with datasets.training_authority(manifest.dataset_digest, binding["dataset_authority_epoch"]):
            self._validate_model(datasets, manifest, binding, checkpoint, payload, corpus)
            self._validate_operator(operator, manifest, datasets)
        return CheckpointArchiveContents(manifest, binding, checkpoint, payload, operator)

    def restore(
        self,
        receipt: CheckpointArchiveReceipt,
        datasets: DatasetRegistry,
        corpus: Sequence[str],
    ) -> TrainingCheckpoint:
        manifest, binding, checkpoint, payload, operator = self._read(receipt)
        with datasets.training_authority(manifest.dataset_digest, binding["dataset_authority_epoch"]):
            self._validate_model(datasets, manifest, binding, checkpoint, payload, corpus)
            self._validate_operator(operator, manifest, datasets)
            with self.runs._write():
                if self.runs.manifest(manifest.run_id).as_dict() != manifest.as_dict():
                    raise CheckpointArchiveError("restore target manifest/code/environment identity mismatch")
                if self.runs.execution_binding(manifest.run_id) != binding:
                    raise CheckpointArchiveError("restore target execution binding mismatch")
                state = self.runs.state(manifest.run_id)
                latest = self.runs.latest_checkpoint(manifest.run_id)
                if latest is not None and latest.step > checkpoint.step:
                    raise CheckpointArchiveError("restore cannot rewind a newer durable checkpoint")
                if (
                    latest is not None
                    and latest.step == checkpoint.step
                    and latest.digest != checkpoint.digest
                ):
                    raise CheckpointArchiveError("restore checkpoint conflicts with durable target step")
                if state == "completed":
                    if latest is None or latest.digest != checkpoint.digest:
                        raise CheckpointArchiveError("completed target is immutable")
                    self.runs.checkpoint_payload(latest)
                    self._restore_operator(operator)
                    return latest
                if state not in {"registered", "recovering", "running", "failed"}:
                    raise CheckpointArchiveError("restore target state is incompatible")
                self._restore_operator(operator)
                if latest is None or latest.digest != checkpoint.digest:
                    self.runs._db.execute(
                        "INSERT INTO training_checkpoint VALUES (?,?,?,?)",
                        (
                            checkpoint.digest,
                            manifest.run_id,
                            checkpoint.step,
                            _canonical(checkpoint.as_dict()),
                        ),
                    )
                    self.runs._db.execute(
                        "INSERT INTO training_checkpoint_payload VALUES (?,?,?)",
                        (checkpoint.digest, checkpoint.payload_digest, _canonical(payload)),
                    )
                else:
                    if self.runs.checkpoint_payload(latest) != payload:
                        raise CheckpointArchiveError("restore durable target payload mismatch")
                existing = self.runs._db.execute(
                    "SELECT receipt_digest FROM training_checkpoint_archive WHERE checkpoint_digest=?",
                    (checkpoint.digest,),
                ).fetchone()
                if existing is None:
                    self.runs._db.execute(
                        "INSERT INTO training_checkpoint_archive VALUES (?,?,?,?)",
                        (checkpoint.digest, manifest.run_id, receipt.digest, _canonical(receipt.as_dict())),
                    )
                elif self._receipt(manifest.run_id, checkpoint.digest) != receipt:
                    raise CheckpointArchiveError("restore backup receipt conflict")
                current_epoch = self.runs._epoch(manifest.run_id)
                next_epoch = max(current_epoch + (state != "recovering"), checkpoint.worker_epoch + 1)
                self.runs._db.execute(
                    "UPDATE training_run SET state='recovering',worker_epoch=? WHERE run_id=?",
                    (next_epoch, manifest.run_id),
                )
                self.runs._db.execute("DELETE FROM worker_lease WHERE run_id=?", (manifest.run_id,))
                self.runs._db.execute(
                    "INSERT OR REPLACE INTO training_checkpoint_reference VALUES (?,?,?,?)",
                    (manifest.run_id, "archive-recovery", checkpoint.digest, "recovery"),
                )
        return checkpoint

    def _reference_lease(self, run_id: str, lease: WorkerLease | None) -> None:
        if self.runs.state(run_id) == "running":
            if lease is None or lease.run_id != run_id:
                raise CheckpointArchiveError(
                    "running checkpoint reference mutation requires its worker lease"
                )
            self.runs.assert_worker_current(lease)
        elif lease is not None:
            raise CheckpointArchiveError("reference lease requires a running run")

    def pin(
        self,
        run_id: str,
        checkpoint_digest: str,
        reference_id: str,
        *,
        kind: str = "recovery",
        lease: WorkerLease | None = None,
    ) -> None:
        if not isinstance(reference_id, str) or not reference_id.strip() or len(reference_id.encode()) > 256:
            raise ValueError("checkpoint reference ID must be non-empty and bounded")
        if kind not in {"active", "recovery"}:
            raise ValueError("checkpoint reference kind must be active or recovery")
        with self.runs._write():
            self._reference_lease(run_id, lease)
            if not any(item.digest == checkpoint_digest for item in self.runs.checkpoints(run_id)):
                raise CheckpointArchiveError("checkpoint reference requires a durable run checkpoint")
            self.runs._db.execute(
                "INSERT OR REPLACE INTO training_checkpoint_reference VALUES (?,?,?,?)",
                (run_id, reference_id, checkpoint_digest, kind),
            )

    def unpin(self, run_id: str, reference_id: str, *, lease: WorkerLease | None = None) -> None:
        with self.runs._write():
            self._reference_lease(run_id, lease)
            self.runs._db.execute(
                "DELETE FROM training_checkpoint_reference WHERE run_id=? AND reference_id=?",
                (run_id, reference_id),
            )

    def retain(self, run_id: str, *, keep_newest: int = 2) -> tuple[str, ...]:
        if (
            isinstance(keep_newest, bool)
            or not isinstance(keep_newest, int)
            or not 1 <= keep_newest <= MAX_RETAINED_COUNT
        ):
            raise ValueError("retained checkpoint count must be in [1, 1024]")
        with self.runs._write():
            checkpoints = self.runs.checkpoints(run_id)
            protected = {item.digest for item in checkpoints[:keep_newest]}
            protected.update(
                row[0]
                for row in self.runs._db.execute(
                    "SELECT checkpoint_digest FROM training_checkpoint_reference WHERE run_id=?", (run_id,)
                ).fetchall()
            )
            removed = []
            for checkpoint in checkpoints:
                if checkpoint.digest in protected:
                    continue
                row = self.runs._db.execute(
                    "SELECT 1 FROM training_checkpoint_archive WHERE run_id=? AND checkpoint_digest=?",
                    (run_id, checkpoint.digest),
                ).fetchone()
                if row is None:
                    continue
                _, _, backed_up, _, _ = self._read(self._receipt(run_id, checkpoint.digest))
                if backed_up != checkpoint:
                    raise CheckpointArchiveError("retention backup checkpoint identity mismatch")
                removed.append(checkpoint.digest)
            for digest in removed:
                self.runs._db.execute(
                    "DELETE FROM training_checkpoint_payload WHERE checkpoint_digest=?", (digest,)
                )
                self.runs._db.execute("DELETE FROM training_checkpoint WHERE checkpoint_digest=?", (digest,))
            return tuple(removed)
