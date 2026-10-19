"""Single candidate-only composition entry point for the frontier game milestones.

This module joins *existing Jeeves-owned* deterministic game components. It
does not open GPU providers, mutate world state, or certify neural-model output.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Iterable

from .game_frontier_dynamics import (
    Cloud, InputObservation, PresentationClock, WindField, WorldAxis,
    advect_clouds, anticipate_user_motion, generate_world_cell,
)
from .game_frontier_production import (
    AnimationClip, CharacterSkeleton, Percept, plan_cinematic,
    pose_skinned_mesh, reason_about_world, skeleton_to_polygon, Vec3,
)
from .game_frontier_worlds import (
    WorldVariant, CameraSpec, variant_world_cell, project_scene,
)
from .game_frontier_motion import (
    Weather, CharacterState, CharacterStep, CollisionPlane,
    SoftNode, EnvironmentalState, StructureState,
    simulate_character, simulate_soft_nodes, advance_environment, age_structure,
)
from .game_frontier_lighting import (
    SurfaceSample, LightSource, RayOccluder, illuminate_scene,
)

FRONTIER_SCENE_SCHEMA = "skeleton.game.frontier_scene_candidate.v1"
FRONTIER_MODEL_STATUS = "engine_candidate_only_no_proprietary_weights"


@dataclass(frozen=True)
class FrontierSceneCandidate:
    manifest: dict
    manifest_digest: str
    geometry_vertices: tuple
    moved_clouds: tuple[Cloud, ...]
    approved_for_runtime: bool = False
    geometry_triangles: tuple[tuple[int, int, int], ...] = ()
    geometry_colliders: tuple = ()


def compile_frontier_scene(
    *,
    world_axes: WorldAxis,
    cell_x: int,
    cell_y: int,
    wind_field: WindField,
    clouds: Iterable[Cloud],
    time_s: float,
    delta_s: float,
    skeleton: CharacterSkeleton,
    animation: AnimationClip,
    animation_time_ms: int,
    era: str,
    fps: int,
    evidence: Iterable[Percept],
    world_goal_kind: str,
    available_actions: Iterable[str],
    speculative_input: InputObservation | None = None,
    prediction_horizon_ms: int = 100,
    triangle_budget: int | None = None,
    world_variant: WorldVariant | None = None,
    camera: CameraSpec | None = None,
    weather: Weather | None = None,
    character_state: CharacterState | None = None,
    collision_surfaces: tuple[CollisionPlane, ...] = (),
    desired_character_velocity: Vec3 | None = None,
    soft_nodes: tuple[SoftNode, ...] = (),
    soft_anchors: tuple[Vec3, ...] = (),
    environment_state: EnvironmentalState | None = None,
    structures: tuple[StructureState, ...] = (),
    construction_work_days: float = 0,
    maintenance_work_days: float = 0,
    lighting_surfaces: tuple[SurfaceSample, ...] = (),
    light_sources: tuple[LightSource, ...] = (),
    light_occluders: tuple[RayOccluder, ...] = (),
) -> FrontierSceneCandidate:
    """Produce a content-addressed, inspectable, playable-engine-side proposal.

    Authority changes, scene import and model checkpoint inference MUST go
    through the existing engine/forge acceptance and provider-runtime planes.
    A candidate is never marked approved merely because it can be composed.
    """
    cell = generate_world_cell(world_axes, cell_x, cell_y)
    moved = advect_clouds(clouds, wind_field, time_s=time_s, elapsed_s=delta_s)
    clock = PresentationClock(fps)
    mesh = skeleton_to_polygon(skeleton, era, max_triangles=triangle_budget)
    vertices = pose_skinned_mesh(skeleton, mesh, animation, animation_time_ms)
    observations = tuple(evidence)
    cinematic = plan_cinematic(observations)
    next_action = reason_about_world(observations,
                                     goal_kind=world_goal_kind,
                                     available_actions=available_actions)
    variant_cell = (variant_world_cell(world_axes, world_variant, cell_x, cell_y)
                    if world_variant is not None else None)
    points = project_scene(vertices, camera, variant=world_variant) if camera is not None else ()
    physical_weather = weather
    if physical_weather is None and any((character_state is not None, soft_nodes,
                                         environment_state is not None, structures)):
        wind = wind_field.sample(cell_x, cell_y, 0, time_s)
        physical_weather = Weather(Vec3(wind.east_mps, wind.north_mps, 0),
                                   (cell.temperature - .5) * 60,
                                   humidity=cell.humidity)
    # Do not infer authority, run prediction model or mutate host-scene objects.
    if (character_state is not None and desired_character_velocity is None):
        raise ValueError("character simulation requires explicit desired velocity")
    if (soft_nodes or soft_anchors) and physical_weather is None:
        raise ValueError("soft material simulation requires weather")
    character_step = (simulate_character(character_state, physical_weather,
                                         collision_surfaces,
                                         desired_velocity=desired_character_velocity,
                                         delta_s=delta_s)
                      if character_state is not None else None)
    simulated_soft = (simulate_soft_nodes(soft_nodes, physical_weather,
                                           anchors=soft_anchors, delta_s=delta_s)
                      if soft_nodes else ())
    if soft_anchors and not soft_nodes:
        raise ValueError("soft anchors require soft nodes")
    environment_step = (advance_environment(environment_state, physical_weather,
                                            delta_days=delta_s / 86400,
                                            impact=character_step.impacts[0]
                                            if character_step and character_step.impacts else None)
                        if environment_state is not None else None)
    if (construction_work_days or maintenance_work_days) and not structures:
        raise ValueError("construction or maintenance requires structures")
    if len(structures) > 1024:
        raise ValueError("structure batch exceeds limit")
    structure_steps = tuple(
        age_structure(s, physical_weather, elapsed_days=delta_s / 86400,
                      work_days=construction_work_days,
                      maintenance_days=maintenance_work_days,
                      impact=character_step.impacts[0]
                      if character_step and character_step.impacts else None)
        for s in structures
    )
    cloud_coverage = (sum(c.opacity for c in moved) / len(moved)) if moved else 0
    world_luminance = variant_cell.luminance if variant_cell else .7
    ambient = max(.005, .1 * (world_luminance / .7) * (1 - cloud_coverage * .45))
    light_steps = (illuminate_scene(
        lighting_surfaces, light_sources, light_occluders,
        ambient_rgb=(ambient, ambient, ambient),
    ) if lighting_surfaces else ())
    prediction = None
    if speculative_input is not None:
        anticipated = anticipate_user_motion(speculative_input, horizon_ms=prediction_horizon_ms)
        prediction = {
            "x": anticipated.x, "y": anticipated.y,
            "horizon_ms": anticipated.prediction_horizon_ms,
            "confidence_upper_bound": anticipated.confidence_upper_bound,
            "evidence": anticipated.source_digest, "authority": anticipated.authority,
        }
    manifest = {
        "schema": FRONTIER_SCENE_SCHEMA, "model_status": FRONTIER_MODEL_STATUS,
        "world": {
            "seed": world_axes.seed,
            "axis": {"terrain": world_axes.terrain, "moisture": world_axes.moisture,
                     "temperature": world_axes.temperature, "verticality": world_axes.verticality,
                     "sky_islands": world_axes.sky_islands,
                     "weather_volatility": world_axes.weather_volatility},
            "cell": {"x": cell.x, "y": cell.y, "elevation": cell.elevation,
                     "humidity": cell.humidity, "temperature": cell.temperature,
                     "biome": cell.biome, "sky_island": cell.sky_island,
                     "gust_strength": cell.gust_strength},
        },
        "wind_configuration": {"seed": wind_field.seed,
                               "gust_period_s": wind_field.gust_period_s},
        "simulation_time_s": time_s + delta_s,
        "wind": [{"altitude_m": layer.altitude_m,
                  "east_mps": layer.base.east_mps, "north_mps": layer.base.north_mps,
                  "turbulence_mps": layer.turbulence_mps,
                  "cell_size_m": layer.cell_size_m}
                 for layer in wind_field.layers],
        "clouds": [
            {"id": c.cloud_id, "x_m": c.x_m, "y_m": c.y_m,
             "altitude_m": c.altitude_m, "opacity": c.opacity,
             "stretch": c.stretch, "orientation_rad": c.orientation_rad}
            for c in moved
        ],
        "render": {
            "era": era, "fps": clock.fps,
            "next_presentation_deadline_ns": clock.deadline(1),
            "triangle_count": mesh.triangle_count,
            "polygon_regression_ratio": mesh.regression_ratio,
            "rigged_mesh_digest": mesh.digest,
            "vertex_count": len(vertices),
        },
        "animation": {"clip": animation.name, "sample_ms": animation_time_ms,
                      "bone_count": len(skeleton.bones),
                      "collision_capsules": len(mesh.colliders)},
        "cognition": {
            "shot": cinematic.shot, "focus": cinematic.focus_object_id,
            "shot_reasons": list(cinematic.rationale),
            "shot_evidence": list(cinematic.evidence_digests),
            "suggested_action": next_action.action,
            "target": next_action.target,
            "action_reasons": list(next_action.rationale),
            "action_evidence": list(next_action.evidence_digests),
            "authority": "suggestions_only",
        },
        "preemptive_input": prediction,
        "world_variant": ({
            "family": world_variant.family.value,
            "element": world_variant.element, "intensity": world_variant.intensity,
            "source_coordinates": [variant_cell.source_x, variant_cell.source_y],
            "gravity_sign": variant_cell.gravity_sign,
            "energy": variant_cell.world_energy,
            "permeability": variant_cell.permeability,
            "luminance": variant_cell.luminance,
            "celestial_altitude": variant_cell.celestial_altitude,
            "elevation": variant_cell.elevation,
            "temperature": variant_cell.temperature,
            "humidity": variant_cell.humidity,
            "sky_island": variant_cell.sky_island,
        } if variant_cell else None),
        "projection": ({
            "mode": camera.mode.value,
            "camera_xyz": [camera.position.x, camera.position.y, camera.position.z],
            "projected_vertices": len(points),
            "visible_vertices": sum(1 for p in points if p.visible),
            "first_vertex": ([points[0].screen_x, points[0].screen_y]
                             if points else None),
        } if camera else None),
        "weather_physics": ({
            "temperature_c": physical_weather.temperature_c,
            "wind_xyz": [physical_weather.wind.x, physical_weather.wind.y,
                         physical_weather.wind.z],
            "rain_mm_h": physical_weather.precipitation_mm_h,
            "water_depth_m": physical_weather.water_depth_m,
            "snow_depth_m": physical_weather.snow_depth_m,
        } if physical_weather else None),
        "character_physics": ({
            "position": [character_step.state.position.x,
                         character_step.state.position.y,
                         character_step.state.position.z],
            "velocity": [character_step.state.velocity.x,
                         character_step.state.velocity.y,
                         character_step.state.velocity.z],
            "gait": character_step.state.gait,
            "core_temperature_c": character_step.state.core_temperature_c,
            "clothing_wetness": character_step.state.clothing_wetness,
            "hair_wetness": character_step.state.hair_wetness,
            "boot_wetness": character_step.state.boot_wetness,
            "traction": character_step.friction_coefficient,
            "awareness": {
                "cold_stress": character_step.awareness.cold_stress,
                "heat_stress": character_step.awareness.heat_stress,
                "wet_stress": character_step.awareness.wet_stress,
                "slip_risk": character_step.awareness.slip_risk,
                "protective_action": character_step.awareness.protective_action,
            },
            "impacts": [{"surface": i.surface_id, "impulse_ns": i.impulse_ns,
                         "damage": i.damage, "material": i.material}
                        for i in character_step.impacts],
        } if character_step else None),
        "soft_material_motion": [{
            "id": n.node_id, "material": n.material,
            "xyz": [n.position.x, n.position.y, n.position.z],
            "wetness": n.wetness, "temperature_c": n.temperature_c,
        } for n in simulated_soft],
        "environment_response": ({
            "soil_saturation": environment_step.soil_saturation,
            "erosion": environment_step.erosion,
            "foliage_bend": environment_step.foliage_bend,
            "vegetation_health": environment_step.vegetation_health,
            "puddle_depth_m": environment_step.puddle_depth_m,
            "snow_load": environment_step.snow_load,
            "debris_fraction": environment_step.debris_fraction,
        } if environment_step else None),
        "structures": [{
            "id": s.structure_id, "material": s.material,
            "built": s.complete, "construction_progress_days": s.construction_progress_days,
            "age_days": s.age_days, "integrity": s.integrity,
            "weathering": s.surface_weathering,
            "biological_growth": s.biological_growth,
            "water_infiltration": s.water_infiltration,
            "maintenance_debt": s.maintenance_debt,
        } for s in structure_steps],
        "ray_lighting": [{
            "object_id": l.object_id,
            "rgb": list(l.radiance_rgb),
            "shadow_fraction": l.shadow_occlusion,
            "character_occluders": list(l.character_occluders),
            "environment_occluders": list(l.source_occluders),
            "wet_specular": l.wet_specular,
        } for l in light_steps],
        "governance": {
            "neural_model_checkpoint_loaded": False,
            "gameplay_action_executed": False,
            "model_weights_modified": False,
            "runtime_admitted": False,
        },
    }
    digest = sha256(json.dumps(manifest, sort_keys=True,
                               separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return FrontierSceneCandidate(manifest, digest, vertices, moved,
                                  False, mesh.triangles, mesh.colliders)
