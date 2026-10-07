"""Deterministic workload profiles for ECS regression and scale testing.

Profiles generate repeatable worlds without random state or external fixtures.
They are intentionally lightweight: the goal is reproducible contract and
performance harness input, not synthetic benchmark score inflation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .canonical import digest
from .errors import BoundsError, ValidationError
from .schema import FieldKind, FieldSpec, SchemaRegistry, make_schema
from .store import EntityStore

MAX_PROFILE_ENTITIES = 100_000
MAX_PROFILE_ZONES = 1024


@dataclass(frozen=True)
class WorkloadProfile:
    name: str
    entity_count: int
    zone_count: int = 8
    health_span: int = 100
    include_velocity: bool = True
    include_names: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValidationError("profile name must be non-empty text")
        if isinstance(self.entity_count, bool) or not isinstance(self.entity_count, int):
            raise ValidationError("profile entity_count must be integer")
        if not 0 <= self.entity_count <= MAX_PROFILE_ENTITIES:
            raise BoundsError(
                "profile entity_count outside supported range",
                context={"maximum": MAX_PROFILE_ENTITIES},
            )
        if isinstance(self.zone_count, bool) or not isinstance(self.zone_count, int):
            raise ValidationError("profile zone_count must be integer")
        if not 1 <= self.zone_count <= MAX_PROFILE_ZONES:
            raise BoundsError("profile zone_count outside supported range")
        if isinstance(self.health_span, bool) or not isinstance(self.health_span, int):
            raise ValidationError("profile health_span must be integer")
        if self.health_span < 1:
            raise ValidationError("profile health_span must be positive")
        if not isinstance(self.include_velocity, bool):
            raise ValidationError("include_velocity must be boolean")
        if not isinstance(self.include_names, bool):
            raise ValidationError("include_names must be boolean")

    @property
    def fingerprint(self) -> str:
        return digest(
            {
                "domain": "skeleton.simulation.ecs.workload_profile.v1",
                "name": self.name,
                "entity_count": self.entity_count,
                "zone_count": self.zone_count,
                "health_span": self.health_span,
                "include_velocity": self.include_velocity,
                "include_names": self.include_names,
            }
        )


@dataclass(frozen=True)
class ProfileBuildResult:
    profile: WorkloadProfile
    store: EntityStore
    state_digest: str
    registry_fingerprint: str
    entities: int
    components: int
    build_digest: str


@dataclass(frozen=True)
class ProfileComparison:
    left_digest: str
    right_digest: str
    equal: bool
    left_entities: int
    right_entities: int
    left_components: int
    right_components: int
    comparison_digest: str


def profile_registry() -> SchemaRegistry:
    registry = SchemaRegistry()
    registry.register(
        make_schema(
            "profile.position",
            1,
            (
                FieldSpec("x", FieldKind.FLOAT),
                FieldSpec("y", FieldKind.FLOAT),
                FieldSpec("zone", FieldKind.INT, minimum=0),
            ),
            description="Deterministic profile position.",
        )
    )
    registry.register(
        make_schema(
            "profile.health",
            1,
            (
                FieldSpec("current", FieldKind.INT, minimum=0),
                FieldSpec("maximum", FieldKind.INT, minimum=1),
                FieldSpec("alive", FieldKind.BOOL, default=True),
            ),
            description="Deterministic profile health.",
        )
    )
    registry.register(
        make_schema(
            "profile.velocity",
            1,
            (
                FieldSpec("x", FieldKind.FLOAT),
                FieldSpec("y", FieldKind.FLOAT),
            ),
        )
    )
    registry.register(
        make_schema(
            "profile.name",
            1,
            (FieldSpec("value", FieldKind.TEXT),),
        )
    )
    return registry


def _entity_id(index: int) -> str:
    return f"profile:{index:08d}"


def _position(index: int, profile: WorkloadProfile) -> dict[str, Any]:
    zone = index % profile.zone_count
    x = float((index * 17 + zone * 3) % 10_000) / 10.0
    y = float((index * 31 + zone * 7) % 10_000) / 10.0
    return {"x": x, "y": y, "zone": zone}


def _health(index: int, profile: WorkloadProfile) -> dict[str, Any]:
    maximum = profile.health_span
    current = maximum - (index % maximum)
    return {"current": current, "maximum": maximum, "alive": current > 0}


def _velocity(index: int) -> dict[str, Any]:
    x = float(((index * 5) % 21) - 10) / 10.0
    y = float(((index * 11) % 21) - 10) / 10.0
    return {"x": x, "y": y}


def build_profile_store(profile: WorkloadProfile) -> ProfileBuildResult:
    if not isinstance(profile, WorkloadProfile):
        raise ValidationError("build_profile_store requires WorkloadProfile")
    registry = profile_registry()
    store = EntityStore(registry)
    for index in range(profile.entity_count):
        entity_id = _entity_id(index)
        store.create_entity(entity_id)
        store.set_component(entity_id, "profile.position", _position(index, profile))
        store.set_component(entity_id, "profile.health", _health(index, profile))
        if profile.include_velocity:
            store.set_component(entity_id, "profile.velocity", _velocity(index))
        if profile.include_names:
            store.set_component(
                entity_id,
                "profile.name",
                {"value": f"entity-{index:08d}"},
            )
    state_digest = store.state_digest
    material = {
        "domain": "skeleton.simulation.ecs.profile_build.v1",
        "profile": profile.fingerprint,
        "state_digest": state_digest,
        "registry": registry.fingerprint,
        "entities": store.entity_count,
        "components": store.component_count,
    }
    return ProfileBuildResult(
        profile=profile,
        store=store,
        state_digest=state_digest,
        registry_fingerprint=registry.fingerprint,
        entities=store.entity_count,
        components=store.component_count,
        build_digest=digest(material),
    )


def compare_profile_builds(
    left: ProfileBuildResult,
    right: ProfileBuildResult,
) -> ProfileComparison:
    if not isinstance(left, ProfileBuildResult) or not isinstance(right, ProfileBuildResult):
        raise ValidationError("compare_profile_builds requires ProfileBuildResult values")
    equal = (
        left.state_digest == right.state_digest
        and left.registry_fingerprint == right.registry_fingerprint
        and left.entities == right.entities
        and left.components == right.components
    )
    material = {
        "domain": "skeleton.simulation.ecs.profile_comparison.v1",
        "left": left.build_digest,
        "right": right.build_digest,
        "equal": equal,
    }
    return ProfileComparison(
        left_digest=left.state_digest,
        right_digest=right.state_digest,
        equal=equal,
        left_entities=left.entities,
        right_entities=right.entities,
        left_components=left.components,
        right_components=right.components,
        comparison_digest=digest(material),
    )


def profile_matrix() -> tuple[WorkloadProfile, ...]:
    """Return small deterministic profiles appropriate for CI contract runs."""

    return (
        WorkloadProfile("empty", 0),
        WorkloadProfile("tiny", 8, zone_count=2),
        WorkloadProfile("small", 64, zone_count=4),
        WorkloadProfile(
            "positions-health-only",
            32,
            zone_count=4,
            include_velocity=False,
            include_names=False,
        ),
    )
