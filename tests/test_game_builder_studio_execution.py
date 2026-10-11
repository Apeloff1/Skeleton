"""Real execution plane: role scopes, deterministic receipts and playable outputs."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.playable_compiler import compile_original_game
from skeleton.ai.game_builder.playable_world import GameBuildIntent
from skeleton.ai.game_builder.studio_execution_plane import (
    ExecutionPlaneError, execute_local_tool_plan, EXECUTABLE_TOOLS,
)
from skeleton.ai.game_builder.studio_tool_fabric import (
    Actor, Phase, ToolFabric, ToolRequest,
)


class NativeGameToolExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.intent = GameBuildIntent(
            project_id="actual-jeeves-dragon-2026",
            title="Original Game Tool Execution",
            subtitle="A real tool-driven game, not a descriptive plan.",
            seed=742193, width=11, height=11, levels=1,
            collectibles_per_level=1, hazards_per_level=1,
            theme="ocean", starting_health=4,
        )
        cls.fabric = ToolFabric()
        cls.digest = canonical_digest(cls.intent.to_payload())
        cls.sequence = (
            (Actor.JEEVES, Phase.ORIGINAL, "world.generate"),
            (Actor.DRAGON, Phase.STEPPING_STONE, "game.simulate"),
            (Actor.DRAGON, Phase.STEPPING_STONE, "game.browser"),
            (Actor.DRAGON, Phase.STEPPING_STONE, "game.godot"),
            (Actor.COMPANION, Phase.STEPPING_STONE, "companion.practice"),
            (Actor.MIRROR, Phase.REVIEW, "mirror.fuzz"),
            (Actor.JEEVES, Phase.CONSUMER, "release.assess"),
            (Actor.JEEVES, Phase.CONSUMER, "package.source"),
        )

    def plan(self, sequence=None, *, write=False, fabric=None):
        rows = tuple(ToolRequest(a, p, name, self.digest,
                                 "Execute an approved local game creation capability")
                     for a, p, name in (sequence or self.sequence))
        return (fabric or self.fabric).plan(
            rows, authorized=True, allow_filesystem_write=write,
        )

    def test_actual_compiled_browser_godot_companion_mirror_and_source_export(self):
        plan = self.plan(write=True)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "real-original-project"
            outcome = execute_local_tool_plan(
                self.intent, plan, authorized=True, destination=output,
                companion_games=2, mirror_attempts=128,
            )
            self.assertEqual(len(outcome.receipts), 8)
            self.assertEqual(outcome.world.digest,
                             compile_original_game(self.intent, authorized=True).world.digest)
            self.assertEqual(outcome.project.proof.final_state.status, "won")
            self.assertTrue(outcome.mirror.passed)
            self.assertEqual(len(outcome.mirror.probes), 128)
            self.assertEqual(len(outcome.practice_packages), 2)
            self.assertTrue(all("index.html" in p.files and
                                "godot/scripts/main.gd" in p.files
                                for p in outcome.practice_packages))
            self.assertTrue((output / "index.html").is_file())
            self.assertTrue((output / "godot/project.godot").is_file())
            self.assertEqual(outcome.exported_path, output)
            self.assertFalse(outcome.to_payload()["external_code_executed"])
            self.assertFalse(outcome.to_payload()["publication_approved"])
            self.assertEqual(
                [x.index for x in outcome.receipts], list(range(8)))
            previous = None
            for receipt in outcome.receipts:
                self.assertEqual(receipt.predecessor_digest, previous)
                self.assertEqual(receipt.status, "executed")
                self.assertEqual(len(receipt.evidence_digest), 64)
                previous = receipt.digest
            # A second content-identical run must leave exactly the same
            # tool execution provenance regardless of destination path.
            second = execute_local_tool_plan(
                self.intent, self.plan(write=False, sequence=self.sequence[:-1]),
                authorized=True, companion_games=2, mirror_attempts=128)
            self.assertEqual(
                [r.digest for r in outcome.receipts[:-1]],
                [r.digest for r in second.receipts])
            self.assertEqual(second.world, outcome.world)
            self.assertEqual(second.mirror.digest, outcome.mirror.digest)
            self.assertEqual(outcome.package.manifest, second.package.manifest)

    def test_authored_world_takes_independent_approved_editor_path(self):
        project = compile_original_game(self.intent, authorized=True)
        authored = [list(level.rows) for level in project.world.levels]
        seq = (
            (Actor.JEEVES, Phase.ORIGINAL, "world.authored"),
            (Actor.DRAGON, Phase.STEPPING_STONE, "game.simulate"),
            (Actor.DRAGON, Phase.STEPPING_STONE, "game.browser"),
            (Actor.DRAGON, Phase.STEPPING_STONE, "game.godot"),
            (Actor.MIRROR, Phase.REVIEW, "mirror.fuzz"),
        )
        plan = self.plan(seq)
        result = execute_local_tool_plan(
            self.intent, plan, authorized=True, authored_levels=authored,
            human_reviewed=True, mirror_attempts=64)
        self.assertTrue(result.mirror.passed)
        self.assertEqual(result.world.algorithm,
                         "skeleton.game_builder.authored-tiles.v1")
        self.assertEqual(result.project.proof.final_state.status, "won")
        with self.assertRaisesRegex(ExecutionPlaneError, "human-reviewed"):
            execute_local_tool_plan(self.intent, plan, authorized=True)
        with self.assertRaisesRegex(ExecutionPlaneError, "without"):
            execute_local_tool_plan(self.intent, self.plan(seq[1:]), authorized=True,
                                    authored_levels=authored, human_reviewed=True)

    def test_editing_uses_real_content_hash_and_operator_scopes(self):
        seq = (
            (Actor.JEEVES, Phase.ORIGINAL, "world.generate"),
            (Actor.DRAGON, Phase.STEPPING_STONE, "game.editor"),
        )
        plan = self.plan(seq)
        outcome = execute_local_tool_plan(self.intent, plan, authorized=True)
        self.assertEqual(len(outcome.receipts), 2)
        self.assertEqual(len(outcome.receipts[1].output_digest), 64)
        self.assertNotEqual(outcome.receipts[1].output_digest, outcome.world.digest)
        with self.assertRaises(PermissionError):
            execute_local_tool_plan(self.intent, plan, authorized=False)

    def test_plan_forgery_wrong_intent_invalid_dependency_and_duplicate(self):
        base = self.plan(self.sequence[:-1])
        bad = replace(base, resource_units=1)
        with self.assertRaisesRegex(ExecutionPlaneError, "changed"):
            execute_local_tool_plan(self.intent, bad, authorized=True)
        bad_rows = (
            ToolRequest(Actor.JEEVES, Phase.ORIGINAL, "world.generate",
                        "f" * 64, "Attempt cross-game identity reuse"),
        )
        bad_plan = self.fabric.plan(bad_rows, authorized=True)
        with self.assertRaisesRegex(ExecutionPlaneError, "unanchored"):
            execute_local_tool_plan(self.intent, bad_plan, authorized=True)
        seq = (
            (Actor.JEEVES, Phase.CONSUMER, "package.source"),
            (Actor.JEEVES, Phase.ORIGINAL, "world.generate"),
        )
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "no-project"
            with self.assertRaisesRegex(ExecutionPlaneError, "prerequisite"):
                execute_local_tool_plan(
                    self.intent, self.plan(seq, write=True),
                    authorized=True, destination=destination,
                )
            self.assertFalse(destination.exists())
        duplicate = (
            (Actor.JEEVES, Phase.ORIGINAL, "world.generate"),
            (Actor.JEEVES, Phase.ORIGINAL, "world.generate"),
        )
        with self.assertRaisesRegex(ExecutionPlaneError, "more than once"):
            execute_local_tool_plan(
                self.intent, self.plan(duplicate), authorized=True)

    def test_rejects_unimplemented_builtin_and_external_tool_even_when_declared(self):
        self.assertNotIn("game.native_recipe", EXECUTABLE_TOOLS)
        seq = ((Actor.JEEVES, Phase.CONSUMER, "game.native_recipe"),)
        with self.assertRaisesRegex(ExecutionPlaneError, "unsupported"):
            execute_local_tool_plan(
                self.intent, self.plan(seq), authorized=True)
        seq = ((Actor.JEEVES, Phase.RESEARCH, "knowledge.search"),)
        with self.assertRaisesRegex(ExecutionPlaneError, "unsupported"):
            execute_local_tool_plan(
                self.intent, self.plan(seq), authorized=True)

    def test_no_write_without_explicit_approval_destination_or_mirror(self):
        seq = self.sequence
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / "denied"
            with self.assertRaisesRegex(ExecutionPlaneError, "write grant"):
                execute_local_tool_plan(
                    self.intent, self.plan(seq, write=False),
                    authorized=True, destination=dest)
            self.assertFalse(dest.exists())
            with self.assertRaisesRegex(ExecutionPlaneError, "destination"):
                execute_local_tool_plan(
                    self.intent, self.plan(seq, write=True), authorized=True)
            short_seq = (
                (Actor.JEEVES, Phase.ORIGINAL, "world.generate"),
                (Actor.DRAGON, Phase.STEPPING_STONE, "game.browser"),
                (Actor.DRAGON, Phase.STEPPING_STONE, "game.godot"),
                (Actor.JEEVES, Phase.CONSUMER, "package.source"),
            )
            with self.assertRaisesRegex(ExecutionPlaneError, "prerequisite"):
                execute_local_tool_plan(
                    self.intent, self.plan(short_seq, write=True),
                    authorized=True, destination=dest)
            self.assertFalse(dest.exists())


if __name__ == "__main__":
    unittest.main()
