"""Checkpoint and failover coordination for swarm runtime recovery."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from threading import RLock
from typing import Mapping

from skeleton.agents.swarm_checkpoint import Checkpoint, CheckpointStore
from skeleton.agents.swarm_failover import FailoverCoordinator, ReplicaState
from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_runtime import SwarmRuntime
from skeleton.agents.swarm_tenant_broker import TenantRepairResult, TenantSwarmBroker
from skeleton.agents.swarm_tenant_checkpoint import (
    TenantCheckpointStore,
    TenantMetadataCheckpoint,
)


RECOVERY_ARCHIVE_VERSION = 1
MAX_RECOVERY_ARCHIVE_BYTES = 8 * 1024 * 1024
_RECOVERY_ARCHIVE_FIELDS = frozenset({
    "version",
    "max_checkpoints",
    "runtime",
    "tenant",
    "archive_checksum",
})
_RUNTIME_RECORD_FIELDS = frozenset({"sequence", "created_at", "checksum", "state"})
_TENANT_RECORD_FIELDS = frozenset({"sequence", "created_at", "checksum", "active", "terminal"})


@dataclass(frozen=True, slots=True)
class RecoveryStatus:
    checkpoints: int
    latest_sequence: int | None
    latest_checksum: str | None
    tenant_checkpoints: int
    latest_tenant_sequence: int | None
    latest_tenant_checksum: str | None
    tenant_aligned: bool
    leader: str | None
    epoch: int


class SwarmRecoveryManager:
    """Own bounded runtime/tenant checkpoints and deterministic failover decisions."""

    def __init__(self, *, max_checkpoints: int = 8) -> None:
        self.store = CheckpointStore(max_checkpoints=max_checkpoints)
        self.tenant_store = TenantCheckpointStore(max_checkpoints=max_checkpoints)
        self.failover = FailoverCoordinator()
        self._replicas: dict[str, ReplicaState] = {}
        self._decision = self.failover.elect(self._replicas)
        self._lock = RLock()

    @staticmethod
    def _json_bytes(payload: object) -> bytes:
        try:
            return json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("recovery archive must contain finite JSON values") from exc

    @classmethod
    def _archive_checksum(cls, payload: Mapping[str, object]) -> str:
        return sha256(cls._json_bytes(payload)).hexdigest()

    @classmethod
    def _enforce_archive_size(cls, archive: object) -> int:
        size = len(cls._json_bytes(archive))
        if size > MAX_RECOVERY_ARCHIVE_BYTES:
            raise ValueError("recovery archive exceeds maximum size")
        return size

    @staticmethod
    def _record(
        mapping: object,
        label: str,
        expected_fields: frozenset[str],
    ) -> Mapping[str, object]:
        if not isinstance(mapping, Mapping):
            raise ValueError(f"invalid {label} archive record")
        fields = set(mapping)
        if fields != expected_fields:
            unknown = sorted(fields - expected_fields)
            missing = sorted(expected_fields - fields)
            details = []
            if unknown:
                details.append(f"unknown={unknown}")
            if missing:
                details.append(f"missing={missing}")
            raise ValueError(f"{label} archive record fields mismatch: {', '.join(details)}")
        return mapping

    @staticmethod
    def _pairs(value: object, label: str) -> tuple[tuple[str, str], ...]:
        if not isinstance(value, list):
            raise ValueError(f"invalid {label} archive pairs")
        pairs: list[tuple[str, str]] = []
        for item in value:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise ValueError(f"invalid {label} archive pair")
            left, right = item
            if not isinstance(left, str) or not isinstance(right, str):
                raise ValueError(f"invalid {label} archive pair")
            pairs.append((left, right))
        return tuple(pairs)

    @staticmethod
    def _sequence(sequence: int) -> int:
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ValueError("checkpoint sequence must be a positive integer")
        return sequence

    def checkpoint(self, runtime: SwarmRuntime, tenant_broker: TenantSwarmBroker | None = None) -> int:
        """Capture runtime and tenant ownership transactionally at one sequence."""
        with self._lock:
            checkpoint = self.store.capture(runtime)
            if tenant_broker is None:
                return checkpoint.sequence
            try:
                self.tenant_store.capture(checkpoint.sequence, tenant_broker)
            except Exception:
                self.store.discard(checkpoint.sequence)
                self.tenant_store.discard(checkpoint.sequence)
                raise
            return checkpoint.sequence

    def export_archive(self) -> dict[str, object]:
        """Return a JSON-serializable, checksummed copy of bounded recovery history."""
        with self._lock:
            runtime_records = [
                {
                    "sequence": item.sequence,
                    "created_at": item.created_at,
                    "checksum": item.checksum,
                    "state": item.state,
                }
                for item in self.store.history()
            ]
            tenant_records = [
                {
                    "sequence": item.sequence,
                    "created_at": item.created_at,
                    "checksum": item.checksum,
                    "active": [list(pair) for pair in item.active],
                    "terminal": [list(pair) for pair in item.terminal],
                }
                for item in self.tenant_store.history()
            ]
            payload: dict[str, object] = {
                "version": RECOVERY_ARCHIVE_VERSION,
                "max_checkpoints": self.store.max_checkpoints,
                "runtime": runtime_records,
                "tenant": tenant_records,
            }
            archive = {**payload, "archive_checksum": self._archive_checksum(payload)}
            self._enforce_archive_size(archive)
            return archive

    def export_archive_bytes(self) -> bytes:
        payload = self._json_bytes(self.export_archive())
        if len(payload) > MAX_RECOVERY_ARCHIVE_BYTES:
            raise ValueError("recovery archive exceeds maximum size")
        return payload

    @classmethod
    def from_archive(cls, archive: Mapping[str, object]) -> "SwarmRecoveryManager":
        """Reconstruct bounded recovery history only after archive and record verification."""
        if not isinstance(archive, Mapping):
            raise ValueError("recovery archive must be a mapping")
        cls._enforce_archive_size(dict(archive))
        fields = set(archive)
        if fields != _RECOVERY_ARCHIVE_FIELDS:
            unknown = sorted(fields - _RECOVERY_ARCHIVE_FIELDS)
            missing = sorted(_RECOVERY_ARCHIVE_FIELDS - fields)
            details = []
            if unknown:
                details.append(f"unknown={unknown}")
            if missing:
                details.append(f"missing={missing}")
            raise ValueError(f"recovery archive fields mismatch: {', '.join(details)}")
        version = archive.get("version")
        if isinstance(version, bool) or not isinstance(version, int) or version != RECOVERY_ARCHIVE_VERSION:
            raise ValueError(f"unsupported recovery archive version: {version}")
        max_checkpoints = archive.get("max_checkpoints")
        if isinstance(max_checkpoints, bool) or not isinstance(max_checkpoints, int) or max_checkpoints < 1:
            raise ValueError("recovery archive max_checkpoints must be a positive integer")
        runtime_raw = archive.get("runtime")
        tenant_raw = archive.get("tenant")
        if not isinstance(runtime_raw, list) or not isinstance(tenant_raw, list):
            raise ValueError("recovery archive histories must be lists")
        if len(runtime_raw) > max_checkpoints or len(tenant_raw) > max_checkpoints:
            raise ValueError("recovery archive exceeds configured history capacity")
        archive_checksum = archive.get("archive_checksum")
        if not isinstance(archive_checksum, str) or not archive_checksum:
            raise ValueError("recovery archive checksum must not be empty")
        payload: dict[str, object] = {
            "version": version,
            "max_checkpoints": max_checkpoints,
            "runtime": runtime_raw,
            "tenant": tenant_raw,
        }
        if cls._archive_checksum(payload) != archive_checksum:
            raise ValueError("recovery archive checksum mismatch")

        manager = cls(max_checkpoints=max_checkpoints)
        for raw in runtime_raw:
            record = cls._record(raw, "runtime checkpoint", _RUNTIME_RECORD_FIELDS)
            state = record.get("state")
            if not isinstance(state, dict):
                raise ValueError("runtime checkpoint state must be a dictionary")
            manager.store.load_verified(
                Checkpoint(
                    sequence=record.get("sequence"),
                    created_at=record.get("created_at"),
                    checksum=record.get("checksum"),
                    state=state,
                )
            )

        runtime_sequences = set(manager.store.sequences())
        for raw in tenant_raw:
            record = cls._record(raw, "tenant checkpoint", _TENANT_RECORD_FIELDS)
            checkpoint = TenantMetadataCheckpoint(
                sequence=record.get("sequence"),
                created_at=record.get("created_at"),
                checksum=record.get("checksum"),
                active=cls._pairs(record.get("active"), "active tenant"),
                terminal=cls._pairs(record.get("terminal"), "terminal tenant"),
            )
            if checkpoint.sequence not in runtime_sequences:
                raise ValueError(f"tenant checkpoint has no runtime checkpoint: {checkpoint.sequence}")
            manager.tenant_store.load_verified(checkpoint)
        return manager

    @classmethod
    def from_archive_bytes(cls, payload: bytes) -> "SwarmRecoveryManager":
        if not isinstance(payload, (bytes, bytearray)):
            raise TypeError("recovery archive payload must be bytes")
        raw = bytes(payload)
        if len(raw) > MAX_RECOVERY_ARCHIVE_BYTES:
            raise ValueError("recovery archive exceeds maximum size")
        try:
            archive = json.loads(raw.decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError("invalid recovery archive payload") from exc
        if not isinstance(archive, dict):
            raise ValueError("recovery archive payload must contain an object")
        return cls.from_archive(archive)

    def restore(self, sequence: int | None = None) -> HardenedSwarmRuntime | None:
        """Restore one retained runtime checkpoint, requeuing any persisted leases."""
        with self._lock:
            checkpoint = self.store.latest() if sequence is None else self.store.get(self._sequence(sequence))
            if checkpoint is None:
                return None
            return HardenedSwarmRuntime.from_state(checkpoint.state, requeue_leased=True)

    def restore_latest(self) -> HardenedSwarmRuntime | None:
        return self.restore()

    def restore_tenants(
        self,
        tenant_broker: TenantSwarmBroker,
        sequence: int | None = None,
    ) -> TenantRepairResult | None:
        """Restore tenant ownership for a runtime checkpoint when sidecar metadata exists."""
        with self._lock:
            target_sequence = sequence
            if target_sequence is None:
                latest = self.store.latest()
                if latest is None:
                    return None
                target_sequence = latest.sequence
            else:
                target_sequence = self._sequence(target_sequence)
            if self.tenant_store.get(target_sequence) is None:
                return None
            if self.store.get(target_sequence) is None:
                raise ValueError(f"tenant checkpoint has no runtime checkpoint: {target_sequence}")
            return self.tenant_store.restore(tenant_broker, target_sequence)

    def elect(self, replicas: Mapping[str, ReplicaState]) -> str | None:
        with self._lock:
            self._replicas = dict(replicas)
            self._decision = self.failover.elect(self._replicas)
            return self._decision.leader_id

    def status(self) -> RecoveryStatus:
        with self._lock:
            latest = self.store.latest()
            latest_tenant = self.tenant_store.latest()
            runtime_sequence = None if latest is None else latest.sequence
            tenant_sequence = None if latest_tenant is None else latest_tenant.sequence
            return RecoveryStatus(
                checkpoints=len(self.store),
                latest_sequence=runtime_sequence,
                latest_checksum=None if latest is None else latest.checksum,
                tenant_checkpoints=len(self.tenant_store),
                latest_tenant_sequence=tenant_sequence,
                latest_tenant_checksum=None if latest_tenant is None else latest_tenant.checksum,
                tenant_aligned=(tenant_sequence is None or tenant_sequence == runtime_sequence),
                leader=self._decision.leader_id,
                epoch=self._decision.epoch,
            )
