"""Cross-check real Godot compass animation observations against authored travel.

The gameplay runtime reports only actual waypoint-driven avatar animation
changes. This independent reviewer replays the already-authorized autoplay
edge IDs over the original immutable ExpeditionWorld geometry, computing the
expected horizontal direction and frame name. Missing, extra, reordered,
cross-project, or forged native observations cannot earn a compass receipt.
"""
from __future__ import annotations

from collections.abc import Mapping
import json
import math
from typing import Any

from skeleton.jeeves.game_frontier_expedition import ExpeditionWorld
from .studio_interaction_contract import digest
from .studio_sprite_direction import FACING

PREFIX = "JEEVES_COMPASS "
MAX_OBSERVATIONS = 4096


class SpriteCompassEvidenceError(ValueError):
    """Real-world route and native sprite-facing events do not agree."""


def _heading(dx: float, dz: float) -> str:
    radians = math.atan2(dx, -dz)
    sectors = radians / (math.pi / 4.0)
    # Godot 4 round() uses half-away-from-zero semantics; unlike Python's
    # nearest-even round. Preserve the engine's exact tie-breaking policy.
    nearest = (
        math.floor(sectors + 0.5) if sectors >= 0
        else math.ceil(sectors - 0.5)
    )
    return FACING[nearest % 8]


def expected_compass_transitions(
    world: ExpeditionWorld, recipe: Mapping[str, Any],
    binding: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Derive observable sprite transitions from real game waypoints."""
    if not isinstance(world, ExpeditionWorld):
        raise SpriteCompassEvidenceError("real original game world required")
    if (not isinstance(recipe, Mapping)
            or recipe.get("world_digest") != world.digest):
        raise SpriteCompassEvidenceError("autoplay route belongs to another original world")
    steps = recipe.get("steps")
    if type(steps) is not list or len(steps) > MAX_OBSERVATIONS:
        raise SpriteCompassEvidenceError("native autoplay route exceeds bounds")
    if not isinstance(binding, Mapping) or not isinstance(
        binding.get("directional_animations"), dict
    ):
        raise SpriteCompassEvidenceError("original player facing source is missing")
    source = dict(binding)
    authority_sha256 = source.pop("receipt_sha256", None)
    if digest(source) != authority_sha256:
        raise SpriteCompassEvidenceError("player compass record is not source-bound")
    names = binding["directional_animations"]
    by_node = world.by_id
    by_edge = world.by_edge
    arrivals: list[dict[str, str]] = []
    position = world.arrival
    for item in steps:
        if type(item) is not dict or set(item) != {"edge_id", "target"}:
            raise SpriteCompassEvidenceError("autoplay step lacks exact edge identity")
        edge = by_edge.get(item["edge_id"])
        if (edge is None or edge.source != position
                or edge.target != item["target"]):
            raise SpriteCompassEvidenceError(
                "autoplay source/target did not follow a real game navigation edge"
            )
        origin, destination = by_node[position], by_node[edge.target]
        dx = destination.x_m - origin.x_m
        dz = destination.y_m - origin.y_m
        position = edge.target
        if dx * dx + dz * dz <= 0.000001:
            continue
        facing = _heading(dx, dz)
        if facing in names:
            animation = names[facing]
            if type(animation) is not str or not animation:
                raise SpriteCompassEvidenceError("original direction has no valid animation")
            arrivals.append({
                "waypoint_id": edge.target,
                "heading": facing,
                "animation": animation,
            })
    return arrivals


def inspect_native_compass_observations(
    raw_log: str, world: ExpeditionWorld,
    recipe: Mapping[str, Any], binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Refuse replay unless every native direction matches real route geometry."""
    if type(raw_log) is not str or len(raw_log.encode("utf-8")) > 4_000_000:
        raise SpriteCompassEvidenceError("native engine log exceeds bounded evidence size")
    expected = expected_compass_transitions(world, recipe, binding)
    observed: list[dict[str, str]] = []
    for line in raw_log.splitlines():
        if not line.startswith(PREFIX):
            continue
        payload = line[len(PREFIX):]
        if len(payload) > 1024 or len(observed) >= MAX_OBSERVATIONS:
            raise SpriteCompassEvidenceError("native compass observations exceed policy")
        try:
            value = json.loads(payload)
        except (TypeError, ValueError) as exc:
            raise SpriteCompassEvidenceError(
                "native Godot compass emitted invalid JSON"
            ) from exc
        if (type(value) is not dict
                or set(value) != {"waypoint_id", "heading", "animation"}
                or any(type(v) is not str or len(v) > 128 for v in value.values())):
            raise SpriteCompassEvidenceError("native sprite event lacks typed identity")
        observed.append(value)
    if observed != expected:
        raise SpriteCompassEvidenceError(
            "real Godot sprite animation changes contradict authored world route"
        )
    body = {
        "schema_version": "skeleton.jeeves.native_compass_replay.v1",
        "world_digest": world.digest,
        "player_source_receipt_sha256": binding["receipt_sha256"],
        "autoplay_route_digest": recipe.get("route_digest"),
        "waypoint_compass_events_verified": len(observed),
        "event_sequence_sha256": digest(observed),
        "native_trace_matches_original_travel": True,
        "sprite_animation_observed": len(observed) > 0,
        "image_pixels_or_screen_independently_observed": False,
    }
    body["receipt_sha256"] = digest(body)
    return body


__all__ = [
    "SpriteCompassEvidenceError", "expected_compass_transitions",
    "inspect_native_compass_observations",
]
