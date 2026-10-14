"""Durable retention/privacy binding for VOL-024 learning signals.

Only lifecycle metadata is persisted through this module. Learning payloads remain
outside the lifecycle registry; the registry receives a content-addressed signal
reference, explicit classification, finite retention deadline, declared deletion
targets, and export policy.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re

from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.eval.failure_knowledge import LearningSignal
from skeleton.vault.data_governance import DataClass
from skeleton.vault.data_lifecycle import DataLifecycleRegistry, GovernedDataRecord
from skeleton.vault.regional_privacy import policy_for_region


LEARNING_RETENTION_SCHEMA_VERSION = 1
LEARNING_RETENTION_MAX_SECONDS = 10 * 365 * 24 * 60 * 60
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,191}$")


class LearningRetentionError(ValueError):
    """Learning-signal lifecycle policy is incomplete or unsafe."""


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise LearningRetentionError(f"{field} must be a canonical token")
    return value


def _seconds(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LearningRetentionError("retention_seconds must be an integer")
    if value < 1 or value > LEARNING_RETENTION_MAX_SECONDS:
        raise LearningRetentionError("retention_seconds is outside bounded policy")
    return value


def _targets(values: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not values:
        raise LearningRetentionError("deletion_targets must be a non-empty tuple")
    normalized = tuple(sorted({_token(value, "deletion_target") for value in values}))
    if len(normalized) != len(values):
        raise LearningRetentionError("deletion_targets must be sorted unique values")
    if normalized != values:
        raise LearningRetentionError("deletion_targets must be canonical")
    return normalized


@dataclass(frozen=True, slots=True)
class LearningSignalRetentionPolicy:
    policy_id: str
    data_class: DataClass | str | int
    retention_seconds: int
    deletion_targets: tuple[str, ...]
    region: str = "GLOBAL"
    exportable: bool = False
    schema_version: int = LEARNING_RETENTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _token(self.policy_id, "policy_id"))
        try:
            classification = DataClass.parse(self.data_class)
        except Exception as exc:
            raise LearningRetentionError("invalid data_class") from exc
        object.__setattr__(self, "data_class", classification)
        object.__setattr__(
            self,
            "retention_seconds",
            _seconds(self.retention_seconds),
        )
        object.__setattr__(
            self,
            "deletion_targets",
            _targets(self.deletion_targets),
        )
        if not isinstance(self.region, str) or not self.region.strip():
            raise LearningRetentionError("region is required")
        normalized_region = self.region.strip().upper()
        try:
            policy_for_region(normalized_region)
        except Exception as exc:
            raise LearningRetentionError("region is not governed") from exc
        object.__setattr__(self, "region", normalized_region)
        if not isinstance(self.exportable, bool):
            raise LearningRetentionError("exportable must be boolean")
        if classification is DataClass.RESTRICTED and self.exportable:
            raise LearningRetentionError("restricted learning signals cannot be exportable")
        if self.schema_version != LEARNING_RETENTION_SCHEMA_VERSION:
            raise LearningRetentionError("unsupported retention schema version")

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "data_class": self.data_class.label,
            "retention_seconds": self.retention_seconds,
            "deletion_targets": list(self.deletion_targets),
            "region": self.region,
            "exportable": self.exportable,
            "payload_persistence": False,
        }

    @property
    def policy_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class LearningSignalLifecycleBinding:
    signal_digest: str
    policy_digest: str
    record_id: str
    tenant_id: str
    retention_until: float
    data_class: str
    region: str
    exportable: bool
    deletion_targets: tuple[str, ...]
    payload_persisted: bool = False

    def __post_init__(self) -> None:
        for field in ("signal_digest", "policy_digest"):
            value = getattr(self, field)
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise LearningRetentionError(f"{field} must be lowercase sha256")
        _token(self.record_id, "record_id")
        _token(self.tenant_id, "tenant_id")
        if not isinstance(self.retention_until, (int, float)) or isinstance(
            self.retention_until, bool
        ):
            raise LearningRetentionError("retention_until must be finite")
        if not math.isfinite(float(self.retention_until)) or self.retention_until < 0:
            raise LearningRetentionError("retention_until must be finite")
        if self.payload_persisted is not False:
            raise LearningRetentionError("learning payload must not be lifecycle-persisted")


def register_learning_signal_lifecycle(
    *,
    registry: DataLifecycleRegistry,
    signal: LearningSignal,
    tenant_id: str,
    policy: LearningSignalRetentionPolicy,
    created_at: float,
) -> LearningSignalLifecycleBinding:
    if not isinstance(registry, DataLifecycleRegistry):
        raise TypeError("registry must be DataLifecycleRegistry")
    if not isinstance(signal, LearningSignal):
        raise TypeError("signal must be LearningSignal")
    if not isinstance(policy, LearningSignalRetentionPolicy):
        raise TypeError("policy must be LearningSignalRetentionPolicy")
    tenant = _token(tenant_id, "tenant_id")
    if isinstance(created_at, bool) or not isinstance(created_at, (int, float)):
        raise LearningRetentionError("created_at must be finite")
    timestamp = float(created_at)
    if not math.isfinite(timestamp) or timestamp < 0:
        raise LearningRetentionError("created_at must be finite")

    signal_digest = signal.signal_digest
    record_id = f"learning-signal:{signal_digest}"
    retention_until = timestamp + policy.retention_seconds
    governed = GovernedDataRecord(
        record_id=record_id,
        tenant_id=tenant,
        owner_plane="evaluation-learning",
        source_ref=f"learning-signal://{signal_digest}",
        data_class=policy.data_class,
        purposes=("evaluation", "learning-signal"),
        deletion_targets=policy.deletion_targets,
        created_at=timestamp,
        retention_until=retention_until,
        exportable=policy.exportable,
    )
    registry.register(governed)

    return LearningSignalLifecycleBinding(
        signal_digest=signal_digest,
        policy_digest=policy.policy_digest,
        record_id=record_id,
        tenant_id=tenant,
        retention_until=retention_until,
        data_class=policy.data_class.label,
        region=policy.region,
        exportable=policy.exportable,
        deletion_targets=policy.deletion_targets,
        payload_persisted=False,
    )


__all__ = [
    "LEARNING_RETENTION_MAX_SECONDS",
    "LEARNING_RETENTION_SCHEMA_VERSION",
    "LearningRetentionError",
    "LearningSignalLifecycleBinding",
    "LearningSignalRetentionPolicy",
    "register_learning_signal_lifecycle",
]
