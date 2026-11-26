"""Admit a scene candidate only when its signed receipt matches the digest.

The signature check is the existing Jeeves runtime-authorisation HMAC. A
mismatch raises before the caller commits a step.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from skeleton.jeeves.game_frontier_runtime_binding import (
    CANDIDATE_SCHEMA,
    RuntimeAuthorisation,
    RuntimeBindingError,
    digest_of,
    route_runtime_outputs,
    verify_authorisation,
)

from skeleton.frontier_runtime.state import (
    StepRejected,
    WeatherState,
    WorldState,
    with_updates,
)


def admit_scene_candidate(
    candidate: object,
    authorisation: object,
    *,
    key: bytes,
    now_ms: int,
) -> Mapping[str, object]:
    """Return the candidate manifest when the receipt matches its digest."""
    if not isinstance(authorisation, RuntimeAuthorisation):
        raise StepRejected("signed receipt required")
    try:
        verify_authorisation(authorisation, key=key, now_ms=now_ms)
    except RuntimeBindingError as exc:
        raise StepRejected(str(exc)) from exc
    manifest = getattr(candidate, "manifest", None)
    claimed = getattr(candidate, "manifest_digest", None)
    if not isinstance(manifest, Mapping) or type(claimed) is not str:
        raise StepRejected("scene candidate required")
    if digest_of(manifest) != claimed:
        raise StepRejected("candidate digest mismatch")
    if claimed != authorisation.candidate_digest:
        raise StepRejected("receipt digest mismatch")
    if getattr(candidate, "approved_for_runtime", None) is not False:
        raise StepRejected("candidate must arrive unadmitted")
    if manifest.get("schema") != CANDIDATE_SCHEMA:
        raise StepRejected("unsupported candidate schema")
    render = manifest.get("render") if isinstance(manifest.get("render"), Mapping) else {}
    if render.get("era") != authorisation.era:
        raise StepRejected("receipt era mismatch")
    return manifest


def apply_scene_candidate(world: WorldState, manifest: Mapping[str, object], binding_era: str) -> WorldState:
    """Copy admitted candidate channel outputs onto the world that will be stepped.

    Unknown ids are rejected. The returned world is a new value; the caller's
    committed snapshot is unchanged until the whole step succeeds.
    """
    try:
        outputs, _dropped = route_runtime_outputs(manifest, binding_era)
    except RuntimeBindingError as exc:
        raise StepRejected(str(exc)) from exc
    weather = world.weather
    nodes = list(world.soft_nodes)
    structures = list(world.structures)
    character = world.character
    nodes_by_id = {node.node_id: index for index, node in enumerate(nodes)}
    structures_by_id = {item.structure_id: index for index, item in enumerate(structures)}
    for output in outputs:
        payload = output.payload
        if output.channel == "weather":
            weather = WeatherState(
                wind=tuple(payload["wind_xyz"]),  # type: ignore[arg-type]
                temperature_c=float(payload["temperature_c"]),  # type: ignore[arg-type]
                precipitation_mm_h=float(payload["rain_mm_h"]),  # type: ignore[arg-type]
                humidity=weather.humidity,
                water_depth_m=float(payload["water_depth_m"]),  # type: ignore[arg-type]
                sunlight=weather.sunlight,
                snow_depth_m=float(payload["snow_depth_m"]),  # type: ignore[arg-type]
                airborne_dust=weather.airborne_dust,
            )
        elif output.channel == "soft_body":
            node_id = output.node_path.rsplit("/", 1)[-1]
            index = nodes_by_id.get(node_id)
            if index is None:
                raise StepRejected(f"candidate soft body {node_id} is not in the world")
            current = nodes[index]
            if current.material != str(payload["material"]):
                raise StepRejected("candidate soft material does not match the world")
            nodes[index] = replace(
                current,
                position=tuple(payload["xyz"]),  # type: ignore[arg-type]
                wetness=float(payload["wetness"]),  # type: ignore[arg-type]
                temperature_c=float(payload["temperature_c"]),  # type: ignore[arg-type]
            )
        elif output.channel == "lifecycle":
            structure_id = output.node_path.rsplit("/", 1)[-1]
            index = structures_by_id.get(structure_id)
            if index is None:
                raise StepRejected(f"candidate structure {structure_id} is not in the world")
            current = structures[index]
            if current.material != str(payload["material"]):
                raise StepRejected("candidate structure material does not match the world")
            structures[index] = replace(
                current,
                age_days=float(payload["age_days"]),  # type: ignore[arg-type]
                integrity=float(payload["integrity"]),  # type: ignore[arg-type]
                surface_weathering=float(payload["weathering"]),  # type: ignore[arg-type]
                maintenance_debt=float(payload["maintenance_debt"]),  # type: ignore[arg-type]
            )
        elif output.channel == "character_collision":
            if character is None:
                raise StepRejected("candidate character is not in the world")
            character = replace(
                character,
                position=tuple(payload["position"]),  # type: ignore[arg-type]
                velocity=tuple(payload["velocity"]),  # type: ignore[arg-type]
            )
        else:
            raise StepRejected(f"unsupported candidate channel {output.channel}")
    claimed = digest_of(manifest)
    return with_updates(
        world,
        weather=weather,
        soft_nodes=tuple(nodes),
        structures=tuple(structures),
        character=character,
        admitted_candidate_digest=claimed,
    )
