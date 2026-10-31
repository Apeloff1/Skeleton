"""Twenty real 3D game trigger and force-field authoring operations.

Resulting source types compile through existing native Godot zone/physics
descriptors. Actor bindings are exact placed prefab identities, not placeholders.
"""
from __future__ import annotations

from dataclasses import replace
import math
from typing import Any, Mapping

from .game_frontier_studio import (
    StudioProject, StudioError, StudioTriggerVolume, StudioForceField,
)
from .game_frontier_studio_map_edit import _name

ZONE_ACTIONS = (
    "zone_add", "zone_remove", "zone_clone", "zone_bind_actor",
    "zone_bind_event", "zone_radius", "zone_offset", "zone_translate",
    "zone_scale", "zone_duplicate_to_actor",
)
FIELD_ACTIONS = (
    "field_add", "field_remove", "field_clone", "field_bind_actor",
    "field_kind", "field_radius", "field_strength", "field_offset",
    "field_invert", "field_duplicate_to_actor",
)
PHYSICAL_ACTIONS = ZONE_ACTIONS + FIELD_ACTIONS


def _finite(args: Mapping[str, Any], name: str, *, default=None,
            lo: float = -10000., hi: float = 10000.) -> float:
    value = args.get(name, default)
    if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
        raise StudioError(f"{name} must be a bounded finite game coordinate/quantity")
    return float(value)


def _offset(args: Mapping[str, Any], *, prefix: str = "") -> tuple[float, float, float]:
    return tuple(_finite(args, prefix + name, default=0) for name in ("x", "y", "z"))


def _actor(project: StudioProject, args: Mapping[str, Any], key: str = "actor_id") -> str:
    actor = _name(args, key)
    if actor not in {p.prefab_id + ":" + str(i) for i, p in enumerate(project.placements)}:
        raise StudioError("selected 3D volume/field actor does not exist")
    return actor


def _event(project: StudioProject, args: Mapping[str, Any]) -> str:
    ident = _name(args, "event_id")
    if ident not in {event.event_id for event in project.events}:
        raise StudioError("native zone must bind a currently authored event")
    return ident


def _entry(items: tuple, ident: str, attr: str):
    for index, value in enumerate(items):
        if getattr(value, attr) == ident:
            return index, value
    raise StudioError("authored 3D object is not present")


def _replace(items: tuple, position: int, value: object) -> tuple:
    return items[:position] + (value,) + items[position + 1:]


def edit_physical(project: StudioProject, operation: str,
                  args: Mapping[str, Any]) -> StudioProject:
    if not isinstance(project, StudioProject) or operation not in PHYSICAL_ACTIONS or not isinstance(args, Mapping):
        raise StudioError("unknown native game physics/trigger operation")
    if operation == "zone_add":
        zone = StudioTriggerVolume(
            _name(args, "zone_id"), _actor(project, args), _event(project, args),
            _finite(args, "radius_m", lo=.1), _offset(args))
        if any(v.zone_id == zone.zone_id for v in project.native_trigger_volumes):
            raise StudioError("duplicate native game zone")
        return replace(project, native_trigger_volumes=project.native_trigger_volumes + (zone,))
    if operation.startswith("zone_"):
        position, zone = _entry(project.native_trigger_volumes, _name(args, "zone_id"), "zone_id")
        if operation == "zone_remove":
            return replace(project, native_trigger_volumes=(
                project.native_trigger_volumes[:position] +
                project.native_trigger_volumes[position + 1:]))
        if operation in ("zone_clone", "zone_duplicate_to_actor"):
            name = _name(args, "new_zone_id")
            if any(z.zone_id == name for z in project.native_trigger_volumes):
                raise StudioError("target zone identity already exists")
            actor = (_actor(project, args, "new_actor_id")
                     if operation == "zone_duplicate_to_actor" else zone.actor_entity_id)
            new = replace(zone, zone_id=name, actor_entity_id=actor)
            return replace(project, native_trigger_volumes=project.native_trigger_volumes + (new,))
        if operation == "zone_bind_actor":
            zone = replace(zone, actor_entity_id=_actor(project, args))
        elif operation == "zone_bind_event":
            zone = replace(zone, event_page_id=_event(project, args))
        elif operation == "zone_radius":
            zone = replace(zone, radius_m=_finite(args, "radius_m", lo=.1))
        elif operation == "zone_offset":
            zone = replace(zone, offset_xyz_m=_offset(args))
        elif operation == "zone_translate":
            delta = _offset(args, prefix="d")
            zone = replace(zone, offset_xyz_m=tuple(
                old + step for old, step in zip(zone.offset_xyz_m, delta)))
        elif operation == "zone_scale":
            factor = _finite(args, "factor", lo=.001, hi=100.)
            zone = replace(zone, radius_m=zone.radius_m * factor)
        else:
            raise StudioError("zone operation is unsupported")
        return replace(project, native_trigger_volumes=_replace(
            project.native_trigger_volumes, position, zone))
    if operation == "field_add":
        field = StudioForceField(
            _name(args, "field_id"), _actor(project, args),
            _name(args, "kind"),
            _finite(args, "radius_m", lo=.1),
            _finite(args, "acceleration_mps2", lo=0, hi=25),
            _offset(args),
        )
        if any(f.field_id == field.field_id for f in project.native_gameplay_force_fields):
            raise StudioError("duplicate native physics field")
        return replace(project, native_gameplay_force_fields=project.native_gameplay_force_fields + (field,))
    position, field = _entry(project.native_gameplay_force_fields,
                             _name(args, "field_id"), "field_id")
    if operation == "field_remove":
        return replace(project, native_gameplay_force_fields=(
            project.native_gameplay_force_fields[:position] +
            project.native_gameplay_force_fields[position + 1:]))
    if operation in ("field_clone", "field_duplicate_to_actor"):
        name = _name(args, "new_field_id")
        if any(f.field_id == name for f in project.native_gameplay_force_fields):
            raise StudioError("duplicate field identity")
        actor = (_actor(project, args, "new_actor_id")
                 if operation == "field_duplicate_to_actor" else field.actor_entity_id)
        result = replace(field, field_id=name, actor_entity_id=actor)
        return replace(project, native_gameplay_force_fields=(
            project.native_gameplay_force_fields + (result,)))
    if operation == "field_bind_actor":
        field = replace(field, actor_entity_id=_actor(project, args))
    elif operation == "field_kind":
        field = replace(field, kind=_name(args, "kind"))
    elif operation == "field_radius":
        field = replace(field, radius_m=_finite(args, "radius_m", lo=.1))
    elif operation == "field_strength":
        field = replace(field, acceleration_mps2=_finite(
            args, "acceleration_mps2", lo=0, hi=25))
    elif operation == "field_offset":
        field = replace(field, center_offset_xyz_m=_offset(args))
    elif operation == "field_invert":
        flips = {"updraft": "downdraft", "downdraft": "updraft"}
        if field.kind not in flips:
            raise StudioError("only signed vertical force fields can be inverted")
        field = replace(field, kind=flips[field.kind])
    else:
        raise StudioError("field operation is unsupported")
    return replace(project, native_gameplay_force_fields=_replace(
        project.native_gameplay_force_fields, position, field))
