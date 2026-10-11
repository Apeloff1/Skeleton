"""Game-studio regression and adversarial execution tests, offline and deterministic."""
from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.dual_runtime_export import (
    DualRuntimeExportError, DualRuntimePackage, render_dual_runtime_package,
)
from skeleton.ai.game_builder.mirror_room_runtime import (
    MirrorRoomError, review_playable_project,
)
from skeleton.ai.game_builder.original_game_studio import (
    StudioError, export_studio_run, run_original_game_studio,
)
from skeleton.ai.game_builder.original_game_studio_cli import main
from skeleton.ai.game_builder.playable_compiler import compile_original_game
from skeleton.ai.game_builder.playable_world import GameBuildIntent
from skeleton.ai.game_builder.studio_tool_fabric import (
    Access, Actor, Phase, ToolFabric, ToolFabricError, ToolRequest, ToolSpec,
)


class ToolFabricContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fabric = ToolFabric()
        self.input_digest = "a" * 64

    def request(self, actor=Actor.JEEVES, phase=Phase.ORIGINAL, tool="world.generate"):
        return ToolRequest(actor, phase, tool, self.input_digest, "Build novel test game")

    def test_discovery_has_consistent_roles_and_phases(self):
        self.assertIn("world.generate", [
            x.tool_id for x in self.fabric.discover(actor=Actor.DRAGON, phase=Phase.ORIGINAL)
        ])
        self.assertNotIn("package.source", [
            x.tool_id for x in self.fabric.discover(actor=Actor.COMPANION, phase=Phase.CONSUMER)
        ])
        self.assertIn("mirror.fuzz", [
            x.tool_id for x in self.fabric.discover(actor=Actor.MIRROR, phase=Phase.REVIEW)
        ])
        self.assertEqual(len(self.fabric.discover(actor=Actor.OPERATOR, phase=Phase.ORIGINAL)),
                         len(set(x.tool_id for x in self.fabric.discover(
                             actor=Actor.OPERATOR, phase=Phase.ORIGINAL))))

    def test_role_phase_budget_and_authorization_fail_closed(self):
        self.assertRaises(PermissionError, self.fabric.plan,
                          (self.request(),), authorized=False)
        with self.assertRaisesRegex(ToolFabricError, "role/phase"):
            self.fabric.plan((self.request(Actor.COMPANION, Phase.CONSUMER, "package.source"),),
                             authorized=True)
        with self.assertRaisesRegex(ToolFabricError, "resource budget"):
            self.fabric.plan((self.request(),), authorized=True, max_resource_units=1)
        with self.assertRaisesRegex(ToolFabricError, "not registered"):
            self.fabric.plan((self.request(tool="unregistered.executor"),),
                             authorized=True)
        with self.assertRaisesRegex(ToolFabricError, "tool ID collision"):
            ToolFabric((next(x for x in self.fabric.discover(
                actor=Actor.JEEVES, phase=Phase.ORIGINAL) if x.tool_id == "world.generate"),))

    def test_write_and_external_adapter_are_separate_grants(self):
        filesystem = self.request(Actor.JEEVES, Phase.CONSUMER, "package.source")
        plan = self.fabric.plan((filesystem,), authorized=True)
        self.assertIn("package.source", plan.external_blocked)
        self.assertFalse(plan.write_authorized)
        granted = self.fabric.plan((filesystem,), authorized=True,
                                   allow_filesystem_write=True)
        self.assertFalse(granted.external_blocked)
        ext = ToolSpec(
            "engine.homebrew_adapter", "locally installed custom homebrew engine",
            frozenset({Phase.STEPPING_STONE}),
            frozenset({Actor.DRAGON}),
            Access.EXTERNAL, 7, frozenset({"process"}),
            "SPDX:MIT", "f" * 64,
        )
        extra = ToolFabric((ext,))
        req = self.request(Actor.DRAGON, Phase.STEPPING_STONE, ext.tool_id)
        self.assertEqual(extra.plan((req,), authorized=True).external_blocked,
                         (ext.tool_id,))
        self.assertFalse(extra.plan(
            (req,), authorized=True,
            enabled_external={ext.tool_id: "f" * 64},
        ).external_blocked)
        self.assertIn(ext.tool_id, [
            t.tool_id for t in extra.discover(
                actor=Actor.DRAGON, phase=Phase.STEPPING_STONE)])

    def test_rejects_untrusted_external_tool_declarations(self):
        with self.assertRaises(ToolFabricError):
            ToolSpec("external.tool", "external",
                     frozenset({Phase.ORIGINAL}), frozenset({Actor.DRAGON}),
                     Access.EXTERNAL, 5, frozenset({"network"}), "MIT")
        with self.assertRaises(ToolFabricError):
            ToolSpec("external.tool", "external",
                     frozenset({Phase.ORIGINAL}), frozenset({Actor.DRAGON}),
                     Access.BUILTIN, 5, frozenset({"shell"}), "MIT")
        with self.assertRaises(ToolFabricError):
            ToolRequest(Actor.DRAGON, Phase.ORIGINAL, "world.generate",
                        "not-sha256", "reason")


class ExecutableStudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.intent = GameBuildIntent(
            project_id="original-mirror-room-v1",
            title="Mirror Room Odyssey",
            subtitle="Original consumer stepping stone.",
            seed=49216, width=11, height=11, levels=1,
            collectibles_per_level=1, hazards_per_level=1,
            theme="forest", starting_health=4,
        )
        cls.project = compile_original_game(cls.intent, authorized=True)
        cls.package = render_dual_runtime_package(cls.project, authorized=True)

    def test_mirror_128_real_attempts_all_families_and_deterministic(self):
        report = review_playable_project(
            self.project, self.package, authorized=True, attempts=128)
        self.assertTrue(report.passed, report.failures)
        self.assertEqual(len(report.probes), 128)
        self.assertEqual(len({p.family for p in report.probes}), 12)
        self.assertEqual(report.to_payload()["failed_count"], 0)
        self.assertEqual(report.digest, review_playable_project(
            self.project, self.package, authorized=True, attempts=128).digest)
        self.assertTrue(all(
            len(p.evidence_digest) == 64 and p.observed == p.expected for p in report.probes))
        self.assertFalse(report.to_payload()["native_hardware_reviewed"])

    def test_adversarial_budget_authority_and_precheck_corruption(self):
        with self.assertRaises(PermissionError):
            review_playable_project(self.project, self.package,
                                    authorized=False)
        with self.assertRaises(MirrorRoomError):
            review_playable_project(self.project, self.package,
                                    authorized=True, attempts=10)
        damaged = dict(self.package.files)
        damaged["index.html"] += b"tampered"
        # Construct object without validation to simulate mutation after creation.
        original = self.package.files["index.html"]
        try:
            self.package.files["index.html"] = damaged["index.html"]
            with self.assertRaisesRegex(MirrorRoomError, "changed"):
                review_playable_project(self.project, self.package,
                                        authorized=True, attempts=64)
        finally:
            self.package.files["index.html"] = original

    def test_real_studio_build_companion_xp_and_atomic_consumer_dossier(self):
        run = run_original_game_studio(
            self.intent, authorized=True, mirror_attempts=128,
            companion_practice_games=2,
        )
        self.assertEqual([s.name for s in run.stages], [
            "original", "stepping_stone", "consumer_source_candidate"])
        self.assertTrue(run.mirror.passed)
        self.assertEqual(len(run.practice), 2)
        self.assertTrue(all(p.winning_steps > 0 for p in run.practice))
        self.assertEqual(len(set(p.world_digest for p in run.practice)), 2)
        self.assertGreater(sum(p.capability_xp for p in run.practice), 0)
        self.assertNotEqual(run.practice[0].world_digest, run.project.world.digest)
        self.assertIn("release-blocked", run.consumer.to_payload()["status"])
        self.assertIn("platform_hardware_tested", run.consumer.blockers)
        self.assertIn("rights_reviewed", run.consumer.blockers)
        self.assertEqual(run.package.manifest["schema"],
                         "skeleton.game_builder.studio_package.v1")
        self.assertEqual(
            set(run.package.files), set(run.package.manifest["files"]) | {"release.json"})
        for path in ("studio/pipeline.json", "studio/consumer_gate.json",
                     "studio/mirror_room.json", "studio/companion_practice.json",
                     "studio/jeeves_dragon_tools.json", "godot/project.godot",
                     "index.html"):
            self.assertIn(path, run.package.files)
            self.assertEqual(sha256(run.package.files[path]).hexdigest(),
                             run.package.manifest["files"][path])
        self.assertEqual(run.digest, run_original_game_studio(
            self.intent, authorized=True, mirror_attempts=128,
            companion_practice_games=2).digest)
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "original-product"
            with self.assertRaises(PermissionError):
                export_studio_run(run, str(destination), authorized=False)
            self.assertEqual(
                export_studio_run(run, str(destination), authorized=True), destination)
            self.assertTrue((destination / "godot/scripts/main.gd").exists())
            self.assertTrue((destination / "studio/mirror_room.json").exists())
            self.assertEqual(json.loads((destination / "release.json").read_text()),
                             run.package.manifest)
            with self.assertRaisesRegex(DualRuntimeExportError, "already exists"):
                export_studio_run(run, str(destination), authorized=True)

    def test_authorized_human_authored_pipeline_and_rejections(self):
        authored = [list(level.rows) for level in self.project.world.levels]
        with self.assertRaises(StudioError):
            run_original_game_studio(
                self.intent, authorized=True,
                human_reviewed_tiles=authored, human_authored_approved=False)
        with self.assertRaises(PermissionError):
            run_original_game_studio(self.intent, authorized=False)
        with self.assertRaises(StudioError):
            run_original_game_studio(self.intent, authorized=True, companion_practice_games=9)
        authored_run = run_original_game_studio(
            self.intent, authorized=True,
            human_reviewed_tiles=authored, human_authored_approved=True,
            companion_practice_games=0, mirror_attempts=64)
        self.assertEqual(authored_run.source, "original-authored")
        self.assertEqual(authored_run.project.world.algorithm,
                         "skeleton.game_builder.authored-tiles.v1")
        self.assertFalse(authored_run.practice)

    def test_cli_no_operator_no_export_and_usable_offline_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            intent = Path(tmp) / "intent.json"
            intent.write_text(json.dumps(self.intent.to_payload()), encoding="utf-8")
            output = Path(tmp) / "studio-project"
            args = ["--intent", str(intent), "--output", str(output),
                    "--mirror-attempts", "64", "--companion-practice", "1"]
            self.assertEqual(main(args), 2)
            self.assertFalse(output.exists())
            response = io.StringIO()
            with redirect_stdout(response):
                self.assertEqual(main(args + ["--trusted-local-operator"]), 0)
            result = json.loads(response.getvalue())
            self.assertEqual(result["mirror_attempts"], 64)
            self.assertEqual(result["mirror_failures"], 0)
            self.assertEqual(result["verified_practice_games"], 1)
            self.assertFalse(result["publication_authorized"])
            self.assertTrue((output / "studio/consumer_gate.json").is_file())
            self.assertEqual(main(args + ["--trusted-local-operator"]), 2)


if __name__ == "__main__":
    unittest.main()
