"""Actual source navigation, tamper rejection and regressions (no mocked native pass)."""
from __future__ import annotations

from dataclasses import replace
import unittest

from skeleton.forge.game_frontier_studio import StudioError, MapLayer
from skeleton.forge.game_frontier_studio_document import create_authoring_project
from skeleton.forge.game_frontier_studio_route_assurance import (
    audit_route_playthroughs, verify_route_playthroughs,
    compare_route_playthroughs,
)


def project_with_barrier(openings: tuple[int, ...] = ()):
    project = create_authoring_project("route_assurance", width=7, height=7)
    original = project.layers[0]
    cells = list(original.data)
    for y in range(7):
        if y not in openings:
            cells[y * 7 + 3] = 2  # canonical 'water': non-traversable
    layer = replace(original, data=tuple(cells))
    return replace(project, layers=(layer,))


def scenario(alternate: bool = True, ident: str = "RouteA"):
    return {"scenario_id": ident, "layer": "ground",
            "start": [0, 3], "goal": [6, 3],
            "require_alternate": alternate}


class AuthoredTileRouteReplayTests(unittest.TestCase):
    def test_both_paths_are_reproducible_real_source_witnesses(self):
        project = project_with_barrier((2, 3))
        report = audit_route_playthroughs(project, [scenario()])
        self.assertEqual(1, report["passed_count"])
        row = report["scenarios"][0]
        self.assertTrue(row["primary"]["reachable"])
        self.assertTrue(row["alternate"]["reachable"])
        self.assertTrue(row["passed"])
        self.assertEqual([0, 3], row["primary"]["path_sample"][0])
        self.assertEqual([6, 3], row["primary"]["path_sample"][-1])
        self.assertLessEqual(row["primary"]["steps"], 49)
        self.assertEqual(
            {tuple(row["primary"]["path_sample"][0]),
             tuple(row["primary"]["path_sample"][-1])},
            set(map(tuple, row["primary"]["path_sample"])) &
            set(map(tuple, row["alternate"]["path_sample"])))
        self.assertTrue(verify_route_playthroughs(project, [scenario()], report))
        self.assertEqual(report, audit_route_playthroughs(project, [scenario()]))
        self.assertFalse(report["native_engine_executed"])
        self.assertFalse(report["release_certified"])

    def test_one_bottleneck_is_reachable_but_not_redundant(self):
        project = project_with_barrier((3,))
        report = audit_route_playthroughs(project, [scenario()])
        row = report["scenarios"][0]
        self.assertTrue(row["primary"]["reachable"])
        self.assertFalse(row["alternate"]["reachable"])
        self.assertEqual("no_vertex_disjoint_alternative", row["failure"])
        self.assertEqual(0, report["passed_count"])
        without_redundancy = audit_route_playthroughs(project, [scenario(False)])
        self.assertTrue(without_redundancy["scenarios"][0]["passed"])
        self.assertIsNone(without_redundancy["scenarios"][0]["alternate"])

    def test_water_barrier_is_not_invented_as_walkable(self):
        report = audit_route_playthroughs(project_with_barrier(), [scenario()])
        self.assertFalse(report["scenarios"][0]["primary"]["reachable"])
        self.assertEqual("unreachable_in_authored_tiles",
                         report["scenarios"][0]["failure"])

    def test_source_changes_reject_old_claim_and_tampered_receipt(self):
        first = project_with_barrier((3,))
        second = project_with_barrier((2, 3))
        before = audit_route_playthroughs(first, [scenario()])
        after = audit_route_playthroughs(second, [scenario()])
        self.assertFalse(verify_route_playthroughs(first, [scenario()], after))
        self.assertFalse(verify_route_playthroughs(second, [scenario()], before))
        fake = {**after, "passed_count": 99}
        self.assertFalse(verify_route_playthroughs(second, [scenario()], fake))
        self.assertRaises(StudioError, compare_route_playthroughs, before, fake)
        delta = compare_route_playthroughs(before, after)
        self.assertEqual(["RouteA"], delta["improved"])
        self.assertEqual([], delta["regressed"])
        self.assertTrue(delta["strict_improvement"])
        reverse = compare_route_playthroughs(after, before)
        self.assertEqual(["RouteA"], reverse["regressed"])
        self.assertFalse(reverse["strict_improvement"])
        self.assertFalse(delta["release_certified"])

    def test_mismatched_comparators_and_synthetic_approvals_rejected(self):
        project = project_with_barrier((3,))
        before = audit_route_playthroughs(project, [scenario(False)])
        after = audit_route_playthroughs(project, [scenario()])
        self.assertRaises(StudioError, compare_route_playthroughs, before, after)
        fake = {**before, "native_engine_executed": True}
        self.assertFalse(verify_route_playthroughs(project, [scenario(False)], fake))
        self.assertRaises(StudioError, compare_route_playthroughs, before, fake)

    def test_strict_input_bounds_and_authority(self):
        project = project_with_barrier((3,))
        invalid = (
            [],
            [scenario()] * 101,
            [scenario(), scenario()],
            [{**scenario(), "start": [False, 3]}],
            [{**scenario(), "goal": [7, 3]}],
            [{**scenario(), "start": [0, 3], "goal": [0, 3]}],
            [{**scenario(), "layer": "../../other"}],
            [{**scenario(), "scenario_id": "../escape"}],
            [{**scenario(), "require_alternate": 1}],
            [{**scenario(), "script": "exec"}],
        )
        for i, cases in enumerate(invalid):
            with self.subTest(index=i), self.assertRaises(StudioError):
                audit_route_playthroughs(project, cases)

    def test_one_hundred_scenarios_are_bounded_and_repeatable(self):
        project = project_with_barrier((2, 3))
        queries = [scenario(i % 2 == 0, f"Route{i:03}")
                   for i in range(100)]
        result = audit_route_playthroughs(project, queries)
        self.assertEqual(100, result["scenario_count"])
        self.assertEqual(100, result["passed_count"])
        self.assertEqual(100, len(result["scenarios"]))
        self.assertTrue(verify_route_playthroughs(project, queries, result))
        self.assertEqual("Route099", result["scenarios"][-1]["scenario_id"])

    def test_no_overwrite_and_roundtrip_source_semantics(self):
        project = project_with_barrier((2, 3))
        from skeleton.forge.game_frontier_studio_document import (
            authored_document, load_authored_document,
        )
        restored = load_authored_document(authored_document(project),
                                          project_id=project.project_id)
        self.assertEqual(audit_route_playthroughs(project, [scenario()]),
                         audit_route_playthroughs(restored, [scenario()]))


if __name__ == "__main__":
    unittest.main()
