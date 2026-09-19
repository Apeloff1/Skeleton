"""Worker identity, registration, and generation-safe ownership primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import re
import threading
import time
from types import MappingProxyType
from typing import Callable, Iterable, Mapping

_WORKER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_LABEL_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_LABEL_VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/+-]{0,127}$")


class WorkerIdentityError(ValueError):
    pass


class WorkerRole(str, Enum):
    GENERAL = "general"
    EXECUTOR = "executor"
    BUILDER = "builder"
    TESTER = "tester"
    ANALYZER = "analyzer"
    MAINTENANCE = "maintenance"


def _freeze_labels(labels: Mapping[str, str]) -> Mapping[str, str]:
    if len(labels) > 64:
        raise WorkerIdentityError("too many worker labels")
    clean: dict[str, str] = {}
    for key, value in labels.items():
        if not isinstance(key, str) or not _LABEL_KEY.fullmatch(key):
            raise WorkerIdentityError("invalid worker label key")
        if not isinstance(value, str) or not _LABEL_VALUE.fullmatch(value):
            raise WorkerIdentityError("invalid worker label value")
        clean[key] = value
    return MappingProxyType(clean)


def _freeze_features(features: Iterable[str]) -> frozenset[str]:
    result = frozenset(features)
    if len(result) > 128:
        raise WorkerIdentityError("too many worker features")
    for feature in result:
        if not isinstance(feature, str) or not _LABEL_VALUE.fullmatch(feature):
            raise WorkerIdentityError("invalid worker feature")
    return result


@dataclass(frozen=True)
class WorkerIdentity:
    worker_id: str
    generation: int
    role: WorkerRole = WorkerRole.GENERAL
    labels: Mapping[str, str] = field(default_factory=dict)
    features: frozenset[str] = frozenset()
    protocol_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.worker_id, str) or not _WORKER_ID.fullmatch(self.worker_id):
            raise WorkerIdentityError("invalid worker_id")
        if isinstance(self.generation, bool) or not isinstance(self.generation, int) or self.generation <= 0:
            raise WorkerIdentityError("generation must be a positive integer")
        if not isinstance(self.role, WorkerRole):
            object.__setattr__(self, "role", WorkerRole(self.role))
        if isinstance(self.protocol_version, bool) or not isinstance(self.protocol_version, int):
            raise WorkerIdentityError("protocol_version must be an integer")
        if self.protocol_version <= 0 or self.protocol_version > 1024:
            raise WorkerIdentityError("protocol_version outside supported bounds")
        object.__setattr__(self, "labels", _freeze_labels(self.labels))
        object.__setattr__(self, "features", _freeze_features(self.features))

    @property
    def key(self) -> str:
        return f"{self.worker_id}#{self.generation}"

    def to_dict(self) -> dict[str, object]:
        return {
            "worker_id": self.worker_id,
            "generation": self.generation,
            "role": self.role.value,
            "labels": dict(self.labels),
            "features": sorted(self.features),
            "protocol_version": self.protocol_version,
        }

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return "worker:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def supports(self, feature: str) -> bool:
        return feature in self.features

    def matches_labels(self, required: Mapping[str, str]) -> bool:
        return all(self.labels.get(key) == value for key, value in required.items())


@dataclass(frozen=True)
class WorkerRegistration:
    identity: WorkerIdentity
    registration_id: str
    registered_at: float
    updated_at: float
    enabled: bool = True
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.registration_id:
            raise WorkerIdentityError("registration_id is required")
        metadata = _freeze_labels(self.metadata)
        object.__setattr__(self, "metadata", metadata)
        if self.registered_at < 0 or self.updated_at < 0:
            raise WorkerIdentityError("registration timestamps may not be negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity.to_dict(),
            "registration_id": self.registration_id,
            "registered_at": self.registered_at,
            "updated_at": self.updated_at,
            "enabled": self.enabled,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class WorkerRegistrySnapshot:
    registrations: tuple[WorkerRegistration, ...]
    created_at: float

    @property
    def enabled(self) -> int:
        return sum(reg.enabled for reg in self.registrations)

    @property
    def disabled(self) -> int:
        return len(self.registrations) - self.enabled

    def by_role(self) -> dict[str, int]:
        counts = {role.value: 0 for role in WorkerRole}
        for registration in self.registrations:
            counts[registration.identity.role.value] += 1
        return counts

    def to_dict(self) -> dict[str, object]:
        return {
            "created_at": self.created_at,
            "enabled": self.enabled,
            "disabled": self.disabled,
            "by_role": self.by_role(),
            "registrations": [registration.to_dict() for registration in self.registrations],
        }


class WorkerRegistry:
    """Bounded registry with generation-safe replacement and removal."""

    def __init__(
        self,
        *,
        max_workers: int = 4096,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers <= 0:
            raise ValueError("max_workers must be a positive integer")
        self.max_workers = max_workers
        self._clock = clock
        self._registrations: dict[str, WorkerRegistration] = {}
        self._lock = threading.RLock()
        self._serial = 0

    def _new_registration_id(self, identity: WorkerIdentity) -> str:
        self._serial += 1
        raw = f"{identity.key}:{self._serial}:{self._clock()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def register(
        self,
        identity: WorkerIdentity,
        *,
        metadata: Mapping[str, str] | None = None,
        replace: bool = False,
    ) -> WorkerRegistration:
        if not isinstance(identity, WorkerIdentity):
            raise TypeError("identity must be WorkerIdentity")
        with self._lock:
            existing = self._registrations.get(identity.worker_id)
            if existing is not None:
                if not replace:
                    raise WorkerIdentityError("worker_id is already registered")
                if identity.generation <= existing.identity.generation:
                    raise WorkerIdentityError("replacement generation must increase")
            elif len(self._registrations) >= self.max_workers:
                raise WorkerIdentityError("worker registry capacity exhausted")
            now = self._clock()
            registration = WorkerRegistration(
                identity=identity,
                registration_id=self._new_registration_id(identity),
                registered_at=now if existing is None else existing.registered_at,
                updated_at=now,
                enabled=True,
                metadata=metadata or {},
            )
            self._registrations[identity.worker_id] = registration
            return registration

    def replace(self, identity: WorkerIdentity, *, metadata: Mapping[str, str] | None = None) -> WorkerRegistration:
        return self.register(identity, metadata=metadata, replace=True)

    def get(self, worker_id: str) -> WorkerRegistration:
        with self._lock:
            return self._registrations[worker_id]

    def find(self, worker_id: str) -> WorkerRegistration | None:
        with self._lock:
            return self._registrations.get(worker_id)

    def current(self, identity: WorkerIdentity) -> bool:
        with self._lock:
            registration = self._registrations.get(identity.worker_id)
            return registration is not None and registration.identity.generation == identity.generation

    def require_current(self, identity: WorkerIdentity) -> WorkerRegistration:
        registration = self.find(identity.worker_id)
        if registration is None:
            raise WorkerIdentityError("worker is not registered")
        if registration.identity.generation != identity.generation:
            raise WorkerIdentityError("worker generation is stale")
        return registration

    def set_enabled(self, identity: WorkerIdentity, enabled: bool) -> WorkerRegistration:
        with self._lock:
            current = self.require_current(identity)
            now = self._clock()
            replacement = WorkerRegistration(
                identity=current.identity,
                registration_id=current.registration_id,
                registered_at=current.registered_at,
                updated_at=now,
                enabled=bool(enabled),
                metadata=current.metadata,
            )
            self._registrations[identity.worker_id] = replacement
            return replacement

    def unregister(self, identity: WorkerIdentity, *, registration_id: str | None = None) -> bool:
        with self._lock:
            current = self._registrations.get(identity.worker_id)
            if current is None:
                return False
            if current.identity.generation != identity.generation:
                return False
            if registration_id is not None and current.registration_id != registration_id:
                return False
            del self._registrations[identity.worker_id]
            return True

    def matching(
        self,
        *,
        role: WorkerRole | None = None,
        labels: Mapping[str, str] | None = None,
        features: Iterable[str] = (),
        enabled_only: bool = True,
    ) -> tuple[WorkerRegistration, ...]:
        required_labels = dict(labels or {})
        required_features = frozenset(features)
        with self._lock:
            result = []
            for registration in self._registrations.values():
                identity = registration.identity
                if enabled_only and not registration.enabled:
                    continue
                if role is not None and identity.role is not WorkerRole(role):
                    continue
                if not identity.matches_labels(required_labels):
                    continue
                if not required_features <= identity.features:
                    continue
                result.append(registration)
            return tuple(sorted(result, key=lambda item: item.identity.key))

    def snapshot(self) -> WorkerRegistrySnapshot:
        with self._lock:
            registrations = tuple(
                sorted(self._registrations.values(), key=lambda item: item.identity.key)
            )
            return WorkerRegistrySnapshot(registrations, self._clock())

    def __len__(self) -> int:
        with self._lock:
            return len(self._registrations)
