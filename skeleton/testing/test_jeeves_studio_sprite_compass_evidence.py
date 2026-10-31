"""Independent actual-route tests for eight-way Godot compass observations."""
from __future__ import annotations

import json
import unittest

from skeleton.jeeves.game_frontier_expedition import (
    ExpeditionWorld, TravelEdge, Waypoint,
)
from skeleton.jeeves.ai.studio_interaction_contract import digest
from skeleton.jeeves.ai.studio_sprite_compass_evidence import (
    SpriteCompassEvidenceError, expected_compass_transitions,
    inspect_native_compass_observations,
)


def original_world() -> ExpeditionWorld:
    nodes = (
        Waypoint("start", 0.0, 0.0, 0.0, "ground"),
        Waypoint("northern", 0.0, -10.0, 0.0, "ground"),
        Waypoint("eastern", 10.0, -10.0, 0.0, "ground"),
        Waypoint("southern", 10.0, 0.0, 0.0, "ground"),
    )
    edges = (
        TravelEdge("north-edge", "start", "northern", "walk", 10.0, 10.0, 2),
        TravelEdge("east-edge", "northern", "eastern", "walk", 10.0, 10.0, 2),
        TravelEdge("south-edge", "eastern", "southern", "walk", 10.0, 10.0, 2),
    )
    return ExpeditionWorld(
        project_id="original-hero", source_digest="a" * 64,
        waypoints=nodes, edges=edges,
        arrival="start", destinations=("southern",),
    )


def authored_binding():
    body = {
        "asset_id": "hero-idle",
        "directional_animations": {
            "north": "idle", "east": "walk", "south": "glide",
        },
    }
    body["receipt_sha256"] = digest(body)
    return body


def real_route(world):
    return {
        "world_digest": world.digest, "route_digest": "b" * 64,
        "steps": [
            {"edge_id": "north-edge", "target": "northern"},
            {"edge_id": "east-edge", "target": "eastern"},
            {"edge_id": "south-edge", "target": "southern"},
        ],
    }


def native_compass_log(events):
    return "".join(
        "JEEVES_COMPASS " + json.dumps(item, sort_keys=True) + "\n"
        for item in events
    )


class TestJeevesCompassRouteEvidence(unittest.TestCase):
    def setUp(self):
        self.world = original_world()
        self.binding = authored_binding()
        self.recipe = real_route(self.world)
        self.expected = [
            {"waypoint_id": "northern", "heading": "north", "animation": "idle"},
            {"waypoint_id": "eastern", "heading": "east", "animation": "walk"},
            {"waypoint_id": "southern", "heading": "south", "animation": "glide"},
        ]

    def test_real_route_uses_xz_plane_not_vertical_height(self):
        self.assertEqual(expected_compass_transitions(
            self.world, self.recipe, self.binding,
        ), self.expected)

    def test_complete_native_sprite_events_attest_matching_route(self):
        report = inspect_native_compass_observations(
            native_compass_log(self.expected), self.world,
            self.recipe, self.binding,
        )
        self.assertEqual(report["waypoint_compass_events_verified"], 3)
        self.assertTrue(report["native_trace_matches_original_travel"])
        self.assertTrue(report["sprite_animation_observed"])
        self.assertFalse(report["image_pixels_or_screen_independently_observed"])

    def test_absent_native_game_sprite_events_cannot_claim_transitions(self):
        with self.assertRaises(SpriteCompassEvidenceError):
            inspect_native_compass_observations(
                "", self.world, self.recipe, self.binding,
            )

    def test_wrong_heading_fails_even_with_same_waypoint(self):
        changed = list(self.expected)
        changed[1] = {**changed[1], "heading": "north"}
        with self.assertRaises(SpriteCompassEvidenceError):
            inspect_native_compass_observations(
                native_compass_log(changed), self.world,
                self.recipe, self.binding,
            )

    def test_wrong_animation_fails_even_if_heading_is_correct(self):
        changed = list(self.expected)
        changed[2] = {**changed[2], "animation": "walk"}
        with self.assertRaises(SpriteCompassEvidenceError):
            inspect_native_compass_observations(
                native_compass_log(changed), self.world,
                self.recipe, self.binding,
            )

    def test_duplicate_native_compass_events_do_not_count_as_extra_progress(self):
        with self.assertRaises(SpriteCompassEvidenceError):
            inspect_native_compass_observations(
                native_compass_log(self.expected + self.expected[:1]),
                self.world, self.recipe, self.binding,
            )

    def test_reordered_native_steps_cannot_fake_route(self):
        changed = list(reversed(self.expected))
        with self.assertRaises(SpriteCompassEvidenceError):
            inspect_native_compass_observations(
                native_compass_log(changed), self.world,
                self.recipe, self.binding,
            )

    def test_missing_selected_direction_does_not_fabricate_frame(self):
        reduced = dict(self.binding)
        reduced["directional_animations"] = {"east": "walk"}
        reduced["receipt_sha256"] = digest({
            "asset_id": "hero-idle", "directional_animations": {"east": "walk"},
        })
        self.assertEqual(expected_compass_transitions(
            self.world, self.recipe, reduced,
        ), [self.expected[1]])
        report = inspect_native_compass_observations(
            native_compass_log([self.expected[1]]),
            self.world, self.recipe, reduced,
        )
        self.assertEqual(report["waypoint_compass_events_verified"], 1)

    def test_unconfigured_compass_never_claims_native_observation(self):
        reduced = dict(self.binding)
        reduced["directional_animations"] = {}
        reduced["receipt_sha256"] = digest({
            "asset_id": "hero-idle", "directional_animations": {},
        })
        report = inspect_native_compass_observations(
            "", self.world, self.recipe, reduced,
        )
        self.assertEqual(report["waypoint_compass_events_verified"], 0)
        self.assertFalse(report["sprite_animation_observed"])

    def test_forged_extra_waypoint_is_rejected(self):
        changed = [*self.expected, {
            "waypoint_id": "unvisited", "heading": "west", "animation": "walk",
        }]
        with self.assertRaises(SpriteCompassEvidenceError):
            inspect_native_compass_observations(
                native_compass_log(changed), self.world,
                self.recipe, self.binding,
            )

    def test_foreign_route_world_sha_is_rejected(self):
        recipe = {**self.recipe, "world_digest": "f" * 64}
        with self.assertRaises(SpriteCompassEvidenceError):
            expected_compass_transitions(self.world, recipe, self.binding)

    def test_reverse_or_missing_source_route_is_rejected(self):
        recipe = dict(self.recipe)
        recipe["steps"] = [self.recipe["steps"][1]]
        with self.assertRaises(SpriteCompassEvidenceError):
            expected_compass_transitions(self.world, recipe, self.binding)

    def test_binding_source_change_is_rejected(self):
        forged = dict(self.binding)
        forged["directional_animations"] = {"north": "missing"}
        with self.assertRaises(SpriteCompassEvidenceError):
            expected_compass_transitions(self.world, self.recipe, forged)

    def test_malformed_native_json_is_rejected(self):
        with self.assertRaises(SpriteCompassEvidenceError):
            inspect_native_compass_observations(
                'JEEVES_COMPASS {"heading":', self.world,
                self.recipe, self.binding,
            )

    def test_unbounded_engine_observation_is_rejected(self):
        with self.assertRaises(SpriteCompassEvidenceError):
            inspect_native_compass_observations(
                "JEEVES_COMPASS " + "X" * 2000,
                self.world, self.recipe, self.binding,
            )


if __name__ == "__main__":
    unittest.main()
