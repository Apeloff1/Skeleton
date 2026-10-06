"""Deterministic migration-compatibility rehearsal primitives for VOL-005.

The runtime is intentionally storage-neutral. Store-specific migration code can
bind its real transforms to this harness while release qualification validates
the invariants every durable migration must preserve: stable identity, semantic
read compatibility during a mixed-version window, replay idempotence, exact
rollback where rollback is claimed, and byte-digest-equivalent backup restore.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Callable, Mapping, Sequence


_ID = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")


class MigrationCompatibilityError(ValueError):
    """Migration data or behavior violated a declared compatibility contract."""


def _freeze_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise MigrationCompatibilityError("non-finite JSON number is forbidden")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise MigrationCompatibilityError("JSON object keys must be text")
            if key in frozen:
                raise MigrationCompatibilityError("duplicate JSON object key")
            frozen[key] = _freeze_json(item)
        return frozen
    if isinstance(value, (list, tuple)):
        return [_freeze_json(item) for item in value]
    raise MigrationCompatibilityError(
        f"unsupported canonical JSON value: {type(value).__name__}"
    )


def canonical_json_bytes(value: Any) -> bytes:
    frozen = _freeze_json(value)
    try:
        text = json.dumps(
            frozen,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise MigrationCompatibilityError("value is not canonical JSON") from exc
    return text.encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _stable_id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise MigrationCompatibilityError(
            f"{field} must be a stable lowercase identifier"
        )
    return value


@dataclass(frozen=True, slots=True)
class RecordSchema:
    schema_id: str
    version: int
    identity_fields: tuple[str, ...]
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()
    allow_unknown_fields: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_id", _stable_id(self.schema_id, "schema_id"))
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise MigrationCompatibilityError("schema version must be positive integer")
        for field_name in ("identity_fields", "required_fields", "optional_fields"):
            values = getattr(self, field_name)
            if not isinstance(values, tuple) or any(
                not isinstance(item, str) or not item for item in values
            ):
                raise MigrationCompatibilityError(
                    f"{field_name} must be a tuple of field names"
                )
            if len(values) != len(set(values)):
                raise MigrationCompatibilityError(f"{field_name} contains duplicates")
        if not self.identity_fields:
            raise MigrationCompatibilityError("identity_fields must not be empty")
        if not set(self.identity_fields).issubset(set(self.required_fields)):
            raise MigrationCompatibilityError(
                "identity fields must also be required fields"
            )
        if set(self.required_fields) & set(self.optional_fields):
            raise MigrationCompatibilityError(
                "required and optional fields must be disjoint"
            )
        if not isinstance(self.allow_unknown_fields, bool):
            raise MigrationCompatibilityError("allow_unknown_fields must be bool")

    def validate(self, record: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(record, Mapping):
            raise MigrationCompatibilityError("record must be a mapping")
        normalized = _freeze_json(record)
        if not isinstance(normalized, dict):
            raise MigrationCompatibilityError("record must normalize to object")
        version = normalized.get("schema_version")
        if version != self.version:
            raise MigrationCompatibilityError(
                f"{self.schema_id} requires schema_version={self.version}"
            )
        missing = sorted(set(self.required_fields) - set(normalized))
        if missing:
            raise MigrationCompatibilityError(
                f"{self.schema_id} record missing fields: {', '.join(missing)}"
            )
        allowed = (
            set(self.required_fields)
            | set(self.optional_fields)
            | {"schema_version"}
        )
        unknown = sorted(set(normalized) - allowed)
        if unknown and not self.allow_unknown_fields:
            raise MigrationCompatibilityError(
                f"{self.schema_id} record has unknown fields: {', '.join(unknown)}"
            )
        self.identity(normalized)
        canonical_json_bytes(normalized)
        return normalized

    def identity(self, record: Mapping[str, Any]) -> tuple[Any, ...]:
        values: list[Any] = []
        for field in self.identity_fields:
            if field not in record:
                raise MigrationCompatibilityError(
                    f"identity field {field!r} is missing"
                )
            value = _freeze_json(record[field])
            if value is None or isinstance(value, (dict, list)):
                raise MigrationCompatibilityError(
                    f"identity field {field!r} must be a scalar"
                )
            values.append(value)
        return tuple(values)


Transform = Callable[[Mapping[str, Any]], Mapping[str, Any]]
Projection = Callable[[Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    migration_id: str
    state_domain: str
    source: RecordSchema
    target: RecordSchema
    forward: Transform
    rollback: Transform
    project: Projection

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "migration_id", _stable_id(self.migration_id, "migration_id")
        )
        object.__setattr__(
            self, "state_domain", _stable_id(self.state_domain, "state_domain")
        )
        if self.source.schema_id == self.target.schema_id and self.source.version == self.target.version:
            raise MigrationCompatibilityError(
                "migration source and target schema must differ"
            )
        for name in ("forward", "rollback", "project"):
            if not callable(getattr(self, name)):
                raise MigrationCompatibilityError(f"{name} must be callable")

    def migrate(self, record: Mapping[str, Any]) -> dict[str, Any]:
        raw_version = record.get("schema_version") if isinstance(record, Mapping) else None
        if raw_version == self.target.version:
            # Replaying migration over already-upgraded data is a no-op only
            # when the target record itself validates.
            return self.target.validate(record)
        source = self.source.validate(record)
        before = deepcopy(source)
        migrated = self.target.validate(self.forward(deepcopy(source)))
        if source != before:
            raise MigrationCompatibilityError("forward migration mutated source input")
        if self.source.identity(source) != self.target.identity(migrated):
            raise MigrationCompatibilityError("migration changed canonical record identity")
        return migrated

    def reverse(self, record: Mapping[str, Any]) -> dict[str, Any]:
        target = self.target.validate(record)
        before = deepcopy(target)
        restored = self.source.validate(self.rollback(deepcopy(target)))
        if target != before:
            raise MigrationCompatibilityError("rollback mutated target input")
        if self.target.identity(target) != self.source.identity(restored):
            raise MigrationCompatibilityError("rollback changed canonical record identity")
        return restored

    def semantic_projection(self, record: Mapping[str, Any]) -> dict[str, Any]:
        raw_version = record.get("schema_version") if isinstance(record, Mapping) else None
        if raw_version == self.source.version:
            normalized = self.source.validate(record)
        elif raw_version == self.target.version:
            normalized = self.target.validate(record)
        else:
            raise MigrationCompatibilityError(
                "mixed-version reader received unsupported schema version"
            )
        projected = _freeze_json(self.project(deepcopy(normalized)))
        if not isinstance(projected, dict) or not projected:
            raise MigrationCompatibilityError(
                "semantic projection must be a non-empty object"
            )
        canonical_json_bytes(projected)
        return projected


@dataclass(frozen=True, slots=True)
class MigrationQualificationReceipt:
    migration_id: str
    state_domain: str
    record_count: int
    source_digest: str
    target_digest: str
    replay_digest: str
    source_projection_digest: str
    target_projection_digest: str
    mixed_projection_digest: str
    rollback_digest: str
    backup_digest: str
    restore_digest: str

    @property
    def qualified(self) -> bool:
        return (
            self.target_digest == self.replay_digest
            and self.source_projection_digest == self.target_projection_digest
            and self.source_projection_digest == self.mixed_projection_digest
            and self.source_digest == self.rollback_digest
            and self.source_digest == self.backup_digest
            and self.source_digest == self.restore_digest
        )

    @property
    def receipt_digest(self) -> str:
        return digest(
            {
                "migration_id": self.migration_id,
                "state_domain": self.state_domain,
                "record_count": self.record_count,
                "source_digest": self.source_digest,
                "target_digest": self.target_digest,
                "replay_digest": self.replay_digest,
                "source_projection_digest": self.source_projection_digest,
                "target_projection_digest": self.target_projection_digest,
                "mixed_projection_digest": self.mixed_projection_digest,
                "rollback_digest": self.rollback_digest,
                "backup_digest": self.backup_digest,
                "restore_digest": self.restore_digest,
                "qualified": self.qualified,
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "migration_id": self.migration_id,
            "state_domain": self.state_domain,
            "record_count": self.record_count,
            "source_digest": self.source_digest,
            "target_digest": self.target_digest,
            "replay_digest": self.replay_digest,
            "source_projection_digest": self.source_projection_digest,
            "target_projection_digest": self.target_projection_digest,
            "mixed_projection_digest": self.mixed_projection_digest,
            "rollback_digest": self.rollback_digest,
            "backup_digest": self.backup_digest,
            "restore_digest": self.restore_digest,
            "qualified": self.qualified,
            "receipt_digest": self.receipt_digest,
        }


def _ordered_records(
    records: Sequence[Mapping[str, Any]],
    schema: RecordSchema,
) -> list[dict[str, Any]]:
    normalized = [schema.validate(record) for record in records]
    identities = [schema.identity(record) for record in normalized]
    if len(identities) != len(set(identities)):
        raise MigrationCompatibilityError("migration fixture contains duplicate identity")
    return [
        record
        for _, record in sorted(
            zip(
                [canonical_json_bytes(identity) for identity in identities],
                normalized,
            ),
            key=lambda pair: pair[0],
        )
    ]


def _projection_digest(
    plan: MigrationPlan,
    records: Sequence[Mapping[str, Any]],
) -> str:
    projections = [
        {
            "identity": list(
                (
                    plan.source.identity(record)
                    if record.get("schema_version") == plan.source.version
                    else plan.target.identity(record)
                )
            ),
            "semantic": plan.semantic_projection(record),
        }
        for record in records
    ]
    projections.sort(key=lambda row: canonical_json_bytes(row["identity"]))
    return digest(projections)


def run_migration_rehearsal(
    plan: MigrationPlan,
    source_records: Sequence[Mapping[str, Any]],
) -> MigrationQualificationReceipt:
    """Execute a deterministic forward/mixed/replay/rollback/restore rehearsal."""

    if not isinstance(plan, MigrationPlan):
        raise TypeError("plan must be MigrationPlan")
    if not isinstance(source_records, Sequence) or isinstance(
        source_records, (str, bytes, bytearray)
    ):
        raise TypeError("source_records must be a sequence")
    if not source_records:
        raise MigrationCompatibilityError("migration rehearsal requires records")

    source = _ordered_records(source_records, plan.source)
    source_digest = digest(source)
    source_projection_digest = _projection_digest(plan, source)

    # Backup is canonical bytes rather than a Python deepcopy so restore proof
    # catches serialization drift and aliasing.
    backup_bytes = canonical_json_bytes(source)
    backup_digest = hashlib.sha256(backup_bytes).hexdigest()

    target = [plan.migrate(record) for record in source]
    target = _ordered_records(target, plan.target)
    target_digest = digest(target)
    target_projection_digest = _projection_digest(plan, target)
    if source_projection_digest != target_projection_digest:
        raise MigrationCompatibilityError(
            "forward migration changed semantic projection"
        )

    replay = [plan.migrate(record) for record in target]
    replay = _ordered_records(replay, plan.target)
    replay_digest = digest(replay)
    if replay_digest != target_digest:
        raise MigrationCompatibilityError("migration replay is not idempotent")

    split = max(1, len(source) // 2)
    mixed: list[Mapping[str, Any]] = [
        *target[:split],
        *source[split:],
    ]
    mixed_projection_digest = _projection_digest(plan, mixed)
    if mixed_projection_digest != source_projection_digest:
        raise MigrationCompatibilityError(
            "mixed-version semantic reads diverge from source behavior"
        )

    rolled_back = [plan.reverse(record) for record in target]
    rolled_back = _ordered_records(rolled_back, plan.source)
    rollback_digest = digest(rolled_back)
    if rollback_digest != source_digest:
        raise MigrationCompatibilityError(
            "rollback did not restore the exact source snapshot"
        )

    try:
        restored_raw = json.loads(backup_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MigrationCompatibilityError("backup bytes are not restorable") from exc
    if not isinstance(restored_raw, list):
        raise MigrationCompatibilityError("restored backup must contain record list")
    restored = _ordered_records(restored_raw, plan.source)
    restore_digest = digest(restored)
    if restore_digest != source_digest:
        raise MigrationCompatibilityError(
            "backup restore did not reproduce exact source snapshot"
        )

    receipt = MigrationQualificationReceipt(
        migration_id=plan.migration_id,
        state_domain=plan.state_domain,
        record_count=len(source),
        source_digest=source_digest,
        target_digest=target_digest,
        replay_digest=replay_digest,
        source_projection_digest=source_projection_digest,
        target_projection_digest=target_projection_digest,
        mixed_projection_digest=mixed_projection_digest,
        rollback_digest=rollback_digest,
        backup_digest=backup_digest,
        restore_digest=restore_digest,
    )
    if not receipt.qualified:
        raise MigrationCompatibilityError("migration qualification receipt is not qualified")
    return receipt


def reference_rehearsal() -> MigrationQualificationReceipt:
    """Dependency-free release-gate smoke rehearsal for the migration engine."""

    source = RecordSchema(
        schema_id="state.fixture.v1",
        version=1,
        identity_fields=("record_id",),
        required_fields=("record_id", "value"),
    )
    target = RecordSchema(
        schema_id="state.fixture.v2",
        version=2,
        identity_fields=("record_id",),
        required_fields=("record_id", "value", "metadata"),
    )

    def forward(record: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "schema_version": 2,
            "record_id": record["record_id"],
            "value": record["value"],
            "metadata": {"migrated_from": 1},
        }

    def rollback(record: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "schema_version": 1,
            "record_id": record["record_id"],
            "value": record["value"],
        }

    def project(record: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "record_id": record["record_id"],
            "value": record["value"],
        }

    plan = MigrationPlan(
        migration_id="state.reference.v1-v2",
        state_domain="canonical-operation-state",
        source=source,
        target=target,
        forward=forward,
        rollback=rollback,
        project=project,
    )
    return run_migration_rehearsal(
        plan,
        (
            {"schema_version": 1, "record_id": "op-001", "value": {"state": "running"}},
            {"schema_version": 1, "record_id": "op-002", "value": {"state": "completed"}},
            {"schema_version": 1, "record_id": "op-003", "value": {"state": "failed"}},
        ),
    )


__all__ = [
    "MigrationCompatibilityError",
    "MigrationPlan",
    "MigrationQualificationReceipt",
    "RecordSchema",
    "canonical_json_bytes",
    "digest",
    "reference_rehearsal",
    "run_migration_rehearsal",
]
