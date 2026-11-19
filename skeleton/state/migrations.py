"""Versioned checkpoint-state migrations for durable run recovery.

The storage layer records a checkpoint ``state_version`` but intentionally does
not know subsystem-specific schemas. ``CheckpointMigrator`` supplies the
missing contract above storage: migrations are explicit, contiguous, bounded,
and validated as finite JSON after every step so restart recovery fails closed
instead of silently accepting partially migrated state.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Callable

MigrationFn = Callable[[Any], Any]
DEFAULT_MAX_MIGRATION_BYTES = 1_048_576
DEFAULT_MAX_MIGRATION_STEPS = 64


class MigrationError(RuntimeError):
    """Base error for checkpoint-state migration failures."""


class MigrationPathError(MigrationError):
    """Raised when no complete forward migration path exists."""


class MigrationValidationError(MigrationError):
    """Raised when a migration produces invalid or oversized state."""


@dataclass(frozen=True)
class MigrationResult:
    """Detached result of a completed checkpoint migration."""

    state: Any
    from_version: int
    to_version: int
    applied_versions: tuple[int, ...]


class CheckpointMigrator:
    """Registry of one-version-at-a-time checkpoint migrations.

    Each registered function upgrades version ``N`` to exactly ``N + 1``.
    Requiring contiguous migrations keeps compatibility debt visible and makes
    it impossible to accidentally skip an intermediate invariant.
    """

    def __init__(
        self,
        current_version: int,
        *,
        max_payload_bytes: int = DEFAULT_MAX_MIGRATION_BYTES,
        max_steps: int = DEFAULT_MAX_MIGRATION_STEPS,
    ) -> None:
        self.current_version = self._version(current_version, "current_version")
        if isinstance(max_payload_bytes, bool) or not isinstance(max_payload_bytes, int):
            raise ValueError("max_payload_bytes must be a positive integer")
        if max_payload_bytes < 1:
            raise ValueError("max_payload_bytes must be a positive integer")
        if isinstance(max_steps, bool) or not isinstance(max_steps, int):
            raise ValueError("max_steps must be a positive integer")
        if max_steps < 1:
            raise ValueError("max_steps must be a positive integer")
        self._max_payload_bytes = max_payload_bytes
        self._max_steps = max_steps
        self._migrations: dict[int, MigrationFn] = {}

    @staticmethod
    def _version(value: int, field: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{field} must be a positive integer")
        return value

    def register(self, from_version: int, migration: MigrationFn) -> None:
        """Register an ``N -> N+1`` migration exactly once."""
        from_version = self._version(from_version, "from_version")
        if from_version >= self.current_version:
            raise ValueError("from_version must be below current_version")
        if not callable(migration):
            raise TypeError("migration must be callable")
        if from_version in self._migrations:
            raise MigrationPathError(
                f"migration from version {from_version} is already registered"
            )
        self._migrations[from_version] = migration

    def migration(self, from_version: int) -> Callable[[MigrationFn], MigrationFn]:
        """Decorator form of :meth:`register`."""
        def decorate(fn: MigrationFn) -> MigrationFn:
            self.register(from_version, fn)
            return fn

        return decorate

    def missing_versions(
        self,
        from_version: int = 1,
        to_version: int | None = None,
    ) -> tuple[int, ...]:
        """Return source versions whose forward migration is not registered."""
        source, target = self._bounds(from_version, to_version)
        return tuple(
            version
            for version in range(source, target)
            if version not in self._migrations
        )

    def validate_path(
        self,
        from_version: int = 1,
        to_version: int | None = None,
    ) -> None:
        """Fail unless every required migration edge is registered."""
        missing = self.missing_versions(from_version, to_version)
        if missing:
            joined = ", ".join(str(version) for version in missing)
            raise MigrationPathError(
                f"incomplete checkpoint migration path; missing source versions: {joined}"
            )

    def migrate(
        self,
        state: Any,
        from_version: int,
        *,
        to_version: int | None = None,
    ) -> MigrationResult:
        """Upgrade detached checkpoint state through every required version."""
        source, target = self._bounds(from_version, to_version)
        distance = target - source
        if distance > self._max_steps:
            raise MigrationPathError(
                f"migration requires {distance} steps; maximum is {self._max_steps}"
            )
        self.validate_path(source, target)

        value = self._validated_copy(state, f"checkpoint state v{source}")
        applied: list[int] = []
        for version in range(source, target):
            migration = self._migrations[version]
            try:
                candidate = migration(copy.deepcopy(value))
            except MigrationError:
                raise
            except Exception as exc:
                raise MigrationError(
                    f"checkpoint migration {version}->{version + 1} failed"
                ) from exc
            value = self._validated_copy(
                candidate,
                f"checkpoint state v{version + 1}",
            )
            applied.append(version + 1)

        return MigrationResult(
            state=value,
            from_version=source,
            to_version=target,
            applied_versions=tuple(applied),
        )

    def _bounds(
        self,
        from_version: int,
        to_version: int | None,
    ) -> tuple[int, int]:
        source = self._version(from_version, "from_version")
        target = (
            self.current_version
            if to_version is None
            else self._version(to_version, "to_version")
        )
        if source > self.current_version:
            raise MigrationPathError(
                f"checkpoint version {source} is newer than supported version "
                f"{self.current_version}"
            )
        if target > self.current_version:
            raise MigrationPathError(
                f"target version {target} is newer than supported version "
                f"{self.current_version}"
            )
        if target < source:
            raise MigrationPathError("checkpoint migrations do not support downgrade")
        return source, target

    def _validated_copy(self, value: Any, field: str) -> Any:
        try:
            encoded = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise MigrationValidationError(
                f"{field} must be finite JSON data"
            ) from exc
        if len(encoded.encode("utf-8")) > self._max_payload_bytes:
            raise MigrationValidationError(
                f"{field} exceeds {self._max_payload_bytes} encoded bytes"
            )
        # JSON round-trip guarantees the caller receives detached plain data,
        # not an object graph that a migration function can later mutate.
        return json.loads(encoded)
