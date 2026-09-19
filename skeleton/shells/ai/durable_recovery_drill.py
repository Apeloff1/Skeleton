"""Signed non-destructive disaster-recovery drill evidence.

A recovery drill validates a restored target against a signed backup manifest
and records operational observations such as source-to-backup sequence lag and
verification duration.  The drill never performs the restore itself and grants
no restore, pruning, or execution authority.

Success means the supplied restored target passed the selected restore policy
and the configured recovery objectives were met.  Repeated named drills form a
monotonic signed history so operators can detect regressions relative to the
previous exercise.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import time
from typing import Callable, Iterable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.durable_backup_manifest import (
    DurableBackupManifest,
    DurableBackupManifestStore,
)
from skeleton.shells.ai.durable_restore_validation import (
    DurableRestoreMode,
    DurableRestoreReport,
    DurableRestoreVerifier,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
    SignedArtifact,
)
from skeleton.shells.ai.store_protocol import VersionedStateBackend


def _digest(
    name: str,
    value: str,
    *,
    optional: bool = False,
) -> str:
    if optional and not value:
        return ""
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be 64-character digest")
    return value.lower()


def _identity(
    name: str,
    value: str,
    *,
    maximum: int,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
    ):
        raise ValueError(f"invalid {name}")
    return value


def _timestamp(name: str, value: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(f"{name} must be finite and non-negative")
    return float(value)


def _stable_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class DurableRecoveryDrillPolicy:
    max_chains: int = 32
    max_verification_seconds: float = 300.0
    max_sequence_lag: int = 10_000
    require_restore_verified: bool = True
    require_source_ancestry: bool = True

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_chains, bool)
            or not isinstance(self.max_chains, int)
            or self.max_chains <= 0
        ):
            raise ValueError(
                "max_chains must be positive integer"
            )
        if (
            isinstance(self.max_sequence_lag, bool)
            or not isinstance(self.max_sequence_lag, int)
            or self.max_sequence_lag < 0
        ):
            raise ValueError(
                "max_sequence_lag must be non-negative integer"
            )
        if (
            isinstance(self.max_verification_seconds, bool)
            or not isinstance(
                self.max_verification_seconds,
                (int, float),
            )
            or not math.isfinite(
                float(self.max_verification_seconds)
            )
            or float(self.max_verification_seconds) <= 0.0
        ):
            raise ValueError(
                "max_verification_seconds must be finite and positive"
            )
        object.__setattr__(
            self,
            "max_verification_seconds",
            float(self.max_verification_seconds),
        )
        for name in (
            "require_restore_verified",
            "require_source_ancestry",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict()
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "max_chains": self.max_chains,
            "max_verification_seconds": (
                self.max_verification_seconds
            ),
            "max_sequence_lag": (
                self.max_sequence_lag
            ),
            "require_restore_verified": (
                self.require_restore_verified
            ),
            "require_source_ancestry": (
                self.require_source_ancestry
            ),
        }


@dataclass(frozen=True)
class DurableRecoveryDrillMember:
    chain_id: str
    backup_sequence: int
    backup_root: str
    source_sequence: int
    source_root: str
    sequence_lag: int
    backup_root_is_source_ancestor: bool
    restore_state: str
    restore_exact_head: bool
    restore_expected_root_is_ancestor: bool

    def __post_init__(self) -> None:
        _identity(
            "chain_id",
            self.chain_id,
            maximum=128,
        )
        for name in (
            "backup_root",
            "source_root",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                ),
            )
        for name in (
            "backup_sequence",
            "source_sequence",
            "sequence_lag",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be non-negative integer"
                )
        if (
            self.source_sequence
            < self.backup_sequence
        ):
            raise ValueError(
                "source sequence may not precede backup in drill member"
            )
        if (
            self.sequence_lag
            != self.source_sequence
            - self.backup_sequence
        ):
            raise ValueError(
                "sequence_lag does not match source/backup positions"
            )
        for name in (
            "backup_root_is_source_ancestor",
            "restore_exact_head",
            "restore_expected_root_is_ancestor",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )
        if (
            not isinstance(self.restore_state, str)
            or not self.restore_state
            or len(self.restore_state) > 64
        ):
            raise ValueError(
                "invalid restore_state"
            )

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.to_dict(include_digest=False)
        )

    def to_dict(
        self,
        *,
        include_digest: bool = True,
    ) -> dict[str, object]:
        data: dict[str, object] = {
            "chain_id": self.chain_id,
            "backup_sequence": (
                self.backup_sequence
            ),
            "backup_root": self.backup_root,
            "source_sequence": (
                self.source_sequence
            ),
            "source_root": self.source_root,
            "sequence_lag": self.sequence_lag,
            "backup_root_is_source_ancestor": (
                self.backup_root_is_source_ancestor
            ),
            "restore_state": self.restore_state,
            "restore_exact_head": (
                self.restore_exact_head
            ),
            "restore_expected_root_is_ancestor": (
                self.restore_expected_root_is_ancestor
            ),
        }
        if include_digest:
            data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class DurableRecoveryDrill:
    schema_version: int
    drill_id: str
    drill_name: str
    generation: int
    previous_drill_id: str
    previous_drill_digest: str
    backup_manifest_id: str
    backup_manifest_digest: str
    backup_generation: int
    restore_report_digest: str
    restore_mode: str
    operator_id: str
    started_at: float
    completed_at: float
    duration_seconds: float
    policy_digest: str
    members: tuple[DurableRecoveryDrillMember, ...]
    restore_verified: bool
    verification_time_met: bool
    sequence_lag_met: bool
    regression: bool
    regression_reasons: tuple[str, ...]
    success: bool
    restore_performed_by_drill: bool = False
    destructive_action_authorized: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                "unsupported recovery drill schema"
            )
        object.__setattr__(
            self,
            "drill_id",
            _digest("drill_id", self.drill_id),
        )
        _identity(
            "drill_name",
            self.drill_name,
            maximum=256,
        )
        for name in (
            "previous_drill_id",
            "previous_drill_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(
                    name,
                    getattr(self, name),
                    optional=True,
                ),
            )
        for name in (
            "backup_manifest_id",
            "backup_manifest_digest",
            "restore_report_digest",
            "policy_digest",
        ):
            object.__setattr__(
                self,
                name,
                _digest(name, getattr(self, name)),
            )
        _identity(
            "operator_id",
            self.operator_id,
            maximum=256,
        )
        for name in (
            "generation",
            "backup_generation",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(
                    f"{name} must be positive integer"
                )
        if self.generation == 1:
            if (
                self.previous_drill_id
                or self.previous_drill_digest
            ):
                raise ValueError(
                    "first drill generation may not bind predecessor"
                )
        else:
            if (
                not self.previous_drill_id
                or not self.previous_drill_digest
            ):
                raise ValueError(
                    "later drill generation requires predecessor"
                )
        object.__setattr__(
            self,
            "started_at",
            _timestamp(
                "started_at",
                self.started_at,
            ),
        )
        object.__setattr__(
            self,
            "completed_at",
            _timestamp(
                "completed_at",
                self.completed_at,
            ),
        )
        if self.completed_at < self.started_at:
            raise ValueError(
                "drill completion precedes start"
            )
        if (
            isinstance(self.duration_seconds, bool)
            or not isinstance(
                self.duration_seconds,
                (int, float),
            )
            or not math.isfinite(
                float(self.duration_seconds)
            )
            or float(self.duration_seconds) < 0.0
        ):
            raise ValueError(
                "duration_seconds must be finite and non-negative"
            )
        object.__setattr__(
            self,
            "duration_seconds",
            float(self.duration_seconds),
        )
        if (
            abs(
                self.duration_seconds
                - (
                    self.completed_at
                    - self.started_at
                )
            )
            > 1e-9
        ):
            raise ValueError(
                "duration_seconds does not match drill timestamps"
            )
        if (
            not isinstance(self.restore_mode, str)
            or not self.restore_mode
            or len(self.restore_mode) > 64
        ):
            raise ValueError(
                "invalid restore_mode"
            )
        members = tuple(self.members)
        if not members:
            raise ValueError(
                "recovery drill requires members"
            )
        chain_ids = tuple(
            item.chain_id for item in members
        )
        if chain_ids != tuple(sorted(chain_ids)):
            raise ValueError(
                "drill members must be sorted"
            )
        if len(chain_ids) != len(set(chain_ids)):
            raise ValueError(
                "drill member chain_ids must be unique"
            )
        object.__setattr__(
            self,
            "members",
            members,
        )
        for name in (
            "restore_verified",
            "verification_time_met",
            "sequence_lag_met",
            "regression",
            "success",
            "restore_performed_by_drill",
            "destructive_action_authorized",
        ):
            if not isinstance(
                getattr(self, name),
                bool,
            ):
                raise ValueError(
                    f"{name} must be bool"
                )
        object.__setattr__(
            self,
            "regression_reasons",
            tuple(self.regression_reasons),
        )
        if self.regression != bool(
            self.regression_reasons
        ):
            raise ValueError(
                "regression flag/reasons mismatch"
            )
        expected_success = (
            self.restore_verified
            and self.verification_time_met
            and self.sequence_lag_met
        )
        if self.success != expected_success:
            raise ValueError(
                "drill success does not match objective results"
            )
        if self.restore_performed_by_drill:
            raise ValueError(
                "recovery drill may not claim restore execution"
            )
        if self.destructive_action_authorized:
            raise ValueError(
                "recovery drill may not authorize destructive action"
            )
        expected = self.derive_id(
            drill_name=self.drill_name,
            generation=self.generation,
            previous_drill_id=(
                self.previous_drill_id
            ),
            previous_drill_digest=(
                self.previous_drill_digest
            ),
            backup_manifest_id=(
                self.backup_manifest_id
            ),
            backup_manifest_digest=(
                self.backup_manifest_digest
            ),
            backup_generation=(
                self.backup_generation
            ),
            restore_report_digest=(
                self.restore_report_digest
            ),
            restore_mode=self.restore_mode,
            operator_id=self.operator_id,
            started_at=self.started_at,
            completed_at=self.completed_at,
            policy_digest=self.policy_digest,
            members=members,
            restore_verified=(
                self.restore_verified
            ),
            verification_time_met=(
                self.verification_time_met
            ),
            sequence_lag_met=(
                self.sequence_lag_met
            ),
            regression=self.regression,
            regression_reasons=(
                self.regression_reasons
            ),
            success=self.success,
        )
        if expected != self.drill_id:
            raise ValueError(
                "drill_id does not match drill content"
            )

    @staticmethod
    def derive_id(
        *,
        drill_name: str,
        generation: int,
        previous_drill_id: str,
        previous_drill_digest: str,
        backup_manifest_id: str,
        backup_manifest_digest: str,
        backup_generation: int,
        restore_report_digest: str,
        restore_mode: str,
        operator_id: str,
        started_at: float,
        completed_at: float,
        policy_digest: str,
        members: Iterable[
            DurableRecoveryDrillMember
        ],
        restore_verified: bool,
        verification_time_met: bool,
        sequence_lag_met: bool,
        regression: bool,
        regression_reasons: Iterable[str],
        success: bool,
    ) -> str:
        raw = json.dumps(
            {
                "drill_name": drill_name,
                "generation": generation,
                "previous_drill_id": (
                    previous_drill_id
                ),
                "previous_drill_digest": (
                    previous_drill_digest
                ),
                "backup_manifest_id": (
                    backup_manifest_id
                ),
                "backup_manifest_digest": (
                    backup_manifest_digest
                ),
                "backup_generation": (
                    backup_generation
                ),
                "restore_report_digest": (
                    restore_report_digest
                ),
                "restore_mode": restore_mode,
                "operator_id": operator_id,
                "started_at": float(started_at),
                "completed_at": float(
                    completed_at
                ),
                "policy_digest": policy_digest,
                "members": [
                    item.digest for item in members
                ],
                "restore_verified": (
                    restore_verified
                ),
                "verification_time_met": (
                    verification_time_met
                ),
                "sequence_lag_met": (
                    sequence_lag_met
                ),
                "regression": regression,
                "regression_reasons": list(
                    regression_reasons
                ),
                "success": success,
                "restore_performed_by_drill": False,
                "destructive_action_authorized": False,
                "authority": (
                    "durable-recovery-drill"
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def digest(self) -> str:
        return _stable_digest(
            self.unsigned_dict()
        )

    @property
    def max_sequence_lag(self) -> int:
        return max(
            item.sequence_lag
            for item in self.members
        )

    def unsigned_dict(
        self,
    ) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "drill_id": self.drill_id,
            "drill_name": self.drill_name,
            "generation": self.generation,
            "previous_drill_id": (
                self.previous_drill_id
            ),
            "previous_drill_digest": (
                self.previous_drill_digest
            ),
            "backup_manifest_id": (
                self.backup_manifest_id
            ),
            "backup_manifest_digest": (
                self.backup_manifest_digest
            ),
            "backup_generation": (
                self.backup_generation
            ),
            "restore_report_digest": (
                self.restore_report_digest
            ),
            "restore_mode": self.restore_mode,
            "operator_id": self.operator_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": (
                self.duration_seconds
            ),
            "policy_digest": self.policy_digest,
            "members": [
                item.to_dict()
                for item in self.members
            ],
            "max_sequence_lag": (
                self.max_sequence_lag
            ),
            "restore_verified": (
                self.restore_verified
            ),
            "verification_time_met": (
                self.verification_time_met
            ),
            "sequence_lag_met": (
                self.sequence_lag_met
            ),
            "regression": self.regression,
            "regression_reasons": list(
                self.regression_reasons
            ),
            "success": self.success,
            "restore_performed_by_drill": False,
            "destructive_action_authorized": False,
            "grants_execution_authority": False,
            "grants_restore_authority": False,
            "grants_pruning_authority": False,
        }

    def to_dict(self) -> dict[str, object]:
        data = self.unsigned_dict()
        data["digest"] = self.digest
        return data


@dataclass(frozen=True)
class SignedDurableRecoveryDrill:
    drill: DurableRecoveryDrill
    signature: SignedArtifact

    def __post_init__(self) -> None:
        if not isinstance(
            self.drill,
            DurableRecoveryDrill,
        ):
            raise TypeError(
                "drill must be DurableRecoveryDrill"
            )
        if not isinstance(
            self.signature,
            SignedArtifact,
        ):
            raise TypeError(
                "signature must be SignedArtifact"
            )
        if (
            self.signature.artifact_type
            != "ai-durable-recovery-drill"
        ):
            raise ValueError(
                "invalid recovery drill artifact type"
            )
        if (
            self.signature.artifact_digest
            != self.drill.digest
        ):
            raise ValueError(
                "recovery drill signed digest mismatch"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "drill": self.drill.to_dict(),
            "signature": self.signature.to_dict(),
        }


@dataclass(frozen=True)
class DurableRecoveryDrillHead:
    drill_name: str
    generation: int
    drill_id: str
    drill_digest: str

    def __post_init__(self) -> None:
        _identity(
            "drill_name",
            self.drill_name,
            maximum=256,
        )
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation <= 0
        ):
            raise ValueError(
                "drill head generation must be positive"
            )
        object.__setattr__(
            self,
            "drill_id",
            _digest("drill_id", self.drill_id),
        )
        object.__setattr__(
            self,
            "drill_digest",
            _digest(
                "drill_digest",
                self.drill_digest,
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "drill_name": self.drill_name,
            "generation": self.generation,
            "drill_id": self.drill_id,
            "drill_digest": self.drill_digest,
        }


@dataclass(frozen=True)
class StoredDurableRecoveryDrill:
    revision: int
    signed: SignedDurableRecoveryDrill

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError(
                "recovery drill revision must be positive"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "signed": self.signed.to_dict(),
        }


class DurableRecoveryDrillConflict(RuntimeError):
    pass


class DurableRecoveryDrillCorruption(RuntimeError):
    pass


class DurableRecoveryDrillStore:
    """Immutable signed recovery drills and monotonic named heads."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        signer: ArtifactSigner,
        *,
        namespace: str = "shell-ai-durable-recovery-drill",
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError(
                "invalid recovery drill namespace"
            )
        if not isinstance(
            signer,
            ArtifactSigner,
        ):
            raise TypeError(
                "signer must be ArtifactSigner"
            )
        self.backend = backend
        self.signer = signer
        self.namespace = namespace

    @staticmethod
    def _record_key(drill_id: str) -> str:
        return "drill:" + _digest(
            "drill_id",
            drill_id,
        )

    @staticmethod
    def _head_key(
        drill_name: str,
    ) -> str:
        drill_name = _identity(
            "drill_name",
            drill_name,
            maximum=256,
        )
        return "head:" + hashlib.sha256(
            drill_name.encode()
        ).hexdigest()

    def _verify_signature(
        self,
        item: SignedDurableRecoveryDrill,
    ) -> None:
        try:
            self.signer.verify(
                item.signature
            )
        except ArtifactSignatureError as exc:
            raise DurableRecoveryDrillCorruption(
                "recovery drill signature verification failed"
            ) from exc
        if (
            item.signature.artifact_digest
            != item.drill.digest
        ):
            raise DurableRecoveryDrillCorruption(
                "recovery drill signature digest mismatch"
            )

    def get(
        self,
        drill_id: str,
    ) -> StoredDurableRecoveryDrill | None:
        record = self.backend.get(
            self.namespace,
            self._record_key(drill_id),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            SignedDurableRecoveryDrill,
        ):
            raise DurableRecoveryDrillCorruption(
                "recovery drill backend value type mismatch"
            )
        self._verify_signature(
            record.value
        )
        if (
            record.value.drill.drill_id
            != drill_id
        ):
            raise DurableRecoveryDrillCorruption(
                "recovery drill record/key mismatch"
            )
        return StoredDurableRecoveryDrill(
            record.revision,
            record.value,
        )

    def head(
        self,
        drill_name: str,
    ) -> tuple[
        int,
        DurableRecoveryDrillHead,
    ] | None:
        record = self.backend.get(
            self.namespace,
            self._head_key(drill_name),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DurableRecoveryDrillHead,
        ):
            raise DurableRecoveryDrillCorruption(
                "recovery drill head type mismatch"
            )
        if (
            record.value.drill_name
            != drill_name
        ):
            raise DurableRecoveryDrillCorruption(
                "recovery drill head/key mismatch"
            )
        return record.revision, record.value

    def current(
        self,
        drill_name: str,
    ) -> StoredDurableRecoveryDrill | None:
        head = self.head(drill_name)
        if head is None:
            return None
        _, item = head
        stored = self.get(
            item.drill_id
        )
        if stored is None:
            raise DurableRecoveryDrillCorruption(
                "recovery drill head references missing record"
            )
        if (
            stored.signed.drill.digest
            != item.drill_digest
            or stored.signed.drill.generation
            != item.generation
        ):
            raise DurableRecoveryDrillCorruption(
                "recovery drill head does not match record"
            )
        return stored

    def publish(
        self,
        drill: DurableRecoveryDrill,
    ) -> StoredDurableRecoveryDrill:
        if not isinstance(
            drill,
            DurableRecoveryDrill,
        ):
            raise TypeError(
                "drill must be DurableRecoveryDrill"
            )
        current = self.head(
            drill.drill_name
        )
        if current is None:
            expected_generation = 1
            previous_id = ""
            previous_digest = ""
        else:
            _, head = current
            expected_generation = (
                head.generation + 1
            )
            previous_id = head.drill_id
            previous_digest = head.drill_digest
        if (
            drill.generation
            != expected_generation
        ):
            raise DurableRecoveryDrillConflict(
                "recovery drill generation is stale or skipped"
            )
        if (
            drill.previous_drill_id
            != previous_id
            or drill.previous_drill_digest
            != previous_digest
        ):
            raise DurableRecoveryDrillConflict(
                "recovery drill predecessor differs from current head"
            )

        signature = self.signer.sign(
            "ai-durable-recovery-drill",
            drill.digest,
            metadata={
                "drill_name": drill.drill_name,
                "generation": str(
                    drill.generation
                ),
                "backup_manifest_id": (
                    drill.backup_manifest_id
                ),
            },
        )
        signed = SignedDurableRecoveryDrill(
            drill,
            signature,
        )
        key = self._record_key(
            drill.drill_id
        )
        existing = self.backend.get(
            self.namespace,
            key,
        )
        if existing is None:
            try:
                stored_record = self.backend.put_if_absent(
                    self.namespace,
                    key,
                    signed,
                )
            except DistributedStateConflict:
                existing = self.backend.get(
                    self.namespace,
                    key,
                )
                if existing is None:
                    raise
                stored_record = existing
        else:
            stored_record = existing
        if not isinstance(
            stored_record.value,
            SignedDurableRecoveryDrill,
        ):
            raise DurableRecoveryDrillCorruption(
                "recovery drill record has invalid type"
            )
        self._verify_signature(
            stored_record.value
        )
        if stored_record.value.drill != drill:
            raise DurableRecoveryDrillConflict(
                "drill_id already binds different content"
            )

        head_value = DurableRecoveryDrillHead(
            drill.drill_name,
            drill.generation,
            drill.drill_id,
            drill.digest,
        )
        head_key = self._head_key(
            drill.drill_name
        )
        current_record = self.backend.get(
            self.namespace,
            head_key,
        )
        if current_record is None:
            try:
                head_record = self.backend.put_if_absent(
                    self.namespace,
                    head_key,
                    head_value,
                )
            except DistributedStateConflict:
                current_record = self.backend.get(
                    self.namespace,
                    head_key,
                )
                if current_record is None:
                    raise
                head_record = current_record
        else:
            if (
                not isinstance(
                    current_record.value,
                    DurableRecoveryDrillHead,
                )
                or current_record.value.generation
                != drill.generation - 1
                or current_record.value.drill_id
                != drill.previous_drill_id
                or current_record.value.drill_digest
                != drill.previous_drill_digest
            ):
                raise DurableRecoveryDrillConflict(
                    "recovery drill head changed during publication"
                )
            try:
                head_record = self.backend.compare_and_swap(
                    self.namespace,
                    head_key,
                    expected_revision=(
                        current_record.revision
                    ),
                    value=head_value,
                )
            except DistributedStateConflict as exc:
                raise DurableRecoveryDrillConflict(
                    "recovery drill head CAS lost"
                ) from exc

        if (
            not isinstance(
                head_record.value,
                DurableRecoveryDrillHead,
            )
            or head_record.value != head_value
        ):
            raise DurableRecoveryDrillConflict(
                "published recovery drill head differs"
            )
        return StoredDurableRecoveryDrill(
            stored_record.revision,
            stored_record.value,
        )


class DurableRecoveryDrillOperator:
    """Validate one restored target and publish non-destructive drill evidence."""

    def __init__(
        self,
        manifest_store: DurableBackupManifestStore,
        restore_verifier: DurableRestoreVerifier,
        drill_store: DurableRecoveryDrillStore,
        *,
        policy: DurableRecoveryDrillPolicy
        | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(
            manifest_store,
            DurableBackupManifestStore,
        ):
            raise TypeError(
                "manifest_store must be DurableBackupManifestStore"
            )
        if not isinstance(
            restore_verifier,
            DurableRestoreVerifier,
        ):
            raise TypeError(
                "restore_verifier must be DurableRestoreVerifier"
            )
        if not isinstance(
            drill_store,
            DurableRecoveryDrillStore,
        ):
            raise TypeError(
                "drill_store must be DurableRecoveryDrillStore"
            )
        self.manifest_store = manifest_store
        self.restore_verifier = restore_verifier
        self.drill_store = drill_store
        self.policy = (
            policy
            or DurableRecoveryDrillPolicy()
        )
        if not isinstance(
            self.policy,
            DurableRecoveryDrillPolicy,
        ):
            raise TypeError(
                "policy must be DurableRecoveryDrillPolicy"
            )
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._clock = clock

    def _source_entries(
        self,
        manifest: DurableBackupManifest,
        chains: Iterable[
            tuple[str, object]
        ],
    ) -> dict[str, object]:
        values = tuple(chains)
        if len(values) > self.policy.max_chains:
            raise DurableRecoveryDrillConflict(
                "recovery drill source chain bound exceeded"
            )
        result: dict[str, object] = {}
        for value in values:
            if (
                not isinstance(value, tuple)
                or len(value) != 2
            ):
                raise ValueError(
                    "source chains must be (chain_id, chain) pairs"
                )
            chain_id, chain = value
            _identity(
                "chain_id",
                chain_id,
                maximum=128,
            )
            if chain_id in result:
                raise ValueError(
                    "duplicate source chain_id"
                )
            if not callable(
                getattr(chain, "head", None)
            ):
                raise TypeError(
                    f"source chain {chain_id} does not implement head"
                )
            result[chain_id] = chain
        expected = {
            item.chain_id
            for item in manifest.chains
        }
        if set(result) != expected:
            raise DurableRecoveryDrillConflict(
                "source chain set differs from backup manifest"
            )
        return result

    @staticmethod
    def _ancestor(
        chain: object,
        sequence: int,
        root_hash: str,
    ) -> bool:
        root_is_ancestor = getattr(
            chain,
            "root_is_ancestor",
            None,
        )
        if callable(root_is_ancestor):
            try:
                return bool(
                    root_is_ancestor(
                        root_hash
                    )
                )
            except Exception:
                return False
        root_for_sequence = getattr(
            chain,
            "root_for_sequence",
            None,
        )
        if callable(root_for_sequence):
            try:
                return (
                    str(
                        root_for_sequence(
                            sequence
                        )
                    )
                    == root_hash
                )
            except Exception:
                return False
        return False

    @staticmethod
    def _regression(
        previous: DurableRecoveryDrill | None,
        *,
        success: bool,
        duration_seconds: float,
        max_sequence_lag: int,
    ) -> tuple[bool, tuple[str, ...]]:
        if previous is None:
            return False, ()
        reasons: list[str] = []
        if previous.success and not success:
            reasons.append(
                "previous successful drill now fails"
            )
        if (
            duration_seconds
            > previous.duration_seconds
        ):
            reasons.append(
                "verification duration increased"
            )
        if (
            max_sequence_lag
            > previous.max_sequence_lag
        ):
            reasons.append(
                "source-to-backup sequence lag increased"
            )
        return bool(reasons), tuple(reasons)

    def run(
        self,
        drill_name: str,
        manifest_id: str,
        *,
        source_chains: Iterable[
            tuple[str, object]
        ],
        restored_chains: Iterable[
            tuple[str, object]
        ],
        operator_id: str,
        restore_mode: DurableRestoreMode = (
            DurableRestoreMode.EXACT_BARRIER
        ),
    ) -> StoredDurableRecoveryDrill:
        drill_name = _identity(
            "drill_name",
            drill_name,
            maximum=256,
        )
        operator_id = _identity(
            "operator_id",
            operator_id,
            maximum=256,
        )
        restore_mode = DurableRestoreMode(
            restore_mode
        )
        stored_manifest = (
            self.manifest_store.require(
                manifest_id
            )
        )
        manifest = (
            stored_manifest.signed.manifest
        )
        sources = self._source_entries(
            manifest,
            source_chains,
        )

        started_at = _timestamp(
            "started_at",
            self._clock(),
        )
        restore_report = (
            self.restore_verifier.verify(
                manifest_id,
                restored_chains,
                mode=restore_mode,
            )
        )
        completed_at = _timestamp(
            "completed_at",
            self._clock(),
        )
        if completed_at < started_at:
            raise DurableRecoveryDrillConflict(
                "recovery drill clock moved backwards"
            )
        duration = (
            completed_at - started_at
        )

        restore_by_id = {
            item.chain_id: item
            for item in restore_report.chains
        }
        members: list[
            DurableRecoveryDrillMember
        ] = []
        source_ancestry_ok = True
        for backup_chain in manifest.chains:
            source = sources[
                backup_chain.chain_id
            ]
            head = source.head()
            try:
                source_sequence = int(
                    head.sequence
                )
                source_root = str(
                    head.root_hash
                )
            except Exception as exc:
                raise DurableRecoveryDrillConflict(
                    f"source chain {backup_chain.chain_id} head is invalid"
                ) from exc
            if (
                source_sequence
                < backup_chain.barrier_head_sequence
            ):
                raise DurableRecoveryDrillConflict(
                    f"source chain {backup_chain.chain_id} rolled back behind backup"
                )
            ancestor = self._ancestor(
                source,
                backup_chain.barrier_head_sequence,
                backup_chain.barrier_head_root,
            )
            if (
                self.policy.require_source_ancestry
                and not ancestor
            ):
                source_ancestry_ok = False
            restore_chain = restore_by_id.get(
                backup_chain.chain_id
            )
            if restore_chain is None:
                restore_state = "missing"
                restore_exact = False
                restore_ancestor = False
            else:
                restore_state = (
                    restore_chain.state.value
                )
                restore_exact = (
                    restore_chain.exact_head
                )
                restore_ancestor = (
                    restore_chain
                    .expected_root_is_ancestor
                )
            members.append(
                DurableRecoveryDrillMember(
                    backup_chain.chain_id,
                    backup_chain.barrier_head_sequence,
                    backup_chain.barrier_head_root,
                    source_sequence,
                    source_root,
                    source_sequence
                    - backup_chain.barrier_head_sequence,
                    ancestor,
                    restore_state,
                    restore_exact,
                    restore_ancestor,
                )
            )

        ordered = tuple(
            sorted(
                members,
                key=lambda item: item.chain_id,
            )
        )
        max_lag = max(
            item.sequence_lag
            for item in ordered
        )
        restore_verified = (
            restore_report.ok
            and (
                source_ancestry_ok
                or not self.policy.require_source_ancestry
            )
        )
        if (
            not self.policy.require_restore_verified
        ):
            restore_verified = (
                source_ancestry_ok
                or not self.policy.require_source_ancestry
            )
        verification_time_met = (
            duration
            <= self.policy.max_verification_seconds
        )
        sequence_lag_met = (
            max_lag
            <= self.policy.max_sequence_lag
        )
        success = (
            restore_verified
            and verification_time_met
            and sequence_lag_met
        )

        current = self.drill_store.current(
            drill_name
        )
        if current is None:
            generation = 1
            previous_id = ""
            previous_digest = ""
            previous_drill = None
        else:
            previous_drill = (
                current.signed.drill
            )
            generation = (
                previous_drill.generation + 1
            )
            previous_id = (
                previous_drill.drill_id
            )
            previous_digest = (
                previous_drill.digest
            )
        regression, reasons = self._regression(
            previous_drill,
            success=success,
            duration_seconds=duration,
            max_sequence_lag=max_lag,
        )
        drill_id = DurableRecoveryDrill.derive_id(
            drill_name=drill_name,
            generation=generation,
            previous_drill_id=previous_id,
            previous_drill_digest=(
                previous_digest
            ),
            backup_manifest_id=(
                manifest.manifest_id
            ),
            backup_manifest_digest=(
                manifest.digest
            ),
            backup_generation=(
                manifest.generation
            ),
            restore_report_digest=(
                restore_report.digest
            ),
            restore_mode=(
                restore_mode.value
            ),
            operator_id=operator_id,
            started_at=started_at,
            completed_at=completed_at,
            policy_digest=self.policy.digest,
            members=ordered,
            restore_verified=restore_verified,
            verification_time_met=(
                verification_time_met
            ),
            sequence_lag_met=(
                sequence_lag_met
            ),
            regression=regression,
            regression_reasons=reasons,
            success=success,
        )
        drill = DurableRecoveryDrill(
            1,
            drill_id,
            drill_name,
            generation,
            previous_id,
            previous_digest,
            manifest.manifest_id,
            manifest.digest,
            manifest.generation,
            restore_report.digest,
            restore_mode.value,
            operator_id,
            started_at,
            completed_at,
            duration,
            self.policy.digest,
            ordered,
            restore_verified,
            verification_time_met,
            sequence_lag_met,
            regression,
            reasons,
            success,
            False,
            False,
        )
        return self.drill_store.publish(
            drill
        )
