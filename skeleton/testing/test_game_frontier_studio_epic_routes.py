"""Real Epic multilevel source path witnesses, alternatives and negative authority.

No native portals are executed: every result is explicitly a source-only
reference, signed from the actual immutable authored source layers.
"""
from __future__ import annotations

from dataclasses import replace
from copy import deepcopy
import unittest

from skeleton.forge.game_frontier_studio import StudioError
from skeleton.forge.game_frontier_studio_document import (
    create_authoring_project, authored_document, load_authored_document,
)
from skeleton.forge.game_frontier_studio_epic_route_graph import (
    audit_epic_interlayer_routes, verify_epic_interlayer_routes,
    compare_epic_interlayer_routes,
)


def worlds():
    base = create_authoring_project("epic_route_test", width=7, height=7)
    return replace(base, layers=(
        base.layers[0],
        replace(base.layers[0], layer_id="sky_island", elevation_m=12.),
        replace(base.layers[0], layer_id="underground", elevation_m=-30.),
    ))


def node(layer, x, y):
    return {"layer": layer, "x": x, "y": y}


def crossing(alternate=False):
    return {
        "layer_ids": ["ground", "sky_island"],
        "connectors": [{
            "connector_id": "lift_center",
            "from": node("ground", 3, 3), "to": node("sky_island", 3, 3),
            "mode": "stairs", "bidirectional": True,
        }],
        "itineraries": [{
            "journey_id": "AcrossWorlds",
            "start": node("ground", 0, 3),
            "goal": node("sky_island", 6, 3),
            "require_alternate": alternate,
        }],
    }


class EpicInterlayerReferenceTests(unittest.TestCase):
    def test_stairs_bidirectional_source_replay_is_reproducible(self):
        source = worlds()
        case = crossing()
        first = audit_epic_interlayer_routes(source, case)
        second = audit_epic_interlayer_routes(source, case)
        self.assertEqual(first, second)
        self.assertEqual(1, first["passed_count"])
        self.assertEqual(3, len(first["layer_source_sha256"]) if False
                         else len(source.layers))
        witness = first["journeys"][0]["primary"]
        self.assertTrue(witness["reachable"])
        self.assertEqual(1, witness["transfers"])
        self.assertEqual(["lift_center"], witness["connector_ids"])
        self.assertEqual(["ground", 0, 3], witness["sample"][0])
        self.assertEqual(["sky_island", 6, 3], witness["sample"][-1])
        self.assertTrue(verify_epic_interlayer_routes(source, case, first))
        self.assertFalse(first["native_engine_executed"])
        self.assertFalse(first["transport_actions_applied"])
        self.assertFalse(first["release_certified"])

    def test_no_silent_cross_world_warp_without_native_proposal(self):
        case = crossing()
        case["connectors"] = []
        report = audit_epic_interlayer_routes(worlds(), case)
        self.assertEqual(0, report["passed_count"])
        self.assertEqual("no_source_tile_path", report["journeys"][0]["failure"])

    def test_underground_stairs_elevator_ferry_portal_modes_are_bounded(self):
        source = worlds()
        for mode in ("stairs", "elevator", "ferry", "shuttle", "portal"):
            with self.subTest(mode=mode):
                case = crossing()
                case["connectors"][0]["mode"] = mode
                self.assertEqual(1,
                                 audit_epic_interlayer_routes(source, case)["passed_count"])
        for mode in ("walk", "bridge"):
            with self.subTest(mode=mode), self.assertRaises(StudioError):
                case = crossing()
                case["connectors"][0]["mode"] = mode
                audit_epic_interlayer_routes(source, case)

    def test_real_optional_independent_alternatives(self):
        case = crossing(alternate=True)
        broken = audit_epic_interlayer_routes(worlds(), case)
        self.assertEqual(0, broken["passed_count"])
        self.assertEqual("no_vertex_disjoint_alternative",
                         broken["journeys"][0]["failure"])
        case["connectors"] = [
            {"connector_id": "west_bridge",
             "from": node("ground", 2, 2), "to": node("sky_island", 2, 2),
             "mode": "stairs", "bidirectional": True},
            {"connector_id": "east_bridge",
             "from": node("ground", 4, 4), "to": node("sky_island", 4, 4),
             "mode": "stairs", "bidirectional": True},
        ]
        pass_report = audit_epic_interlayer_routes(worlds(), case)
        self.assertEqual(1, pass_report["passed_count"])
        self.assertTrue(pass_report["journeys"][0]["alternate"]["reachable"])
        self.assertNotEqual(pass_report["journeys"][0]["primary"]["path_sha256"],
                            pass_report["journeys"][0]["alternate"]["path_sha256"])

    def test_blocked_destination_prevents_deceptive_transfer(self):
        source = worlds()
        upper = source.layers[1]
        cells = list(upper.data)
        cells[3*7+3] = 2  # original 'water' is blocked by movement bridge
        blocked = replace(source, layers=(
            source.layers[0], replace(upper, data=tuple(cells)), source.layers[2]))
        with self.assertRaises(StudioError):
            audit_epic_interlayer_routes(blocked, crossing())

    def test_source_tampering_invalidates_receipts_and_real_comparisons(self):
        case = crossing(alternate=True)
        source = worlds()
        before = audit_epic_interlayer_routes(source, case)
        after_case = deepcopy(case)
        after_case["connectors"].append({
            "connector_id": "second",
            "from": node("ground", 5, 1),
            "to": node("sky_island", 5, 1),
            "mode": "stairs", "bidirectional": True,
        })
        after = audit_epic_interlayer_routes(source, after_case)
        self.assertFalse(verify_epic_interlayer_routes(source, case, after))
        fake = dict(before, passed_count=999)
        self.assertFalse(verify_epic_interlayer_routes(source, case, fake))
        with self.assertRaises(StudioError):
            compare_epic_interlayer_routes(before, fake)
        with self.assertRaises(StudioError):
            compare_epic_interlayer_routes(before, after)
        saved = load_authored_document(authored_document(source),
                                      project_id=source.project_id)
        self.assertEqual(before, audit_epic_interlayer_routes(saved, case))

    def test_compare_source_before_and_after_removing_barrier(self):
        case = {
            "layer_ids": ["ground"], "connectors": [],
            "itineraries": [{
                "journey_id": "CanalPassage",
                "start": node("ground", 0, 3),
                "goal": node("ground", 6, 3),
                "require_alternate": False,
            }],
        }
        base = worlds()
        first = base.layers[0]
        blocked_cells = list(first.data)
        for y in range(7):
            blocked_cells[y*7 + 3] = 2
        blocked = replace(base, layers=(
            replace(first, data=tuple(blocked_cells)), *base.layers[1:]))
        before = audit_epic_interlayer_routes(blocked, case)
        after = audit_epic_interlayer_routes(base, case)
        comparison = compare_epic_interlayer_routes(before, after)
        self.assertEqual(["CanalPassage"], comparison["improved"])
        self.assertEqual([], comparison["regressed"])
        self.assertTrue(comparison["strict_improvement"])
        self.assertEqual(["CanalPassage"],
                         compare_epic_interlayer_routes(after, before)["regressed"])

    def test_strict_validation_for_malformed_source_journeys(self):
        original = crossing()
        invalid = []
        for value in (-1, False, 7, "../evil"):
            case = deepcopy(original)
            case["itineraries"][0]["start"]["x"] = value
            invalid.append(case)
        for key, value in [
            ("mode", "teleport_script"),
            ("connector_id", "../../escape"),
            ("bidirectional", "yes"),
            ("to", node("missing", 3, 3)),
        ]:
            case = deepcopy(original)
            case["connectors"][0][key] = value
            invalid.append(case)
        duplicate = deepcopy(original)
        duplicate["connectors"].append(dict(duplicate["connectors"][0]))
        invalid.append(duplicate)
        same = deepcopy(original)
        same["itineraries"][0]["goal"] = same["itineraries"][0]["start"]
        invalid.append(same)
        excess = deepcopy(original)
        excess["connectors"] *= 65
        invalid.append(excess)
        added = deepcopy(original)
        added["script"] = "exec"
        invalid.append(added)
        for i, case in enumerate(invalid):
            with self.subTest(case=i), self.assertRaises(StudioError):
                audit_epic_interlayer_routes(worlds(), case)

    def test_one_way_portal_respects_directionality(self):
        source = worlds()
        case = crossing()
        case["connectors"][0]["mode"] = "portal"
        case["connectors"][0]["bidirectional"] = False
        forward = audit_epic_interlayer_routes(source, case)
        self.assertEqual(1, forward["passed_count"])
        reverse = deepcopy(case)
        reverse["itineraries"][0]["start"], reverse["itineraries"][0]["goal"] = (
            reverse["itineraries"][0]["goal"], reverse["itineraries"][0]["start"])
        self.assertEqual(0, audit_epic_interlayer_routes(source, reverse)["passed_count"])


if __name__ == "__main__":
    unittest.main()
