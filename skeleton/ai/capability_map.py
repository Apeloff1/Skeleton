"""Dependency-aware capability registry for VOL-113.

Planned intent and observed live availability are separate authorities.
A descriptor says what a capability is intended to provide; live evidence says
what exact descriptor revision is currently supported. Resolution is fail-closed:
missing or mismatched evidence never becomes availability, dependency failures
propagate explicitly, and callers cannot silently fall back to weaker guarantees.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import re
from itertools import islice
from typing import Iterable

CAPABILITY_MAP_SCHEMA = "skeleton.ai.capability_map.v1"
_MAX_CAPABILITIES = 10_000
_MAX_DEPENDENCIES = 256
_MAX_GUARANTEES = 256
_MAX_REASON = 2_048
_ID = re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GUARANTEE = re.compile(r"^[a-z][a-z0-9_.:-]{1,127}$")


class CapabilityError(ValueError):
    """Capability registry state is malformed, contradictory, or unavailable."""


class Maturity(str, Enum):
    PLANNED = "planned"
    EXPERIMENTAL = "experimental"
    PRODUCTION = "production"


class Availability(str, Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


def _id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise CapabilityError(f"{field} must be stable identifier")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise CapabilityError(f"{field} must be lowercase sha256")
    return value


def _guarantee(value: object) -> str:
    if not isinstance(value, str) or not _GUARANTEE.fullmatch(value):
        raise CapabilityError("guarantee must be canonical token")
    return value


def _reason(value: object, *, required: bool) -> str:
    if not isinstance(value, str):
        raise CapabilityError("availability reason must be text")
    if value != value.strip() or len(value) > _MAX_REASON:
        raise CapabilityError("availability reason must be bounded canonical text")
    if any(ord(char) < 32 for char in value):
        raise CapabilityError("availability reason contains control characters")
    if required and not value:
        raise CapabilityError("degraded/unavailable capability requires reason")
    return value


def _digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CapabilityError("capability state must be deterministic JSON") from exc
    return sha256(raw).hexdigest()


def _normalize_ids(
    values: tuple[str, ...],
    *,
    field: str,
    maximum: int,
) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise CapabilityError(f"{field} must be tuple")
    if len(values) > maximum:
        raise CapabilityError(f"{field} exceeds safety bound")
    item_field = field[:-1] if field.endswith("s") else field
    normalized = tuple(_id(value, item_field) for value in values)
    if len(normalized) != len(set(normalized)):
        raise CapabilityError(f"duplicate {item_field}")
    return tuple(sorted(normalized))


def _normalize_guarantees(
    values: tuple[str, ...],
    *,
    required: bool = True,
) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise CapabilityError("guarantees must be tuple")
    if len(values) > _MAX_GUARANTEES:
        raise CapabilityError("guarantees exceed safety bound")
    normalized = tuple(_guarantee(value) for value in values)
    if len(normalized) != len(set(normalized)):
        raise CapabilityError("duplicate guarantee")
    if required and not normalized:
        raise CapabilityError("capability guarantees required")
    return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    capability_id: str
    owner_id: str
    maturity: Maturity
    dependency_ids: tuple[str, ...]
    guarantees: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "capability_id",
            _id(self.capability_id, "capability_id"),
        )
        object.__setattr__(self, "owner_id", _id(self.owner_id, "owner_id"))
        if not isinstance(self.maturity, Maturity):
            raise CapabilityError("maturity must be Maturity")
        dependencies = _normalize_ids(
            self.dependency_ids,
            field="dependency_ids",
            maximum=_MAX_DEPENDENCIES,
        )
        if self.capability_id in dependencies:
            raise CapabilityError("self dependency")
        object.__setattr__(self, "dependency_ids", dependencies)
        object.__setattr__(
            self,
            "guarantees",
            _normalize_guarantees(self.guarantees),
        )

    @property
    def digest(self) -> str:
        return _digest(
            [
                CAPABILITY_MAP_SCHEMA,
                self.capability_id,
                self.owner_id,
                self.maturity.value,
                list(self.dependency_ids),
                list(self.guarantees),
            ]
        )


@dataclass(frozen=True, slots=True)
class CapabilityEvidence:
    """Observed live support for one exact descriptor revision."""

    evidence_id: str
    capability_id: str
    descriptor_digest: str
    state: Availability
    guarantees: tuple[str, ...]
    artifact_digest: str
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evidence_id",
            _id(self.evidence_id, "evidence_id"),
        )
        object.__setattr__(
            self,
            "capability_id",
            _id(self.capability_id, "capability_id"),
        )
        object.__setattr__(
            self,
            "descriptor_digest",
            _sha(self.descriptor_digest, "descriptor_digest"),
        )
        object.__setattr__(
            self,
            "artifact_digest",
            _sha(self.artifact_digest, "artifact_digest"),
        )
        if not isinstance(self.state, Availability):
            raise CapabilityError("state must be Availability")
        guarantees = _normalize_guarantees(
            self.guarantees,
            required=self.state is not Availability.UNAVAILABLE,
        )
        object.__setattr__(self, "guarantees", guarantees)
        object.__setattr__(
            self,
            "reason",
            _reason(
                self.reason,
                required=self.state is not Availability.AVAILABLE,
            ),
        )
        if self.state is Availability.UNAVAILABLE and guarantees:
            raise CapabilityError(
                "unavailable evidence cannot advertise guarantees"
            )

    @property
    def digest(self) -> str:
        return _digest(
            [
                CAPABILITY_MAP_SCHEMA,
                self.evidence_id,
                self.capability_id,
                self.descriptor_digest,
                self.state.value,
                list(self.guarantees),
                self.artifact_digest,
                self.reason,
            ]
        )


@dataclass(frozen=True, slots=True)
class CapabilityAvailability:
    """Resolved effective availability after dependency propagation."""

    capability_id: str
    state: Availability
    guarantees: tuple[str, ...]
    reason: str
    evidence_digest: str | None
    dependency_states: tuple[tuple[str, Availability], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "capability_id",
            _id(self.capability_id, "capability_id"),
        )
        if not isinstance(self.state, Availability):
            raise CapabilityError("state must be Availability")
        object.__setattr__(
            self,
            "guarantees",
            _normalize_guarantees(
                self.guarantees,
                required=self.state is Availability.AVAILABLE,
            ),
        )
        object.__setattr__(
            self,
            "reason",
            _reason(
                self.reason,
                required=self.state is not Availability.AVAILABLE,
            ),
        )
        if self.evidence_digest is not None:
            object.__setattr__(
                self,
                "evidence_digest",
                _sha(self.evidence_digest, "evidence_digest"),
            )
        if self.state is Availability.UNAVAILABLE and self.guarantees:
            raise CapabilityError(
                "unavailable capability cannot advertise guarantees"
            )
        normalized_dependencies: list[tuple[str, Availability]] = []
        seen: set[str] = set()
        for item in self.dependency_states:
            if not isinstance(item, tuple) or len(item) != 2:
                raise CapabilityError("dependency state must be (id, state)")
            dependency_id, state = item
            dependency_id = _id(dependency_id, "dependency_id")
            if not isinstance(state, Availability):
                raise CapabilityError("dependency state must use Availability")
            if dependency_id in seen:
                raise CapabilityError("duplicate dependency state")
            seen.add(dependency_id)
            normalized_dependencies.append((dependency_id, state))
        object.__setattr__(
            self,
            "dependency_states",
            tuple(sorted(normalized_dependencies, key=lambda item: item[0])),
        )

    @property
    def digest(self) -> str:
        return _digest(
            [
                CAPABILITY_MAP_SCHEMA,
                self.capability_id,
                self.state.value,
                list(self.guarantees),
                self.reason,
                self.evidence_digest,
                [
                    (item, state.value)
                    for item, state in self.dependency_states
                ],
            ]
        )


@dataclass(frozen=True, slots=True)
class CapabilitySnapshot:
    """Deterministic complete resolution result."""

    registry_digest: str
    capabilities: tuple[CapabilityAvailability, ...]

    @property
    def healthy(self) -> bool:
        return all(
            item.state is Availability.AVAILABLE
            for item in self.capabilities
        )

    @property
    def digest(self) -> str:
        return _digest(
            [
                CAPABILITY_MAP_SCHEMA,
                self.registry_digest,
                [item.digest for item in self.capabilities],
                self.healthy,
            ]
        )


    def to_dict(self) -> dict[str, object]:
        return {
            "schema": CAPABILITY_MAP_SCHEMA,
            "registry_digest": self.registry_digest,
            "capabilities": [
                {
                    "capability_id": item.capability_id,
                    "state": item.state.value,
                    "guarantees": list(item.guarantees),
                    "reason": item.reason,
                    "evidence_digest": item.evidence_digest,
                    "dependency_states": [
                        [dependency_id, state.value]
                        for dependency_id, state in item.dependency_states
                    ],
                }
                for item in self.capabilities
            ],
            "healthy": self.healthy,
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, value: object) -> "CapabilitySnapshot":
        if not isinstance(value, dict):
            raise CapabilityError("capability snapshot payload must be mapping")
        expected = {"schema", "registry_digest", "capabilities", "healthy", "digest"}
        if set(value) != expected:
            raise CapabilityError("capability snapshot has unknown or missing fields")
        if value["schema"] != CAPABILITY_MAP_SCHEMA:
            raise CapabilityError("unsupported capability snapshot schema")
        registry_digest = _sha(value["registry_digest"], "registry_digest")
        raw_capabilities = value["capabilities"]
        if not isinstance(raw_capabilities, list):
            raise CapabilityError("snapshot capabilities must be list")
        if len(raw_capabilities) > _MAX_CAPABILITIES:
            raise CapabilityError("snapshot capability count exceeds safety bound")
        capabilities = []
        for raw in raw_capabilities:
            if not isinstance(raw, dict):
                raise CapabilityError("snapshot capability must be mapping")
            fields = {"capability_id", "state", "guarantees", "reason", "evidence_digest", "dependency_states"}
            if set(raw) != fields:
                raise CapabilityError("snapshot capability has unknown or missing fields")
            guarantees_raw = raw["guarantees"]
            dependencies_raw = raw["dependency_states"]
            if not isinstance(guarantees_raw, list):
                raise CapabilityError("snapshot guarantees must be list")
            if len(guarantees_raw) > _MAX_GUARANTEES:
                raise CapabilityError("snapshot guarantees exceed safety bound")
            if not isinstance(dependencies_raw, list):
                raise CapabilityError("snapshot dependency states must be list")
            if len(dependencies_raw) > _MAX_DEPENDENCIES:
                raise CapabilityError("snapshot dependency states exceed safety bound")
            try:
                state = Availability(raw["state"])
                guarantees = tuple(guarantees_raw)
                dependency_states = tuple(
                    (item[0], Availability(item[1]))
                    for item in dependencies_raw
                )
            except (TypeError, ValueError, IndexError) as exc:
                raise CapabilityError("malformed snapshot capability") from exc
            capabilities.append(CapabilityAvailability(
                raw["capability_id"], state, guarantees, raw["reason"],
                raw["evidence_digest"], dependency_states,
            ))
        capability_ids = [item.capability_id for item in capabilities]
        if len(capability_ids) != len(set(capability_ids)):
            raise CapabilityError("duplicate snapshot capability")
        if capability_ids != sorted(capability_ids):
            raise CapabilityError("snapshot capabilities must be canonical order")
        result = cls(registry_digest, tuple(capabilities))
        if not isinstance(value["healthy"], bool):
            raise CapabilityError("capability snapshot health must be boolean")
        if value["healthy"] is not result.healthy:
            raise CapabilityError("capability snapshot health mismatch")
        if value["digest"] != result.digest:
            raise CapabilityError("capability snapshot digest mismatch")
        return result


class CapabilityMap:
    """Resolve exact live capability guarantees without fallback."""

    def __init__(
        self,
        descriptors: Iterable[CapabilityDescriptor],
        evidence: Iterable[CapabilityEvidence],
    ) -> None:
        try:
            materialized_descriptors = tuple(
                islice(iter(descriptors), _MAX_CAPABILITIES + 1)
            )
        except TypeError as exc:
            raise TypeError("descriptors must be iterable") from exc
        try:
            materialized_evidence = tuple(
                islice(iter(evidence), _MAX_CAPABILITIES + 1)
            )
        except TypeError as exc:
            raise TypeError("evidence must be iterable") from exc

        if len(materialized_descriptors) > _MAX_CAPABILITIES:
            raise CapabilityError("capability count exceeds safety bound")
        if len(materialized_evidence) > _MAX_CAPABILITIES:
            raise CapabilityError("evidence count exceeds safety bound")
        if any(
            not isinstance(item, CapabilityDescriptor)
            for item in materialized_descriptors
        ):
            raise TypeError("descriptors must contain CapabilityDescriptor")
        if any(
            not isinstance(item, CapabilityEvidence)
            for item in materialized_evidence
        ):
            raise TypeError("evidence must contain CapabilityEvidence")

        descriptor_ids = [
            item.capability_id for item in materialized_descriptors
        ]
        if len(descriptor_ids) != len(set(descriptor_ids)):
            raise CapabilityError("duplicate capability descriptor")

        evidence_ids = [
            item.evidence_id for item in materialized_evidence
        ]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise CapabilityError("duplicate capability evidence id")

        evidence_capabilities = [
            item.capability_id for item in materialized_evidence
        ]
        if len(evidence_capabilities) != len(set(evidence_capabilities)):
            raise CapabilityError(
                "multiple live evidence records for capability"
            )

        self.descriptors = {
            item.capability_id: item
            for item in sorted(
                materialized_descriptors,
                key=lambda item: item.capability_id,
            )
        }
        self.evidence = {
            item.capability_id: item
            for item in sorted(
                materialized_evidence,
                key=lambda item: item.capability_id,
            )
        }

        for descriptor in self.descriptors.values():
            missing = [
                dependency_id
                for dependency_id in descriptor.dependency_ids
                if dependency_id not in self.descriptors
            ]
            if missing:
                raise CapabilityError(
                    "unknown capability dependency: " + ",".join(missing)
                )

        for item in self.evidence.values():
            if item.capability_id not in self.descriptors:
                raise CapabilityError(
                    "evidence references unknown capability"
                )

        self._reject_dependency_cycles()

    def _reject_dependency_cycles(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(capability_id: str) -> None:
            if capability_id in visited:
                return
            if capability_id in visiting:
                raise CapabilityError("capability dependency cycle")
            visiting.add(capability_id)
            for dependency_id in (
                self.descriptors[capability_id].dependency_ids
            ):
                visit(dependency_id)
            visiting.remove(capability_id)
            visited.add(capability_id)

        for capability_id in self.descriptors:
            visit(capability_id)

    @property
    def digest(self) -> str:
        return _digest(
            [
                CAPABILITY_MAP_SCHEMA,
                [item.digest for item in self.descriptors.values()],
                [item.digest for item in self.evidence.values()],
            ]
        )

    def descriptor(self, capability_id: str) -> CapabilityDescriptor:
        capability_id = _id(capability_id, "capability_id")
        try:
            return self.descriptors[capability_id]
        except KeyError as exc:
            raise CapabilityError("unknown capability") from exc

    def resolve(self, capability_id: str) -> CapabilityAvailability:
        capability_id = self.descriptor(capability_id).capability_id
        cache: dict[str, CapabilityAvailability] = {}

        def resolve_one(current_id: str) -> CapabilityAvailability:
            cached = cache.get(current_id)
            if cached is not None:
                return cached

            descriptor = self.descriptors[current_id]
            if descriptor.maturity is Maturity.PLANNED:
                resolved = CapabilityAvailability(
                    current_id,
                    Availability.UNAVAILABLE,
                    (),
                    "planned_not_live",
                    None,
                )
                cache[current_id] = resolved
                return resolved

            live = self.evidence.get(current_id)
            if live is None:
                resolved = CapabilityAvailability(
                    current_id,
                    Availability.UNAVAILABLE,
                    (),
                    "no_live_evidence",
                    None,
                )
                cache[current_id] = resolved
                return resolved

            if live.descriptor_digest != descriptor.digest:
                resolved = CapabilityAvailability(
                    current_id,
                    Availability.UNAVAILABLE,
                    (),
                    "descriptor_evidence_mismatch",
                    live.digest,
                )
                cache[current_id] = resolved
                return resolved

            unsupported = sorted(
                set(live.guarantees) - set(descriptor.guarantees)
            )
            if unsupported:
                resolved = CapabilityAvailability(
                    current_id,
                    Availability.UNAVAILABLE,
                    (),
                    (
                        "evidence_claims_undeclared_guarantee:"
                        + ",".join(unsupported)
                    ),
                    live.digest,
                )
                cache[current_id] = resolved
                return resolved

            if live.state is Availability.UNAVAILABLE:
                resolved = CapabilityAvailability(
                    current_id,
                    Availability.UNAVAILABLE,
                    (),
                    live.reason,
                    live.digest,
                )
                cache[current_id] = resolved
                return resolved

            dependencies = tuple(
                resolve_one(dependency_id)
                for dependency_id in descriptor.dependency_ids
            )
            dependency_states = tuple(
                (item.capability_id, item.state)
                for item in dependencies
            )
            bad_dependencies = tuple(
                item
                for item in dependencies
                if item.state is not Availability.AVAILABLE
            )

            live_guarantees = tuple(
                sorted(
                    set(live.guarantees)
                    & set(descriptor.guarantees)
                )
            )
            missing_guarantees = tuple(
                sorted(
                    set(descriptor.guarantees)
                    - set(live_guarantees)
                )
            )

            if bad_dependencies:
                reason = "dependency:" + ",".join(
                    f"{item.capability_id}={item.state.value}"
                    for item in bad_dependencies
                )
                resolved = CapabilityAvailability(
                    current_id,
                    Availability.DEGRADED,
                    live_guarantees,
                    reason,
                    live.digest,
                    dependency_states,
                )
            elif live.state is Availability.DEGRADED:
                resolved = CapabilityAvailability(
                    current_id,
                    Availability.DEGRADED,
                    live_guarantees,
                    live.reason,
                    live.digest,
                    dependency_states,
                )
            elif missing_guarantees:
                resolved = CapabilityAvailability(
                    current_id,
                    Availability.DEGRADED,
                    live_guarantees,
                    (
                        "missing_live_guarantee:"
                        + ",".join(missing_guarantees)
                    ),
                    live.digest,
                    dependency_states,
                )
            else:
                resolved = CapabilityAvailability(
                    current_id,
                    Availability.AVAILABLE,
                    live_guarantees,
                    "",
                    live.digest,
                    dependency_states,
                )

            cache[current_id] = resolved
            return resolved

        return resolve_one(capability_id)

    def resolve_all(self) -> CapabilitySnapshot:
        return CapabilitySnapshot(
            self.digest,
            tuple(
                self.resolve(capability_id)
                for capability_id in self.descriptors
            ),
        )

    def require(
        self,
        capability_id: str,
        *,
        guarantees: tuple[str, ...] | None = None,
    ) -> CapabilityDescriptor:
        descriptor = self.descriptor(capability_id)
        requested = (
            descriptor.guarantees
            if guarantees is None
            else _normalize_guarantees(guarantees)
        )
        undeclared = tuple(
            sorted(set(requested) - set(descriptor.guarantees))
        )
        if undeclared:
            raise CapabilityError(
                "capability does not declare guarantee: "
                + ",".join(undeclared)
            )

        resolved = self.resolve(capability_id)
        if resolved.state is not Availability.AVAILABLE:
            raise CapabilityError(
                "capability guarantee unavailable: " + resolved.reason
            )

        missing = tuple(
            sorted(set(requested) - set(resolved.guarantees))
        )
        if missing:
            raise CapabilityError(
                "capability guarantee unavailable: " + ",".join(missing)
            )
        return descriptor


__all__ = [
    "CAPABILITY_MAP_SCHEMA",
    "Availability",
    "CapabilityAvailability",
    "CapabilityDescriptor",
    "CapabilityError",
    "CapabilityEvidence",
    "CapabilityMap",
    "CapabilitySnapshot",
    "Maturity",
]
