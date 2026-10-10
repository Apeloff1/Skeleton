"""State-compatible checkpoint rollback contracts for learned models.

A rollback target is not safe merely because its weight digest is old and known.
It must be compatible with the current representation, architecture/runtime ABI,
optimizer state schema, data cursor semantics and migration envelope.

This module provides a deterministic fail-closed admission contract. It is
training-framework agnostic and intentionally separates "checkpoint exists"
from "checkpoint may replace current state".
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Mapping, Sequence


class ModelRollbackError(RuntimeError):
    """A checkpoint cannot be proven safe for rollback."""


def _stable_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ModelRollbackError("rollback identity is not deterministic JSON") from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _text(name: str, value: object, *, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelRollbackError(f"{name} must be non-empty text")
    result = value.strip()
    if len(result) > maximum:
        raise ModelRollbackError(f"{name} exceeds {maximum} characters")
    return result


def _sha(name: str, value: object) -> str:
    result = _text(name, value, maximum=64).lower()
    if len(result) != 64 or any(ch not in "0123456789abcdef" for ch in result):
        raise ModelRollbackError(f"{name} must be lowercase sha256")
    return result


def _nonnegative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ModelRollbackError(f"{name} must be a non-negative integer")
    return value


def _unique(name: str, values: Sequence[str]) -> tuple[str, ...]:
    result = tuple(_text(name, item) for item in values)
    if len(result) != len(set(result)):
        raise ModelRollbackError(f"{name} values must be unique")
    return result


@dataclass(frozen=True, slots=True)
class OptimizerStateIdentity:
    optimizer_family: str
    optimizer_version: str
    schema_version: str
    parameter_group_digest: str
    state_digest: str

    def __post_init__(self) -> None:
        for field_name in ("optimizer_family", "optimizer_version", "schema_version"):
            object.__setattr__(
                self,
                field_name,
                _text(field_name, getattr(self, field_name)),
            )
        object.__setattr__(
            self,
            "parameter_group_digest",
            _sha("parameter_group_digest", self.parameter_group_digest),
        )
        object.__setattr__(
            self,
            "state_digest",
            _sha("state_digest", self.state_digest),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "optimizer_family": self.optimizer_family,
            "optimizer_version": self.optimizer_version,
            "schema_version": self.schema_version,
            "parameter_group_digest": self.parameter_group_digest,
            "state_digest": self.state_digest,
        }

    @property
    def identity(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class DataCursorIdentity:
    data_manifest_root: str
    mixture_digest: str
    cursor_schema: str
    draw_index: int
    cursor_digest: str

    def __post_init__(self) -> None:
        for field_name in ("data_manifest_root", "mixture_digest", "cursor_digest"):
            object.__setattr__(
                self,
                field_name,
                _sha(field_name, getattr(self, field_name)),
            )
        object.__setattr__(
            self,
            "cursor_schema",
            _text("cursor_schema", self.cursor_schema),
        )
        object.__setattr__(
            self,
            "draw_index",
            _nonnegative_int("draw_index", self.draw_index),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "data_manifest_root": self.data_manifest_root,
            "mixture_digest": self.mixture_digest,
            "cursor_schema": self.cursor_schema,
            "draw_index": self.draw_index,
            "cursor_digest": self.cursor_digest,
        }


@dataclass(frozen=True, slots=True)
class ModelCheckpoint:
    checkpoint_id: str
    model_artifact_digest: str
    architecture_config_digest: str
    representation_id: str
    runtime_abi: str
    optimizer: OptimizerStateIdentity
    data_cursor: DataCursorIdentity
    training_step: int
    checkpoint_format: str
    checkpoint_format_version: str
    code_revision: str
    rng_state_digest: str
    integrity_digest: str
    parent_checkpoint_id: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "checkpoint_id",
            "representation_id",
            "runtime_abi",
            "checkpoint_format",
            "checkpoint_format_version",
            "code_revision",
        ):
            object.__setattr__(
                self,
                field_name,
                _text(field_name, getattr(self, field_name)),
            )
        for field_name in (
            "model_artifact_digest",
            "architecture_config_digest",
            "rng_state_digest",
            "integrity_digest",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha(field_name, getattr(self, field_name)),
            )
        if not isinstance(self.optimizer, OptimizerStateIdentity):
            raise TypeError("optimizer must be OptimizerStateIdentity")
        if not isinstance(self.data_cursor, DataCursorIdentity):
            raise TypeError("data_cursor must be DataCursorIdentity")
        object.__setattr__(
            self,
            "training_step",
            _nonnegative_int("training_step", self.training_step),
        )
        if self.parent_checkpoint_id is not None:
            object.__setattr__(
                self,
                "parent_checkpoint_id",
                _text("parent_checkpoint_id", self.parent_checkpoint_id),
            )
        frozen = dict(self.metadata)
        _stable_json(frozen)
        object.__setattr__(self, "metadata", frozen)

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.model_checkpoint.v1",
            "checkpoint_id": self.checkpoint_id,
            "model_artifact_digest": self.model_artifact_digest,
            "architecture_config_digest": self.architecture_config_digest,
            "representation_id": self.representation_id,
            "runtime_abi": self.runtime_abi,
            "optimizer": self.optimizer.as_dict(),
            "data_cursor": self.data_cursor.as_dict(),
            "training_step": self.training_step,
            "checkpoint_format": self.checkpoint_format,
            "checkpoint_format_version": self.checkpoint_format_version,
            "code_revision": self.code_revision,
            "rng_state_digest": self.rng_state_digest,
            "parent_checkpoint_id": self.parent_checkpoint_id,
            "metadata": dict(self.metadata),
        }

    @property
    def computed_integrity_digest(self) -> str:
        return _digest(self.identity_payload())

    def assert_integrity(self) -> None:
        if self.computed_integrity_digest != self.integrity_digest:
            raise ModelRollbackError("checkpoint integrity digest mismatch")


@dataclass(frozen=True, slots=True)
class RuntimeStateEnvelope:
    architecture_config_digest: str
    representation_id: str
    runtime_abi: str
    optimizer_family: str
    optimizer_version: str
    optimizer_schema_version: str
    parameter_group_digest: str
    data_manifest_root: str
    mixture_digest: str
    cursor_schema: str
    checkpoint_format: str
    supported_checkpoint_versions: tuple[str, ...]
    minimum_training_step: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "architecture_config_digest",
            "parameter_group_digest",
            "data_manifest_root",
            "mixture_digest",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha(field_name, getattr(self, field_name)),
            )
        for field_name in (
            "representation_id",
            "runtime_abi",
            "optimizer_family",
            "optimizer_version",
            "optimizer_schema_version",
            "cursor_schema",
            "checkpoint_format",
        ):
            object.__setattr__(
                self,
                field_name,
                _text(field_name, getattr(self, field_name)),
            )
        versions = _unique(
            "supported_checkpoint_version",
            self.supported_checkpoint_versions,
        )
        if not versions:
            raise ModelRollbackError("supported_checkpoint_versions must not be empty")
        object.__setattr__(self, "supported_checkpoint_versions", versions)
        object.__setattr__(
            self,
            "minimum_training_step",
            _nonnegative_int("minimum_training_step", self.minimum_training_step),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "architecture_config_digest": self.architecture_config_digest,
            "representation_id": self.representation_id,
            "runtime_abi": self.runtime_abi,
            "optimizer_family": self.optimizer_family,
            "optimizer_version": self.optimizer_version,
            "optimizer_schema_version": self.optimizer_schema_version,
            "parameter_group_digest": self.parameter_group_digest,
            "data_manifest_root": self.data_manifest_root,
            "mixture_digest": self.mixture_digest,
            "cursor_schema": self.cursor_schema,
            "checkpoint_format": self.checkpoint_format,
            "supported_checkpoint_versions": list(self.supported_checkpoint_versions),
            "minimum_training_step": self.minimum_training_step,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class MigrationEdge:
    component: str
    from_version: str
    to_version: str
    migration_id: str
    reversible: bool
    verifier_ref: str

    def __post_init__(self) -> None:
        for field_name in (
            "component",
            "from_version",
            "to_version",
            "migration_id",
            "verifier_ref",
        ):
            object.__setattr__(
                self,
                field_name,
                _text(field_name, getattr(self, field_name)),
            )
        if self.from_version == self.to_version:
            raise ModelRollbackError("migration must change version")
        if not isinstance(self.reversible, bool):
            raise TypeError("reversible must be boolean")

    def as_dict(self) -> dict[str, object]:
        return {
            "component": self.component,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "migration_id": self.migration_id,
            "reversible": self.reversible,
            "verifier_ref": self.verifier_ref,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RollbackPolicy:
    allow_optimizer_migration: bool = False
    allow_cursor_migration: bool = False
    require_reversible_migrations: bool = True
    require_same_data_manifest: bool = True
    forbid_step_regression_below: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "allow_optimizer_migration",
            "allow_cursor_migration",
            "require_reversible_migrations",
            "require_same_data_manifest",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be boolean")
        object.__setattr__(
            self,
            "forbid_step_regression_below",
            _nonnegative_int(
                "forbid_step_regression_below",
                self.forbid_step_regression_below,
            ),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "allow_optimizer_migration": self.allow_optimizer_migration,
            "allow_cursor_migration": self.allow_cursor_migration,
            "require_reversible_migrations": self.require_reversible_migrations,
            "require_same_data_manifest": self.require_same_data_manifest,
            "forbid_step_regression_below": self.forbid_step_regression_below,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RollbackReceipt:
    checkpoint_id: str
    admissible: bool
    blockers: tuple[str, ...]
    migration_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "checkpoint_id",
            _text("checkpoint_id", self.checkpoint_id),
        )
        if not isinstance(self.admissible, bool):
            raise TypeError("admissible must be boolean")
        blockers = _unique("rollback blocker", self.blockers)
        migration_ids = _unique("migration_id", self.migration_ids)
        if self.admissible and blockers:
            raise ModelRollbackError("admissible rollback cannot contain blockers")
        if not self.admissible and not blockers:
            raise ModelRollbackError("inadmissible rollback must explain at least one blocker")
        object.__setattr__(self, "blockers", blockers)
        object.__setattr__(self, "migration_ids", migration_ids)

    def as_dict(self) -> dict[str, object]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "admissible": self.admissible,
            "blockers": list(self.blockers),
            "migration_ids": list(self.migration_ids),
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class RollbackDecisionEvidence:
    checkpoint_id: str
    checkpoint_claimed_integrity_digest: str
    checkpoint_computed_integrity_digest: str
    runtime_digest: str
    policy_digest: str
    migration_inventory_digests: tuple[str, ...]
    receipt: RollbackReceipt

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "checkpoint_id",
            _text("checkpoint_id", self.checkpoint_id),
        )
        for field_name in (
            "checkpoint_claimed_integrity_digest",
            "checkpoint_computed_integrity_digest",
            "runtime_digest",
            "policy_digest",
        ):
            object.__setattr__(
                self,
                field_name,
                _sha(field_name, getattr(self, field_name)),
            )
        digests = tuple(
            _sha("migration_inventory_digest", value)
            for value in self.migration_inventory_digests
        )
        if len(digests) != len(set(digests)):
            raise ModelRollbackError(
                "migration inventory digests must be unique"
            )
        object.__setattr__(
            self,
            "migration_inventory_digests",
            tuple(sorted(digests)),
        )
        if not isinstance(self.receipt, RollbackReceipt):
            raise TypeError("receipt must be RollbackReceipt")
        if self.receipt.checkpoint_id != self.checkpoint_id:
            raise ModelRollbackError(
                "rollback evidence checkpoint identity mismatch"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_claimed_integrity_digest": self.checkpoint_claimed_integrity_digest,
            "checkpoint_computed_integrity_digest": self.checkpoint_computed_integrity_digest,
            "runtime_digest": self.runtime_digest,
            "policy_digest": self.policy_digest,
            "migration_inventory_digests": list(self.migration_inventory_digests),
            "receipt": self.receipt.as_dict(),
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


def _find_migration(
    migrations: Sequence[MigrationEdge],
    *,
    component: str,
    source: str,
    target: str,
    require_reversible: bool,
) -> MigrationEdge | None:
    matches = [
        edge
        for edge in migrations
        if edge.component == component
        and edge.from_version == source
        and edge.to_version == target
        and (edge.reversible or not require_reversible)
    ]
    if len(matches) > 1:
        raise ModelRollbackError(
            f"ambiguous {component} migration {source}->{target}"
        )
    return matches[0] if matches else None


def evaluate_rollback(
    checkpoint: ModelCheckpoint,
    runtime: RuntimeStateEnvelope,
    *,
    policy: RollbackPolicy | None = None,
    migrations: Sequence[MigrationEdge] = (),
) -> RollbackReceipt:
    if not isinstance(checkpoint, ModelCheckpoint):
        raise TypeError("checkpoint must be ModelCheckpoint")
    if not isinstance(runtime, RuntimeStateEnvelope):
        raise TypeError("runtime must be RuntimeStateEnvelope")
    active_policy = policy or RollbackPolicy()
    if not isinstance(active_policy, RollbackPolicy):
        raise TypeError("policy must be RollbackPolicy")
    if any(not isinstance(edge, MigrationEdge) for edge in migrations):
        raise TypeError("migrations must contain MigrationEdge values")
    migration_ids = [edge.migration_id for edge in migrations]
    if len(migration_ids) != len(set(migration_ids)):
        raise ModelRollbackError("migration ids must be unique")
    unsupported_components = sorted(
        {edge.component for edge in migrations}
        - {"optimizer", "data_cursor"}
    )
    if unsupported_components:
        raise ModelRollbackError(
            "unsupported migration component(s): "
            + ", ".join(unsupported_components)
        )

    blockers: list[str] = []
    selected_migration_ids: list[str] = []

    try:
        checkpoint.assert_integrity()
    except ModelRollbackError as exc:
        blockers.append(str(exc))

    if checkpoint.architecture_config_digest != runtime.architecture_config_digest:
        blockers.append("architecture config is incompatible")
    if checkpoint.representation_id != runtime.representation_id:
        blockers.append("representation identity is incompatible")
    if checkpoint.runtime_abi != runtime.runtime_abi:
        blockers.append("runtime ABI is incompatible")
    if checkpoint.checkpoint_format != runtime.checkpoint_format:
        blockers.append("checkpoint format is incompatible")
    if checkpoint.checkpoint_format_version not in runtime.supported_checkpoint_versions:
        blockers.append("checkpoint format version is unsupported")

    if checkpoint.optimizer.optimizer_family != runtime.optimizer_family:
        blockers.append("optimizer family is incompatible")
    if checkpoint.optimizer.optimizer_version != runtime.optimizer_version:
        blockers.append("optimizer version is incompatible")
    if checkpoint.optimizer.parameter_group_digest != runtime.parameter_group_digest:
        blockers.append("optimizer parameter groups are incompatible")

    if checkpoint.optimizer.schema_version != runtime.optimizer_schema_version:
        if not active_policy.allow_optimizer_migration:
            blockers.append("optimizer schema requires forbidden migration")
        else:
            edge = _find_migration(
                migrations,
                component="optimizer",
                source=checkpoint.optimizer.schema_version,
                target=runtime.optimizer_schema_version,
                require_reversible=active_policy.require_reversible_migrations,
            )
            if edge is None:
                blockers.append("optimizer schema migration is unavailable")
            else:
                selected_migration_ids.append(edge.migration_id)

    if (
        active_policy.require_same_data_manifest
        and checkpoint.data_cursor.data_manifest_root != runtime.data_manifest_root
    ):
        blockers.append("training data manifest is incompatible")
    if checkpoint.data_cursor.mixture_digest != runtime.mixture_digest:
        blockers.append("training mixture identity is incompatible")

    if checkpoint.data_cursor.cursor_schema != runtime.cursor_schema:
        if not active_policy.allow_cursor_migration:
            blockers.append("data cursor schema requires forbidden migration")
        else:
            edge = _find_migration(
                migrations,
                component="data_cursor",
                source=checkpoint.data_cursor.cursor_schema,
                target=runtime.cursor_schema,
                require_reversible=active_policy.require_reversible_migrations,
            )
            if edge is None:
                blockers.append("data cursor schema migration is unavailable")
            else:
                selected_migration_ids.append(edge.migration_id)

    floor = max(
        runtime.minimum_training_step,
        active_policy.forbid_step_regression_below,
    )
    if checkpoint.training_step < floor:
        blockers.append("checkpoint training step violates rollback floor")

    return RollbackReceipt(
        checkpoint_id=checkpoint.checkpoint_id,
        admissible=not blockers,
        blockers=tuple(blockers),
        migration_ids=tuple(selected_migration_ids),
    )


def evaluate_rollback_evidence(
    checkpoint: ModelCheckpoint,
    runtime: RuntimeStateEnvelope,
    *,
    policy: RollbackPolicy | None = None,
    migrations: Sequence[MigrationEdge] = (),
) -> RollbackDecisionEvidence:
    """Return a content-addressed rollback decision bound to its full context."""

    active_policy = policy or RollbackPolicy()
    receipt = evaluate_rollback(
        checkpoint,
        runtime,
        policy=active_policy,
        migrations=migrations,
    )
    return RollbackDecisionEvidence(
        checkpoint_id=checkpoint.checkpoint_id,
        checkpoint_claimed_integrity_digest=checkpoint.integrity_digest,
        checkpoint_computed_integrity_digest=checkpoint.computed_integrity_digest,
        runtime_digest=runtime.digest,
        policy_digest=active_policy.digest,
        migration_inventory_digests=tuple(edge.digest for edge in migrations),
        receipt=receipt,
    )


def build_checkpoint(
    *,
    checkpoint_id: str,
    model_artifact_digest: str,
    architecture_config_digest: str,
    representation_id: str,
    runtime_abi: str,
    optimizer: OptimizerStateIdentity,
    data_cursor: DataCursorIdentity,
    training_step: int,
    checkpoint_format: str,
    checkpoint_format_version: str,
    code_revision: str,
    rng_state_digest: str,
    parent_checkpoint_id: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> ModelCheckpoint:
    """Construct a checkpoint with a self-consistent integrity digest."""

    placeholder = "0" * 64
    candidate = ModelCheckpoint(
        checkpoint_id=checkpoint_id,
        model_artifact_digest=model_artifact_digest,
        architecture_config_digest=architecture_config_digest,
        representation_id=representation_id,
        runtime_abi=runtime_abi,
        optimizer=optimizer,
        data_cursor=data_cursor,
        training_step=training_step,
        checkpoint_format=checkpoint_format,
        checkpoint_format_version=checkpoint_format_version,
        code_revision=code_revision,
        rng_state_digest=rng_state_digest,
        integrity_digest=placeholder,
        parent_checkpoint_id=parent_checkpoint_id,
        metadata={} if metadata is None else dict(metadata),
    )
    return ModelCheckpoint(
        checkpoint_id=candidate.checkpoint_id,
        model_artifact_digest=candidate.model_artifact_digest,
        architecture_config_digest=candidate.architecture_config_digest,
        representation_id=candidate.representation_id,
        runtime_abi=candidate.runtime_abi,
        optimizer=candidate.optimizer,
        data_cursor=candidate.data_cursor,
        training_step=candidate.training_step,
        checkpoint_format=candidate.checkpoint_format,
        checkpoint_format_version=candidate.checkpoint_format_version,
        code_revision=candidate.code_revision,
        rng_state_digest=candidate.rng_state_digest,
        integrity_digest=candidate.computed_integrity_digest,
        parent_checkpoint_id=candidate.parent_checkpoint_id,
        metadata=candidate.metadata,
    )


__all__ = [
    "DataCursorIdentity",
    "MigrationEdge",
    "ModelCheckpoint",
    "ModelRollbackError",
    "OptimizerStateIdentity",
    "RollbackDecisionEvidence",
    "RollbackPolicy",
    "RollbackReceipt",
    "RuntimeStateEnvelope",
    "build_checkpoint",
    "evaluate_rollback",
    "evaluate_rollback_evidence",
]
