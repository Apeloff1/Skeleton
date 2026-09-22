"""Dependency-aware planning for the assembled Skeleton application.

The application manifest is the source of truth for service ownership and
dependencies. This module turns that declarative topology into a deterministic
startup plan that can be inspected by humans, consumed by automation, and used
by the launcher itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from skeleton.app.assembly import AssemblyManifest, load_manifest


@dataclass(frozen=True)
class AssemblyPlan:
    """A deterministic dependency-closed service startup plan."""

    profile: str
    requested: tuple[str, ...]
    services: tuple[str, ...]
    layers: tuple[tuple[str, ...], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile,
            "requested": list(self.requested),
            "services": list(self.services),
            "layers": [list(layer) for layer in self.layers],
        }


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


def dependency_closure(
    manifest: AssemblyManifest,
    requested: Iterable[str],
) -> tuple[str, ...]:
    """Return requested services plus all transitive dependencies."""

    requested_tuple = _ordered_unique(str(item) for item in requested)
    unknown = set(requested_tuple) - set(manifest.service_names)
    if unknown:
        raise ValueError(f"unknown services requested: {sorted(unknown)}")

    required = set(requested_tuple)
    pending = list(requested_tuple)
    while pending:
        name = pending.pop()
        for dependency in manifest.service(name).depends_on:
            if dependency in required:
                continue
            required.add(dependency)
            pending.append(dependency)

    return tuple(name for name in manifest.service_names if name in required)


def _topological_layers(
    manifest: AssemblyManifest,
    services: tuple[str, ...],
) -> tuple[tuple[str, ...], ...]:
    active = set(services)
    dependencies = {
        name: {dep for dep in manifest.service(name).depends_on if dep in active}
        for name in services
    }
    layers: list[tuple[str, ...]] = []
    emitted: set[str] = set()

    while len(emitted) < len(services):
        ready = tuple(
            name
            for name in services
            if name not in emitted and dependencies[name].issubset(emitted)
        )
        if not ready:
            blocked = {
                name: sorted(dependencies[name] - emitted)
                for name in services
                if name not in emitted
            }
            raise ValueError(f"service dependency cycle detected: {blocked}")
        layers.append(ready)
        emitted.update(ready)

    return tuple(layers)


def build_plan(
    *,
    manifest: AssemblyManifest | None = None,
    full: bool = False,
    requested: Iterable[str] | None = None,
) -> AssemblyPlan:
    """Build a deterministic dependency-closed startup plan."""

    manifest = manifest or load_manifest()
    if requested is None:
        requested_tuple = manifest.full_services if full else manifest.default_services
        profile = "full" if full else "default"
    else:
        requested_tuple = _ordered_unique(str(item) for item in requested)
        profile = "custom"

    services = dependency_closure(manifest, requested_tuple)
    layers = _topological_layers(manifest, services)
    ordered = tuple(name for layer in layers for name in layer)
    return AssemblyPlan(
        profile=profile,
        requested=requested_tuple,
        services=ordered,
        layers=layers,
    )


def validate_manifest_topology(
    manifest: AssemblyManifest | None = None,
) -> tuple[AssemblyPlan, AssemblyPlan]:
    """Validate both canonical profiles and return their executable plans."""

    manifest = manifest or load_manifest()
    default = build_plan(manifest=manifest, full=False)
    full = build_plan(manifest=manifest, full=True)

    default_set = set(default.services)
    full_set = set(full.services)
    if not default_set.issubset(full_set):
        missing = sorted(default_set - full_set)
        raise ValueError(f"full profile does not contain default topology: {missing}")

    return default, full
