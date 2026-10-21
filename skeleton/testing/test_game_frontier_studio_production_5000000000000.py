"""5T composable Saga edits and 1B addressable manuals: functional regressions.

Measures actual deterministic source mutation, observed events, host transaction
shape, canonical story preservation, native Godot source and exact file receipts.
Does NOT attest standalone engine execution or independently finished titles.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.forge.game_frontier_rpg_events import evaluate_environment_events
from skeleton.forge.game_frontier_studio import (
    StudioError, StudioProject, compile_studio_expedition,
    compile_studio_native_quest_graph,
)
from skeleton.forge.game_frontier_studio_authoring import (
    AUTHORING_ACTIONS, execute_authoring, project_digest,
    authored_summary, apply_authoring_batch,
)
from skeleton.forge.game_frontier_studio_epoch_production import EPOCH_ACTIONS
from skeleton.forge.game_frontier_studio_saga_production import (
    SAGA_ACTIONS, SAGAS, SIGNALS, parent_action, describe_saga, search_sagas,
)
from skeleton.forge.game_frontier_studio_saga_handbooks import (
    BOOK_COUNT, SAGA_BOOK_PATHS, identity, number,
    list_books, receipt, rank_variants, grade,
)
from skeleton.forge.game_frontier_studio_document import (
    authored_document, load_authored_document,
)
from skeleton.testing.test_game_frontier_studio_production_5000 import (
    original_project, arguments,
)


class FiveTrillionSagaProduction(unittest.TestCase):
    def test_catalog_boundaries_and_original_indices_remain_stable(self):
        self.assertEqual(4_500_000_000_000, len(SAGA_ACTIONS))
        self.assertEqual(5_000_000_000_000, len(AUTHORING_ACTIONS))
        self.assertEqual(EPOCH_ACTIONS[0], AUTHORING_ACTIONS[50_000_000_000])
        self.assertEqual(EPOCH_ACTIONS[-1],
                         AUTHORING_ACTIONS[500_000_000_000 - 1])
        self.assertEqual(SAGA_ACTIONS[0], AUTHORING_ACTIONS[500_000_000_000])
        self.assertEqual(SAGA_ACTIONS[-1], AUTHORING_ACTIONS[-1])
        self.assertNotIn("saga_exec_untrusted___________homecoming",
                         AUTHORING_ACTIONS)
        with self.assertRaises(IndexError):
            _ = SAGA_ACTIONS[4_500_000_000_000]

    def test_saga_action_names_fit_the_actual_edit_transport(self):
        from skeleton.forge.game_frontier_studio_production_recipes import RECIPE_ACTIONS
        from skeleton.forge.game_frontier_studio_system_expansions import GAMEPLAY_LAYERS
        from skeleton.forge.game_frontier_studio_directed_production import DIRECTORS
        from skeleton.forge.game_frontier_studio_final_production import FINISHES
        from skeleton.forge.game_frontier_studio_worldline_production import WORLDLINES
        from skeleton.forge.game_frontier_studio_phase_production import PHASES
        from skeleton.forge.game_frontier_studio_campaign_production import CAMPAIGNS
        from skeleton.forge.game_frontier_studio_chronicle_production import CHRONICLES
        from skeleton.forge.game_frontier_studio_epoch_production import EPOCHS

        axes = (GAMEPLAY_LAYERS, DIRECTORS, FINISHES, WORLDLINES, PHASES,
                CAMPAIGNS, CHRONICLES, EPOCHS, SAGAS)
        maximum = (max(map(len, RECIPE_ACTIONS))
                   - len("produce_") + len("saga_")
                   + sum(3 + axis + max(map(len, values))
                         for axis, values in enumerate(axes)))
        # A mathematical upper bound for *all* 4.5T unique exact names:
        # no materialized catalogue traversal, no sample-only false assurance.
        self.assertLessEqual(maximum, 512)
        self.assertLessEqual(len(SAGA_ACTIONS[0]), maximum)
        self.assertLessEqual(len(SAGA_ACTIONS[-1]), maximum)

    def test_exact_rank_unrank_search_and_invalid_ids(self):
        for index in (0, 1, 9, 10, 99, 100, 999_999,
                      450_000_000_000, 4_499_999_999_999):
            name = SAGA_ACTIONS[index]
            parent, axis = parent_action(name)
            self.assertEqual(EPOCH_ACTIONS[index // 10], parent)
            self.assertEqual(SAGAS[index % 10], SAGAS[axis])
            self.assertEqual(name, describe_saga(name)["operation"])
        for offset in (0, 8, 123, 77_777_777_777,
                       4_500_000_000_000 - 32):
            page = search_sagas(offset=offset, limit=32)
            self.assertEqual(
                [item["operation"] for item in page["items"]],
                list(SAGA_ACTIONS[offset:offset+32]),
            )
        filtered = search_sagas(
            domain="realm", system_layer="stealth",
            director="audio_cues", finish="alternate_endings",
            worldline="sky_navigation", phase="storm_shelters",
            campaign="siege_campaigns", chronicle="emergency_response",
            epoch="spring_thaw", saga="skyward_migration",
            limit=24,
        )
        self.assertEqual(450, filtered["matched"])
        self.assertEqual(24, len(filtered["items"]))
        self.assertTrue(all(item["saga"] == "skyward_migration"
                            for item in filtered["items"]))
        with self.assertRaises(StudioError):
            search_sagas(saga="../../shell")
        with self.assertRaises(StudioError):
            search_sagas(limit=65)

    def test_ten_original_saga_motions_mutate_actual_source_without_prior_canon(self):
        base = original_project()
        initial_digest = project_digest(base)
        digests = set()
        for axis in range(10):
            operation = SAGA_ACTIONS[axis]
            with self.subTest(saga=SAGAS[axis]):
                actual = execute_authoring(base, operation, arguments(operation))
                again = execute_authoring(base, operation, arguments(operation))
                self.assertIsInstance(actual, StudioProject)
                self.assertNotEqual(initial_digest, project_digest(actual))
                self.assertEqual(project_digest(actual), project_digest(again))
                self.assertEqual(base.placements,
                                 actual.placements[:len(base.placements)])
                self.assertEqual(base.native_quests,
                                 actual.native_quests[:len(base.native_quests)])
                self.assertGreater(len(actual.environmental_pages),
                                   len(base.environmental_pages))
                page = actual.environmental_pages[-1]
                self.assertEqual(2, len(page.conditions))
                self.assertEqual(
                    {SIGNALS[axis][0], SIGNALS[axis][3]},
                    {condition.signal for condition in page.conditions},
                )
                digests.add(project_digest(actual))
        self.assertEqual(10, len(digests))
        self.assertEqual(initial_digest, project_digest(base))

    def test_physically_observed_saga_event_does_not_skip_native_authority(self):
        source = original_project()
        operation = SAGA_ACTIONS[0]
        edited = execute_authoring(source, operation, arguments(operation))
        page = edited.environmental_pages[-1]
        triggered = evaluate_environment_events(
            (page,), current={"quest_progress": .7, "npc_reputation": 20.},
            now_ms=40_000,
        )
        blocked = evaluate_environment_events(
            (page,), current={"quest_progress": 0., "npc_reputation": -10.},
            now_ms=40_000,
        )
        self.assertEqual(1, len(triggered.accepted))
        self.assertEqual(0, len(blocked.accepted))
        self.assertTrue(triggered.required_runtime_approvals)

    def test_new_cast_and_quest_branches_only(self):
        base = original_project()
        cast_action = SAGA_ACTIONS[2 * 450_000_000_000 + 4]
        populated = execute_authoring(base, cast_action, arguments(cast_action))
        self.assertGreater(len(populated.placements), len(base.placements))
        self.assertEqual(base.placements,
                         populated.placements[:len(base.placements)])
        quest_action = SAGA_ACTIONS[3 * 450_000_000_000 + 9]
        scripted = execute_authoring(base, quest_action, arguments(quest_action))
        self.assertGreater(len(scripted.native_quests), len(base.native_quests))
        self.assertEqual(base.native_quests,
                         scripted.native_quests[:len(base.native_quests)])
        self.assertTrue(compile_studio_native_quest_graph(scripted)["quests"])

    def test_transaction_rollback_and_reopened_project(self):
        base = original_project()
        name = SAGA_ACTIONS[0]
        result = apply_authoring_batch(base, [
            {"action": name, "parameters": arguments(name)}
        ])
        self.assertTrue(result["receipt"]["actually_changed"])
        self.assertEqual(5_000_000_000_000,
                         authored_summary(result["project"])["catalog_total"])
        self.assertEqual(4_500_000_000_000,
                         authored_summary(result["project"])["saga_recipe_count"])
        restored = load_authored_document(
            authored_document(result["project"]), project_id=base.project_id,
        )
        self.assertEqual(project_digest(restored),
                         project_digest(result["project"]))
        with self.assertRaises(StudioError):
            apply_authoring_batch(base, [
                {"action": name, "parameters": arguments(name)},
                {"action": name, "parameters": {
                    **arguments(name), "instance_id": "../../escape",
                }},
            ])
        self.assertEqual(project_digest(base), project_digest(original_project()))

    def test_real_godot_export_from_edited_saga(self):
        from skeleton.jeeves.game_frontier_expedition_generation import ArchipelagoProfile
        original = original_project()
        operation = SAGA_ACTIONS[5 * 450_000_000_000 + 5]
        edited = execute_authoring(original, operation, arguments(operation))
        result = compile_studio_expedition(
            edited,
            ArchipelagoProfile(seed=53, islands=4, caverns=0,
                               include_portals=False, include_underwater=False),
            include_godot=True, playtest_routes=2,
        )
        self.assertIn("game/frontier/studio_terrain.gd",
                      result["godot_project_files"])
        self.assertIn("game/frontier/studio_terrain.json",
                      result["godot_project_files"])
        self.assertGreater(result["travel_edges"], 0)


class OneBillionIndexedSagaManuals(unittest.TestCase):
    def test_exact_book_indices_are_stable_and_reversible(self):
        self.assertEqual(900_000_000, BOOK_COUNT)
        self.assertEqual(900_000_000, len(SAGA_BOOK_PATHS))
        for index in (0, 1, 9, 10, 300, 90_000, 899_999_999):
            parts = identity(index)
            self.assertEqual(index, number(*parts))
            self.assertTrue(SAGA_BOOK_PATHS[index].endswith(".md"))
        with self.assertRaises(StudioError):
            identity(900_000_000)

    def test_every_manual_sources_registered_operations_and_objective_grade(self):
        sample = receipt(*identity(0))
        self.assertEqual(50, sample["markdown"].count(" | saga_"))
        self.assertEqual(10,
                         sample["markdown"].count("Verified registered saga edit: "))
        self.assertEqual(100, sample["quality_score"])
        self.assertGreater(sample["words"], 1000)
        self.assertEqual(sha256(sample["markdown"].encode("utf8")).hexdigest(),
                         sample["content_sha256"])
        damaged = sample["markdown"].replace("## Fifty distinct registered source archetypes",
                                              "## Missing archetypes")
        self.assertLess(grade(damaged, sample)["quality_score"],
                        sample["quality_score"])

    def test_rank_ten_actually_rendered_variants_by_quality_and_length(self):
        parts = identity(0)
        quality = rank_variants(*parts[:-1], sort="quality")
        length = rank_variants(*parts[:-1], sort="length")
        self.assertEqual(10, quality["compared"])
        self.assertEqual(10, length["compared"])
        self.assertEqual(
            quality["items"],
            sorted(quality["items"],
                   key=lambda row: (-row["quality_score"],
                                    -row["words"], row["saga"])),
        )
        self.assertEqual(
            length["items"],
            sorted(length["items"],
                   key=lambda row: (-row["words"],
                                    -row["quality_score"], row["saga"])),
        )

    def test_exact_filter_limits_and_physically_verified_export(self):
        index = list_books(domain="realm", saga="homecoming", limit=4)
        self.assertEqual(4, len(index["items"]))
        self.assertTrue(all(row["saga"] == "homecoming" for row in index["items"]))
        with self.assertRaises(StudioError):
            list_books(limit=1000)
        from scripts.export_game_studio_saga_handbooks import export
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            output = export(directory, offset=0, limit=2)
            self.assertEqual(2, output["exported"])
            manifest = json.loads(Path(output["manifest"]).read_text())
            self.assertEqual(2, len(manifest["receipts"]))
            self.assertEqual(2, len(manifest["ranking"]["quality"]))
            for item in manifest["receipts"]:
                self.assertEqual(
                    item["content_sha256"],
                    sha256((directory / item["path"]).read_bytes()).hexdigest(),
                )
            with self.assertRaises(FileExistsError):
                export(directory, offset=0, limit=2)


if __name__ == "__main__":
    unittest.main()
