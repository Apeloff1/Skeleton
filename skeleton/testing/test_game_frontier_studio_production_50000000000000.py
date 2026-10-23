"""50T composable Epic source, 45T transformations, 9B virtual manuals.

Tests verify actual map/project edits, bounded multi-layer functionality,
observed gameplay proposals, source topology/quest continuity and SHA exports.
They do not certify that 50T games were individually built or playtested.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.forge.game_frontier_studio import (
    StudioError, StudioProject, compile_studio_expedition,
    compile_studio_native_quest_graph,
)
from skeleton.forge.game_frontier_rpg_events import evaluate_environment_events
from skeleton.forge.game_frontier_studio_authoring import (
    AUTHORING_ACTIONS, execute_authoring, project_digest,
    authored_summary, apply_authoring_batch,
)
from skeleton.forge.game_frontier_studio_saga_production import SAGA_ACTIONS
from skeleton.forge.game_frontier_studio_epic_variations import (
    EPIC_ACTIONS, EPICS, EVENTS, describe_epic, parent_action, search_epics,
    _pattern,
)
from skeleton.forge.game_frontier_studio_epic_handbooks import (
    BOOK_COUNT, EPIC_BOOK_PATHS, identity, number, list_books,
    receipt, rank_variants, grade,
)
from skeleton.forge.game_frontier_studio_document import (
    authored_document, load_authored_document,
)
from skeleton.testing.test_game_frontier_studio_production_5000 import (
    original_project, arguments,
)


class FiftyTrillionEpicVariations(unittest.TestCase):
    def test_exact_counts_and_every_prior_index(self):
        self.assertEqual(45_000_000_000_000, len(EPIC_ACTIONS))
        self.assertEqual(50_000_000_000_000, len(AUTHORING_ACTIONS))
        self.assertEqual(SAGA_ACTIONS[0], AUTHORING_ACTIONS[500_000_000_000])
        self.assertEqual(SAGA_ACTIONS[-1],
                         AUTHORING_ACTIONS[5_000_000_000_000-1])
        self.assertEqual(EPIC_ACTIONS[0], AUTHORING_ACTIONS[5_000_000_000_000])
        self.assertEqual(EPIC_ACTIONS[-1], AUTHORING_ACTIONS[-1])
        self.assertNotIn("epic_unregistered____________cosmic_finale",
                         EPIC_ACTIONS)

    def test_exact_epic_rank_unrank_across_trillion_boundaries(self):
        for pos in (0, 1, 9, 10, 99, 100, 4_500_000_000_000,
                    23_456_789_987_654, 44_999_999_999_999):
            action = EPIC_ACTIONS[pos]
            parent, axis = parent_action(action)
            self.assertEqual(parent, SAGA_ACTIONS[pos//10])
            self.assertEqual(EPICS[axis], EPICS[pos%10])
            self.assertEqual(action, describe_epic(action)["operation"])
            self.assertTrue(action in AUTHORING_ACTIONS)
        with self.assertRaises(IndexError):
            _ = EPIC_ACTIONS[45_000_000_000_000]
        for offset in (0, 7, 8_765_432_100,
                       45_000_000_000_000 - 32):
            page = search_epics(offset=offset, limit=32)
            self.assertEqual(
                [row["operation"] for row in page["items"]],
                list(EPIC_ACTIONS[offset:offset+32]),
            )
        result = search_epics(domain="realm", system_layer="stealth",
                              director="audio_cues", finish="alternate_endings",
                              worldline="sky_navigation", phase="storm_shelters",
                              campaign="siege_campaigns", chronicle="emergency_response",
                              epoch="spring_thaw", saga="skyward_migration",
                              epic="continental_odyssey", limit=10)
        self.assertEqual(450, result["matched"])
        self.assertEqual(10, len(result["items"]))
        self.assertTrue(all(row["epic"] == "continental_odyssey"
                            for row in result["items"]))
        with self.assertRaises(StudioError):
            search_epics(epic="../../unsafe")
        with self.assertRaises(StudioError):
            search_epics(limit=65)

    def test_every_exact_id_fits_authenticated_512_character_route(self):
        from skeleton.forge.game_frontier_studio_production_recipes import RECIPE_ACTIONS
        from skeleton.forge.game_frontier_studio_system_expansions import GAMEPLAY_LAYERS
        from skeleton.forge.game_frontier_studio_directed_production import DIRECTORS
        from skeleton.forge.game_frontier_studio_final_production import FINISHES
        from skeleton.forge.game_frontier_studio_worldline_production import WORLDLINES
        from skeleton.forge.game_frontier_studio_phase_production import PHASES
        from skeleton.forge.game_frontier_studio_campaign_production import CAMPAIGNS
        from skeleton.forge.game_frontier_studio_chronicle_production import CHRONICLES
        from skeleton.forge.game_frontier_studio_epoch_production import EPOCHS
        max_length = max(map(len, RECIPE_ACTIONS)) - len("produce_") + len("epic_")
        for width, axis in enumerate((GAMEPLAY_LAYERS, DIRECTORS, FINISHES,
                                      WORLDLINES, PHASES, CAMPAIGNS, CHRONICLES,
                                      EPOCHS, ("homecoming", "faction_concord",
                                               "buried_history", "skyward_migration",
                                               "oceanic_reckoning", "citadel_reconstruction",
                                               "wildlife_pact", "betrayal_aftermath",
                                               "starfall_observatory", "branching_epilogue"),
                                      EPICS)):
            max_length += (3+width) + max(map(len, axis))
        self.assertLessEqual(max_length, 512)
        self.assertLessEqual(len(EPIC_ACTIONS[0]), max_length)
        self.assertLessEqual(len(EPIC_ACTIONS[-1]), max_length)

    def test_ten_unique_topologies_are_real_repeatable_source_edits(self):
        original = original_project()
        old_sha = project_digest(original)
        outcomes = set()
        for axis, name in enumerate(EPICS):
            operation = EPIC_ACTIONS[axis]
            with self.subTest(epic=name):
                payload = arguments(operation)
                actual = execute_authoring(original, operation, payload)
                same = execute_authoring(original, operation, payload)
                self.assertIsInstance(actual, StudioProject)
                self.assertEqual(project_digest(actual), project_digest(same))
                self.assertNotEqual(old_sha, project_digest(actual))
                self.assertEqual(original.placements,
                                 actual.placements[:len(original.placements)])
                self.assertEqual(original.native_quests,
                                 actual.native_quests[:len(original.native_quests)])
                self.assertEqual(2, len(actual.environmental_pages[-1].conditions))
                self.assertEqual({EVENTS[axis][0], EVENTS[axis][3]},
                                 {c.signal for c in actual.environmental_pages[-1].conditions})
                outcomes.add(project_digest(actual))
        self.assertEqual(10, len(outcomes))
        self.assertEqual(old_sha, project_digest(original))

    def test_eight_explicit_layers_share_edit_and_rollback_invalid_selection(self):
        original = original_project()
        layer = original.layers[0]
        clones = tuple(replace(layer, layer_id="epic_support_"+str(i))
                       for i in range(7))
        initial = replace(original, layers=(*original.layers, *clones))
        name = EPIC_ACTIONS[4]
        args = {**arguments(name),
                "epic_layers": [l.layer_id for l in clones]}
        candidate = execute_authoring(initial, name, args)
        self.assertEqual(8, len(candidate.layers))
        for old, new in zip(initial.layers, candidate.layers):
            self.assertNotEqual(old.data, new.data)
        self.assertEqual(8, len(initial.layers))
        self.assertEqual(layer.data, initial.layers[0].data)
        with self.assertRaises(StudioError):
            execute_authoring(initial, name, {
                **args, "epic_layers": ["missing_world"],
            })
        with self.assertRaises(StudioError):
            execute_authoring(initial, name, {
                **args, "epic_layers": [layer.layer_id],
            })
        with self.assertRaises(StudioError):
            execute_authoring(initial, name, {
                **args, "epic_layers": ["epic_support_0"] * 2,
            })

    def test_sibling_layer_requires_the_same_tile_materials(self):
        base = original_project()
        primary = base.layers[0]
        changed = replace(primary, layer_id="misleading_palette",
                          palette=tuple(reversed(primary.palette)))
        initial = replace(base, layers=(primary, changed))
        operation = EPIC_ACTIONS[0]
        with self.assertRaises(StudioError):
            execute_authoring(initial, operation, {
                **arguments(operation), "epic_layers": ["misleading_palette"],
            })

    def test_optional_quest_branch_uses_declared_entry_and_never_cycles(self):
        from skeleton.forge.game_frontier_studio import StudioQuest, StudioQuestStage
        from skeleton.forge.game_frontier_studio_epic_variations import _branch_new_quests
        base = original_project()
        # A valid single-stage story must remain solvable after adding an
        # optional Epic ending, with no circular root->branch->root edge.
        solo = StudioQuest("single_scene", "Single scene", "start",
                           (StudioQuestStage("start", "Arrive"),))
        alternate = StudioQuest(
            "reordered_arc", "Chapter", "begin",
            (StudioQuestStage("old_end", "Reach the end"),
             StudioQuestStage("begin", "Choose a path", ("old_end",))),
        )
        input_project = replace(base, native_quests=(solo, alternate))
        output = _branch_new_quests(input_project, 0, 0, EPIC_ACTIONS[0])
        self.assertEqual(2, len(output.native_quests))
        first = output.native_quests[0]
        self.assertTrue(first.stages[0].next_stage_ids)
        self.assertFalse(first.stages[-1].next_stage_ids)
        second = output.native_quests[1]
        root = next(stage for stage in second.stages
                    if stage.stage_id == second.first_stage_id)
        self.assertEqual("old_end", root.next_stage_ids[0])
        self.assertTrue(any("_epic_" in edge for edge in root.next_stage_ids))
        self.assertTrue(compile_studio_native_quest_graph(output)["quests"])
        self.assertEqual(input_project.native_quests[0], solo)

    def test_all_epic_patterns_keep_route_spine_and_differ(self):
        grids = set()
        for mode in range(10):
            cells = tuple(_pattern(mode, x, y, 32, 32, 71, 1)
                          for y in range(32) for x in range(32))
            self.assertTrue(all(_pattern(mode, x, 15, 32, 32, 71, 1)[0]
                                for x in range(32)))
            self.assertTrue(all(_pattern(mode, 15, y, 32, 32, 71, 1)[0]
                                for y in range(32)))
            grids.add(cells)
        self.assertEqual(10, len(grids))

    def test_real_observed_epic_event_and_native_review_only(self):
        base = original_project()
        action = EPIC_ACTIONS[0]
        candidate = execute_authoring(base, action, arguments(action))
        page = candidate.environmental_pages[-1]
        accepted = evaluate_environment_events(
            (page,), current={"barometric_altitude_m": 201., "quest_progress": .7},
            now_ms=40_000,
        )
        rejected = evaluate_environment_events(
            (page,), current={"barometric_altitude_m": 4., "quest_progress": 0.},
            now_ms=40_000,
        )
        self.assertEqual(1, len(accepted.accepted))
        self.assertEqual(0, len(rejected.accepted))
        self.assertTrue(accepted.required_runtime_approvals)

    def test_new_quest_paths_preserve_existing_canon(self):
        base = original_project()
        saga_index = 3 * 450_000_000_000 + 9
        action = EPIC_ACTIONS[saga_index * 10 + 9]
        result = execute_authoring(base, action, arguments(action))
        self.assertEqual(base.native_quests,
                         result.native_quests[:len(base.native_quests)])
        self.assertGreater(len(result.native_quests), len(base.native_quests))
        self.assertTrue(compile_studio_native_quest_graph(result)["quests"])
        final = result.native_quests[-1]
        self.assertTrue(any("_epic_" in stage.stage_id for stage in final.stages))

    def test_batch_receipts_rollback_and_real_godot_files(self):
        from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile
        base = original_project()
        action = EPIC_ACTIONS[5]
        batch = apply_authoring_batch(base, [
            {"action": action, "parameters": arguments(action)}
        ])
        self.assertTrue(batch["receipt"]["actually_changed"])
        self.assertEqual(50_000_000_000_000,
                         authored_summary(batch["project"])["catalog_total"])
        self.assertEqual(49_999_999_999_500,
                         authored_summary(batch["project"])["recipe_catalog_count"])
        self.assertEqual(45_000_000_000_000,
                         authored_summary(batch["project"])["epic_recipe_count"])
        restored = load_authored_document(
            authored_document(batch["project"]), project_id=base.project_id,
        )
        self.assertEqual(project_digest(restored),
                         project_digest(batch["project"]))
        with self.assertRaises(StudioError):
            apply_authoring_batch(base, [
                {"action": action, "parameters": arguments(action)},
                {"action": action, "parameters": {
                    **arguments(action), "epic_layers": ["../unsafe"],
                }},
            ])
        self.assertEqual(project_digest(base), project_digest(original_project()))
        project = compile_studio_expedition(
            batch["project"],
            ArchipelagoProfile(seed=53, islands=4, caverns=0,
                               include_portals=False, include_underwater=False),
            include_godot=True, playtest_routes=2,
        )
        self.assertIn("game/frontier/studio_terrain.gd",
                      project["godot_project_files"])
        self.assertGreater(project["travel_edges"], 0)


class TenBillionEpicManuals(unittest.TestCase):
    def test_nine_billion_reversible_source_manuscripts(self):
        self.assertEqual(9_000_000_000, BOOK_COUNT)
        self.assertEqual(9_000_000_000, len(EPIC_BOOK_PATHS))
        for pos in (0, 1, 9, 10, 17, 900, 90_000,
                    888_888_888, 8_999_999_999):
            self.assertEqual(pos, number(*identity(pos)))
            self.assertTrue(EPIC_BOOK_PATHS[pos].endswith(".md"))
        with self.assertRaises(StudioError):
            identity(9_000_000_000)

    def test_real_render_sha_and_objective_source_score(self):
        data = receipt(*identity(0))
        self.assertEqual(50, data["markdown"].count(" | epic_"))
        self.assertEqual(10, data["markdown"].count("Executable registered Epic source: "))
        self.assertEqual(100, data["quality_score"])
        self.assertGreater(data["words"], 2500)
        self.assertEqual(sha256(data["markdown"].encode("utf8")).hexdigest(),
                         data["content_sha256"])
        broken = data["markdown"].replace("## Fifty grounded source archetypes",
                                         "## Missing source examples")
        # Source command coverage remains physically present; the grade
        # measures exact evidence, never subjective aesthetic excellence.
        self.assertEqual(data["quality_score"], grade(broken, data)["quality_score"])

    def test_real_ten_way_rankings_and_bounded_export(self):
        context = identity(0)[:-1]
        for sort in ("quality", "length"):
            ranking = rank_variants(*context, sort=sort)
            self.assertEqual(10, ranking["compared"])
            self.assertEqual(10, len(ranking["items"]))
            if sort == "quality":
                key = lambda d: (-d["quality_score"], -d["words"], d["epic"])
            else:
                key = lambda d: (-d["words"], -d["quality_score"], d["epic"])
            self.assertEqual(ranking["items"], sorted(ranking["items"], key=key))
        page = list_books(domain="realm", epic="cosmic_finale", limit=3)
        self.assertEqual(3, len(page["items"]))
        self.assertTrue(all(x["epic"] == "cosmic_finale" for x in page["items"]))
        with self.assertRaises(StudioError):
            list_books(limit=65)
        from scripts.export_game_studio_epic_handbooks import export
        with TemporaryDirectory() as temp:
            path = Path(temp)
            result = export(path, offset=0, limit=2)
            self.assertEqual(2, result["exported"])
            manifest = json.loads(Path(result["manifest"]).read_text())
            self.assertEqual(2, len(manifest["receipts"]))
            for entry in manifest["receipts"]:
                actual = sha256((path / entry["path"]).read_bytes()).hexdigest()
                self.assertEqual(entry["content_sha256"], actual)
            with self.assertRaises(FileExistsError):
                export(path, offset=0, limit=2)


if __name__ == "__main__":
    unittest.main()
