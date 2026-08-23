"""The capability registry.

A named, versioned catalogue of everything the platform can do: pipeline
kinds, forge blueprint kinds, agent specialisations. Registrations are
validated for uniqueness and semver shape; health is recorded per-capability;
every mutation emits a domain event so observers (metrics, the
``/capabilities`` endpoint) never hold a stale view.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable

from skeleton.kernel.errors import (
    CapabilityNotFoundError,
    DuplicateCapabilityError,
    RegistryError,
)
from skeleton.kernel.events import EventBus


class CapabilityKind(str, Enum):
    PIPELINE = "pipeline"
    FORGE_BLUEPRINT = "forge_blueprint"
    AGENT_SPECIALISATION = "agent_specialisation"
    TOOL = "tool"


class HealthState(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass(frozen=True)
class Version:
    """Semantic version with comparison."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, raw: str) -> "Version":
        parts = raw.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise RegistryError(
                f"Invalid semver {raw!r}", context={"version": raw}
            )
        return cls(int(parts[0]), int(parts[1]), int(parts[2]))

    def compatible_with(self, other: "Version") -> bool:
        """Semver compatibility: same major, this minor >= other minor."""
        return self.major == other.major and self >= other

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def __lt__(self, other: "Version") -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __le__(self, other: "Version") -> bool:
        return self == other or self < other

    def __ge__(self, other: "Version") -> bool:
        return not self < other


@dataclass
class Capability:
    """A registered capability record."""

    name: str
    kind: CapabilityKind
    version: Version
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    handler: Callable[..., Any] | None = None
    health: HealthState = HealthState.UNKNOWN
    health_detail: str = ""
    registered_at: float = field(default_factory=time.time)
    invocation_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "version": str(self.version),
            "description": self.description,
            "metadata": self.metadata,
            "health": self.health.value,
            "health_detail": self.health_detail,
            "registered_at": self.registered_at,
            "invocation_count": self.invocation_count,
        }


class CapabilityRegistry:
    """Thread-free in-process registry of platform capabilities."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._capabilities: dict[str, Capability] = {}
        self._bus = bus or EventBus()

    # -- registration ------------------------------------------------------

    def register(
        self,
        name: str,
        kind: CapabilityKind,
        version: str | Version,
        *,
        description: str = "",
        metadata: dict[str, Any] | None = None,
        handler: Callable[..., Any] | None = None,
        replace: bool = False,
    ) -> Capability:
        """Register a capability, emitting ``registry.capability.registered``."""
        if not name or "." in name:
            raise RegistryError(
                "Capability names must be non-empty and contain no dots",
                context={"name": name},
            )
        fq = f"{kind.value}:{name}"
        if fq in self._capabilities and not replace:
            raise DuplicateCapabilityError(
                f"Capability {fq!r} is already registered", context={"name": fq}
            )
        ver = version if isinstance(version, Version) else Version.parse(version)
        cap = Capability(
            name=name,
            kind=kind,
            version=ver,
            description=description,
            metadata=metadata or {},
            handler=handler,
        )
        self._capabilities[fq] = cap
        self._bus.emit("registry.capability.registered", cap.to_dict())
        return cap

    def deregister(self, kind: CapabilityKind, name: str) -> Capability:
        fq = f"{kind.value}:{name}"
        cap = self._capabilities.pop(fq, None)
        if cap is None:
            raise CapabilityNotFoundError(
                f"Capability {fq!r} is not registered", context={"name": fq}
            )
        self._bus.emit("registry.capability.deregistered", cap.to_dict())
        return cap

    # -- lookup ------------------------------------------------------------

    def get(self, kind: CapabilityKind, name: str) -> Capability:
        fq = f"{kind.value}:{name}"
        cap = self._capabilities.get(fq)
        if cap is None:
            raise CapabilityNotFoundError(
                f"Capability {fq!r} is not registered",
                context={"name": fq, "available": sorted(self._capabilities)},
            )
        return cap

    def has(self, kind: CapabilityKind, name: str) -> bool:
        return f"{kind.value}:{name}" in self._capabilities

    def list(self, kind: CapabilityKind | None = None) -> list[Capability]:
        caps = self._capabilities.values()
        if kind is not None:
            caps = [c for c in caps if c.kind is kind]
        return sorted(caps, key=lambda c: (c.kind.value, c.name))

    def find_compatible(
        self, kind: CapabilityKind, name: str, minimum: str
    ) -> Capability:
        """Find a registered capability whose version is semver-compatible."""
        cap = self.get(kind, name)
        required = Version.parse(minimum)
        if not cap.version.compatible_with(required):
            raise RegistryError(
                f"{kind.value}:{name} v{cap.version} does not satisfy >={minimum}",
                context={"found": str(cap.version), "required": minimum},
            )
        return cap

    # -- health & accounting -------------------------------------------------

    def record_health(
        self, kind: CapabilityKind, name: str, state: HealthState, detail: str = ""
    ) -> None:
        cap = self.get(kind, name)
        previous = cap.health
        cap.health = state
        cap.health_detail = detail
        if previous is not state:
            self._bus.emit(
                "registry.capability.health_changed",
                {
                    "name": cap.name,
                    "kind": cap.kind.value,
                    "from": previous.value,
                    "to": state.value,
                    "detail": detail,
                },
            )

    def record_invocation(self, kind: CapabilityKind, name: str) -> None:
        self.get(kind, name).invocation_count += 1

    # -- introspection -------------------------------------------------------

    def unhealthy(self) -> list[Capability]:
        return [c for c in self.list() if c.health in (HealthState.DEGRADED, HealthState.DOWN)]

    def snapshot(self) -> dict[str, Any]:
        return {
            "total": len(self._capabilities),
            "by_kind": {
                kind.value: sum(1 for c in self._capabilities.values() if c.kind is kind)
                for kind in CapabilityKind
            },
            "unhealthy": [c.name for c in self.unhealthy()],
        }


def bootstrap_registry(bus: EventBus, extra: Iterable[tuple[str, CapabilityKind, str]] = ()) -> CapabilityRegistry:
    """Build the registry pre-loaded with Skeleton's core capabilities."""
    registry = CapabilityRegistry(bus)
    core: list[tuple[str, CapabilityKind, str]] = [
        ("npc", CapabilityKind.PIPELINE, "16.0.0"),
        ("game_logic", CapabilityKind.PIPELINE, "16.0.0"),
        ("animation", CapabilityKind.PIPELINE, "16.0.0"),
        ("universal", CapabilityKind.FORGE_BLUEPRINT, "16.0.0"),
        ("tutoring", CapabilityKind.AGENT_SPECIALISATION, "16.0.0"),
        ("co_coding", CapabilityKind.AGENT_SPECIALISATION, "16.0.0"),
    ]
    for name, kind, version in [*core, *extra]:
        registry.register(name, kind, version)
    return registry
