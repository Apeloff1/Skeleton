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
    pose_skinned_mesh, reason_about_world, skeleton_to_polygon,
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
        "wind": [{"altitude_m": layer.altitude_m,
                  "east_mps": layer.base.east_mps, "north_mps": layer.base.north_mps,
                  "turbulence_mps": layer.turbulence_mps}
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
