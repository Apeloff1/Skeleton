"""500B production catalogue, 450B real epoch compositions and 90M manuals.

Evidence remains candidate-only; counts never imply distinct games or runtimes.
"""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.forge.game_frontier_studio import StudioError, StudioProject
from skeleton.forge.game_frontier_studio_authoring import (
    AUTHORING_ACTIONS, execute_authoring, authored_summary,
    project_digest, apply_authoring_batch,
)
from skeleton.forge.game_frontier_studio_chronicle_production import CHRONICLE_ACTIONS
from skeleton.forge.game_frontier_studio_epoch_production import (
    EPOCH_ACTIONS, EPOCHS, parent_action, describe_epoch, search_epochs,
)
from skeleton.forge.game_frontier_studio_epoch_handbooks import (
    BOOK_COUNT, EPOCH_BOOK_PATHS, identity, number, receipt,
    list_books, rank_variants, grade,
)
from skeleton.testing.test_game_frontier_studio_production_5000 import (
    original_project, arguments,
)


class FiveHundredBillionEpochs(unittest.TestCase):
    def test_stable_legacy_boundaries_and_virtual_rank(self):
        self.assertEqual(450_000_000_000, len(EPOCH_ACTIONS))
        self.assertEqual(500_000_000_000, len(AUTHORING_ACTIONS))
        self.assertEqual(CHRONICLE_ACTIONS[0], AUTHORING_ACTIONS[5_000_000_000])
        self.assertEqual(EPOCH_ACTIONS[0], AUTHORING_ACTIONS[50_000_000_000])
        self.assertEqual(EPOCH_ACTIONS[-1], AUTHORING_ACTIONS[-1])
        for index in (0, 1, 9, 10, 110, 9999, 45_000_000_000,
                      99_999_999_999, 449_999_999_999):
            operation = EPOCH_ACTIONS[index]
            parent, axis = parent_action(operation)
            self.assertEqual(CHRONICLE_ACTIONS[index // 10], parent)
            self.assertEqual(EPOCHS[index % 10], EPOCHS[axis])
            self.assertTrue(operation in EPOCH_ACTIONS)
            self.assertEqual(operation, describe_epoch(operation)["operation"])
        for invalid in ("epoch_run_shell__________daybreak_routes",
                        "epoch_unknown__________future_convergence",
                        EPOCH_ACTIONS[0] + "_forged"):
            self.assertNotIn(invalid, EPOCH_ACTIONS)
        with self.assertRaises(IndexError):
            _ = EPOCH_ACTIONS[len(EPOCH_ACTIONS)]

    def test_filtered_search_is_exact_and_bounded(self):
        for offset in (0, 9, 10, 123, 450_000_000_000 - 32):
            page = search_epochs(offset=offset, limit=32)
            self.assertEqual(
                [row["operation"] for row in page["items"]],
                list(EPOCH_ACTIONS[offset:offset+32]),
            )
        filtered = search_epochs(
            domain="realm", system_layer="stealth",
            director="audio_cues", finish="alternate_endings",
            worldline="sky_navigation", phase="storm_shelters",
            campaign="siege_campaigns", chronicle="emergency_response",
            epoch="spring_thaw", limit=32,
        )
        self.assertEqual(450, filtered["matched"])
        self.assertEqual(32, len(filtered["items"]))
        with self.assertRaises(StudioError):
            search_epochs(epoch="../../bad")
        with self.assertRaises(StudioError):
            search_epochs(limit=1000)

    def test_temporal_source_edits_are_reproducible_and_immutable(self):
        base = original_project()
        before = project_digest(base)
        hashes = set()
        for axis in range(10):
            action = EPOCH_ACTIONS[axis]
            one = execute_authoring(base, action, arguments(action))
            two = execute_authoring(base, action, arguments(action))
            self.assertIsInstance(one, StudioProject)
            self.assertNotEqual(before, project_digest(one))
            self.assertEqual(project_digest(one), project_digest(two))
            self.assertEqual(base.placements, one.placements[:len(base.placements)])
            self.assertEqual(base.native_quests, one.native_quests[:len(base.native_quests)])
            self.assertGreater(len(one.environmental_pages), len(base.environmental_pages))
            hashes.add(project_digest(one))
        self.assertEqual(10, len(hashes))
        self.assertEqual(before, project_digest(base))

    def test_full_transaction_receipts_and_failure_rollback(self):
        base = original_project()
        action = EPOCH_ACTIONS[0]
        result = apply_authoring_batch(base, [
            {"action": action, "parameters": arguments(action)},
        ])
        self.assertTrue(result["receipt"]["actually_changed"])
        self.assertEqual(450_000_000_000,
                         authored_summary(result["project"])["epoch_recipe_count"])
        self.assertEqual(500_000_000_000,
                         authored_summary(result["project"])["catalog_total"])
        with self.assertRaises(StudioError):
            apply_authoring_batch(base, [
                {"action": action, "parameters": arguments(action)},
                {"action": action, "parameters": {
                    **arguments(action), "instance_id": "../../bad",
                }},
            ])
        self.assertEqual(project_digest(base), project_digest(original_project()))


class OneHundredMillionIndexedBooks(unittest.TestCase):
    def test_reversible_book_identity(self):
        self.assertEqual(90_000_000, BOOK_COUNT)
        self.assertEqual(90_000_000, len(EPOCH_BOOK_PATHS))
        for index in (0, 9, 10, 110, 10_000, 89_999_999):
            parts = identity(index)
            self.assertEqual(index, number(*parts))
            self.assertTrue(EPOCH_BOOK_PATHS[index].endswith(".md"))
        with self.assertRaises(StudioError):
            identity(90_000_000)

    def test_fifty_source_examples_and_measured_quality(self):
        row = receipt(*identity(0))
        self.assertEqual(50, row["markdown"].count(" | epoch_"))
        self.assertEqual(10, row["markdown"].count("Executable epoch source: "))
        self.assertEqual(100, row["quality_score"])
        self.assertGreater(row["words"], 1000)
        self.assertEqual(sha256(row["markdown"].encode("utf8")).hexdigest(),
                         row["content_sha256"])
        cut = row["markdown"].replace("## Fifty registered source archetypes",
                                       "## Unregistered source archetypes")
        self.assertLess(grade(cut, row)["quality_score"], row["quality_score"])

    def test_filter_rank_and_exported_sha_receipts(self):
        page = list_books(domain="realm", epoch="spring_thaw", limit=3)
        self.assertEqual(3, len(page["items"]))
        self.assertTrue(all(row["epoch"] == "spring_thaw" for row in page["items"]))
        args = identity(0)
        ranked = rank_variants(*args[:-1], sort="quality")
        self.assertEqual(10, ranked["compared"])
        self.assertEqual(10, len(ranked["items"]))
        self.assertEqual(
            ranked["items"],
            sorted(ranked["items"],
                   key=lambda r: (-r["quality_score"], -r["words"], r["epoch"])),
        )
        from scripts.export_game_studio_epoch_handbooks import export
        with TemporaryDirectory() as folder:
            root = Path(folder)
            result = export(root, offset=0, limit=2)
            self.assertEqual(2, result["exported"])
            manifest = json.loads(Path(result["manifest"]).read_text())
            self.assertEqual(2, len(manifest["receipts"]))
            for row in manifest["receipts"]:
                self.assertEqual(row["content_sha256"],
                                 sha256((root / row["path"]).read_bytes()).hexdigest())
            with self.assertRaises(FileExistsError):
                export(root, offset=0, limit=2)


if __name__ == "__main__":
    unittest.main()
